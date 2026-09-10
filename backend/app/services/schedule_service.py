"""
Medication Schedule Calculation Service

Deterministic service — NOT an LLM agent.
Converts frequency descriptions into concrete time slots, and materializes those
slots as MedicationSchedule rows when a prescription is verified.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.patient import Patient
from app.models.prescribed_medication import PrescribedMedication
from app.models.reminder import Reminder
from app.models.types import utcnow

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from app.models.prescription import Prescription


def resolve_patient_timezone(patient: Optional[Patient]) -> ZoneInfo:
    """Patient's IANA timezone, falling back to UTC on anything unusable."""
    if not patient or not patient.timezone:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(patient.timezone)
    except (KeyError, ValueError, OSError):
        return ZoneInfo("UTC")


def dose_instant_utc(scheduled_time: time, on_local_date: date, tz: ZoneInfo) -> datetime:
    """
    The single definition of "when is this dose, in UTC".

    A schedule stores a wall-clock time and the patient stores a timezone; the instant
    is the combination. This exists as one function because three call sites need the
    identical answer and were computing it separately:

    - the reminder poller, deciding whether a dose is due
    - ``record_patient_response``, deriving ``MedicationEvent.scheduled_at`` when the
      patient self-logs
    - ``get_todays_doses``, telling the client which doses exist

    If those drift by so much as an hour, the dose the UI displays and the event the
    backend writes are different rows: the patient taps "taken", a MedicationEvent
    appears for a slot never shown, and the original slot later expires as MISSED. The
    adherence rate then drops for a dose that was actually taken.
    """
    return datetime.combine(on_local_date, scheduled_time, tzinfo=tz).astimezone(
        timezone.utc
    )


@dataclass(frozen=True)
class TodayDose:
    """
    One scheduled dose on the patient's local calendar day, with its current status.

    ``schedule_id`` is what a client posts back to /adherence/log. ``scheduled_at`` is
    the authoritative UTC instant; the backend re-derives it on write and never trusts
    a client-supplied timestamp.
    """

    schedule_id: int
    event_id: Optional[int]
    reminder_id: Optional[int]
    medicine_name: str
    strength: Optional[str]
    dose: Optional[str]
    instructions: Optional[str]
    relation_to_meal: Optional[str]
    scheduled_at: datetime
    scheduled_local_time: str
    status: str
    confirmed_at: Optional[datetime]
    skip_reason_code: Optional[str]
    skip_reason: Optional[str]
    is_due: bool


async def get_todays_doses(
    db: AsyncSession,
    patient_id: int,
    reference_time: Optional[datetime] = None,
) -> List[TodayDose]:
    """
    Every dose on the patient's local calendar day today, in chronological order.

    Status is PENDING for a slot with no MedicationEvent yet — the row does not exist
    until something happens to it, so absence means "not yet logged", not "missing
    data".

    Only ACTIVE schedules of active prescribed medications are returned, and only
    within the schedule's start/end course dates, matching ``create_due_reminders``
    exactly. A discontinued medication must not appear on the patient's list.

    The two filters are not redundant. The stored status excludes rows that were
    retired by a decision (CANCELLED) or replaced (SUPERSEDED); the date window
    excludes a course that has simply run out, which is
    ``ScheduleLifecycle.COMPLETED`` and is derived rather than stored. Together they
    are exactly ``lifecycle_on(local_today) is ACTIVE``, expressed in SQL so it can
    run in the database.
    """
    now_utc = reference_time or utcnow()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    patient = await db.get(Patient, patient_id)
    tz = resolve_patient_timezone(patient)
    local_today = now_utc.astimezone(tz).date()

    stmt = (
        select(MedicationSchedule)
        .join(
            PrescribedMedication,
            MedicationSchedule.prescribed_medication_id == PrescribedMedication.id,
        )
        .options(selectinload(MedicationSchedule.prescribed_medication))
        .where(
            MedicationSchedule.patient_id == patient_id,
            MedicationSchedule.status == ScheduleLifecycle.ACTIVE.value,
            PrescribedMedication.is_active.is_(True),
            MedicationSchedule.start_date <= local_today,
        )
    )
    schedules = (await db.execute(stmt)).scalars().all()

    in_course = [
        s for s in schedules if s.end_date is None or s.end_date >= local_today
    ]
    if not in_course:
        return []

    instants = {s.id: dose_instant_utc(s.scheduled_time, local_today, tz) for s in in_course}

    # One query for the events and one for the reminders, keyed on the same
    # (schedule_id, instant) pair the write path uses.
    events = (
        await db.execute(
            select(MedicationEvent).where(
                MedicationEvent.schedule_id.in_(instants.keys()),
                MedicationEvent.scheduled_at.in_(instants.values()),
            )
        )
    ).scalars().all()
    event_by_slot = {(e.schedule_id, e.scheduled_at): e for e in events}

    reminders = (
        await db.execute(
            select(Reminder).where(
                Reminder.schedule_id.in_(instants.keys()),
                Reminder.scheduled_for.in_(instants.values()),
            )
        )
    ).scalars().all()
    reminder_by_slot = {(r.schedule_id, r.scheduled_for): r for r in reminders}

    doses: List[TodayDose] = []
    for sched in in_course:
        instant = instants[sched.id]
        slot = (sched.id, instant)
        event = event_by_slot.get(slot)
        reminder = reminder_by_slot.get(slot)
        med = sched.prescribed_medication

        doses.append(
            TodayDose(
                schedule_id=sched.id,
                event_id=event.id if event else None,
                reminder_id=reminder.id if reminder else None,
                medicine_name=med.medicine_name if med else "Scheduled medication",
                strength=med.strength if med else None,
                dose=med.dose if med else None,
                instructions=med.instructions if med else None,
                relation_to_meal=sched.relation_to_meal,
                scheduled_at=instant,
                scheduled_local_time=sched.scheduled_time.strftime("%H:%M"),
                status=event.status if event else MedicationEventStatus.PENDING.value,
                confirmed_at=event.confirmed_at if event else None,
                skip_reason_code=event.skip_reason_code if event else None,
                skip_reason=event.skip_reason if event else None,
                is_due=instant <= now_utc,
            )
        )

    doses.sort(key=lambda d: d.scheduled_at)
    return doses



# Standard medication time mappings
FREQUENCY_TIME_MAP: dict[str, list[time]] = {
    "once_daily": [time(8, 0)],                           # 8:00 AM
    "twice_daily": [time(8, 0), time(20, 0)],             # 8:00 AM, 8:00 PM
    "three_times_daily": [time(8, 0), time(14, 0), time(20, 0)],  # 8AM, 2PM, 8PM
    "four_times_daily": [time(6, 0), time(12, 0), time(18, 0), time(23, 0)],
    "every_12_hours": [time(8, 0), time(20, 0)],
    "every_8_hours": [time(6, 0), time(14, 0), time(22, 0)],
    "every_6_hours": [time(6, 0), time(12, 0), time(18, 0), time(0, 0)],
    "at_bedtime": [time(22, 0)],
    "in_the_morning": [time(8, 0)],
    "before_breakfast": [time(7, 0)],
    "after_breakfast": [time(8, 30)],
    "before_lunch": [time(12, 30)],
    "after_lunch": [time(13, 30)],
    "before_dinner": [time(19, 0)],
    "after_dinner": [time(20, 30)],
}

# Map natural-language frequency to standard keys
FREQUENCY_ALIASES: dict[str, str] = {
    "once daily": "once_daily",
    "od": "once_daily",
    "1x daily": "once_daily",
    "twice daily": "twice_daily",
    "bd": "twice_daily",
    "bid": "twice_daily",
    "b.i.d.": "twice_daily",
    "2x daily": "twice_daily",
    "three times daily": "three_times_daily",
    "tid": "three_times_daily",
    "t.i.d.": "three_times_daily",
    "tds": "three_times_daily",
    "3x daily": "three_times_daily",
    "four times daily": "four_times_daily",
    "qid": "four_times_daily",
    "q.i.d.": "four_times_daily",
    "4x daily": "four_times_daily",
    "every 12 hours": "every_12_hours",
    "q12h": "every_12_hours",
    "every 8 hours": "every_8_hours",
    "q8h": "every_8_hours",
    "every 6 hours": "every_6_hours",
    "q6h": "every_6_hours",
    "at bedtime": "at_bedtime",
    "hs": "at_bedtime",
    "h.s.": "at_bedtime",
    "at night": "at_bedtime",
    "in the morning": "in_the_morning",
    "am": "in_the_morning",
    "before breakfast": "before_breakfast",
    "after breakfast": "after_breakfast",
    "before lunch": "before_lunch",
    "after lunch": "after_lunch",
    "before dinner": "before_dinner",
    "after dinner": "after_dinner",
}


class UnknownFrequencyError(ValueError):
    """
    Raised when a frequency string cannot be mapped to concrete dose times.

    Deliberately NOT defaulted to once-daily: guessing an interval from an
    unrecognized or misread prescription silently changes the dose (e.g. 'q4h'
    treated as once-daily is a six-fold underdose). Unmapped frequencies must
    go back to a human via the prescription verification flow.
    """


# Sentinel for as-needed medication, which is never auto-scheduled.
AS_NEEDED = "as_needed"

AS_NEEDED_ALIASES: set[str] = {
    "prn", "p.r.n.", "as needed", "as required", "when required", "sos",
}


def normalize_frequency(frequency: str) -> str:
    """
    Normalize a frequency string to a standard key.

    Returns:
        A key in FREQUENCY_TIME_MAP, or AS_NEEDED for as-needed medication.

    Raises:
        UnknownFrequencyError: if the frequency cannot be recognized.
    """
    freq_lower = frequency.strip().lower()

    # As-needed medication is dispensed on demand, not on a clock
    if freq_lower in AS_NEEDED_ALIASES:
        return AS_NEEDED

    # Direct match
    if freq_lower in FREQUENCY_TIME_MAP:
        return freq_lower

    # Alias match
    if freq_lower in FREQUENCY_ALIASES:
        return FREQUENCY_ALIASES[freq_lower]

    raise UnknownFrequencyError(
        f"Unrecognized frequency {frequency!r} - cannot derive dose times, "
        f"requires human verification"
    )


def calculate_schedule_times(frequency: str) -> list[time]:
    """
    Convert a frequency description into concrete daily time slots.

    Args:
        frequency: Natural language or abbreviation (e.g., 'Twice daily', 'BD', 'q8h')

    Returns:
        List of time objects representing daily dose times. Empty list for
        as-needed (PRN) medication, which must not generate reminders.

    Raises:
        UnknownFrequencyError: if the frequency cannot be recognized.
    """
    normalized = normalize_frequency(frequency)
    if normalized == AS_NEEDED:
        return []
    return FREQUENCY_TIME_MAP[normalized]


def calculate_end_date(
    start_date: date,
    duration_days: Optional[int] = None,
) -> Optional[date]:
    """
    Calculate the end date for a medication schedule.

    Args:
        start_date: When the medication starts
        duration_days: Number of days prescribed (None = ongoing)

    Returns:
        End date, or None for ongoing medications.
    """
    if duration_days is None or duration_days <= 0:
        return None
    return start_date + timedelta(days=duration_days - 1)


# Words that anchor a dose to food. "food" was missing from the original list, so
# instructions like "after food" silently produced no meal relation at all.
_FOOD_WORDS = ("breakfast", "lunch", "dinner", "meal", "meals", "food", "eating")


def get_meal_relation(frequency: str, instructions: Optional[str] = None) -> Optional[str]:
    """
    Determine meal relation from the frequency and the free-text instructions.

    Reads instructions as well as frequency, because that is where the meal timing
    normally lives: a real prescription says frequency='twice daily',
    instructions='after food'. Reading only frequency loses it, and that is not
    cosmetic — metformin needs food, levothyroxine needs an empty stomach.

    Returns one of BEFORE_MEAL / AFTER_MEAL / WITH_MEAL / EMPTY_STOMACH, or None
    when the text says nothing about food. A dose described relative to two
    different meals collapses to one value; the column only holds one.
    """
    text = " ".join(part for part in (frequency, instructions) if part).strip().lower()

    if "empty stomach" in text:
        return "EMPTY_STOMACH"

    if not any(word in text for word in _FOOD_WORDS):
        return None

    if "before" in text:
        return "BEFORE_MEAL"
    if "after" in text:
        return "AFTER_MEAL"
    if "with" in text:
        return "WITH_MEAL"

    return None


class UnschedulableMedicationsError(ValueError):
    """
    Raised when at least one medication's frequency cannot become dose times.

    Carries every offending medication rather than just the first, so a clinician
    sees all of them at once instead of discovering them one failed request at a
    time. Callers should surface this as a client error and leave the prescription
    unverified — see UnknownFrequencyError for why guessing is not an option.
    """

    def __init__(self, unmapped: list[dict[str, str]]):
        self.unmapped = unmapped
        detail = ", ".join(
            f"{item['medicine_name']} ({item['frequency']!r})" for item in unmapped
        )
        super().__init__(f"Cannot derive dose times for: {detail}")


@dataclass(frozen=True)
class ScheduleGenerationResult:
    """Summary of what a generation run changed."""

    created: int = 0
    reactivated: int = 0
    #: Retired because the medication is no longer prescribed.
    cancelled: int = 0
    #: Retired because a newer schedule replaced this one.
    superseded: int = 0
    unchanged: int = 0
    # Medications intentionally left unscheduled because they are taken as needed.
    as_needed: list[str] = field(default_factory=list)

    @property
    def active_total(self) -> int:
        return self.created + self.reactivated + self.unchanged

    @property
    def deactivated(self) -> int:
        """
        Total rows retired by this run, cancelled and superseded together.

        A derived property rather than a field, so the two counts above cannot
        disagree with their own sum. It stays under this name because it is published:
        ``ScheduleGenerationResponse.deactivated`` is in ``openapi.json`` and generated
        into the Flutter client's models. Splitting the wire field would be a breaking
        contract change for a number no hand-written client code reads, so the internal
        vocabulary gets to be honest without the API moving.
        """
        return self.cancelled + self.superseded


async def generate_schedules(
    db: AsyncSession,
    prescription: "Prescription",
    start_date: date,
) -> ScheduleGenerationResult:
    """
    Create or refresh the MedicationSchedule rows for a verified prescription.

    Requires prescription.medications to be eagerly loaded.

    Four properties this deliberately guarantees:

    1. All-or-nothing. Every frequency is validated before a single row is written,
       so a prescription is never left half-scheduled.
    2. Idempotent. Re-verifying updates the matching row instead of inserting a
       duplicate, which uq_schedule_med_time_start would reject anyway.
    3. Non-destructive. Retired rows get a terminal status, never a delete. A schedule
       delete is refused by the database now (medication_events.schedule_id is
       RESTRICT), so this is enforced rather than merely intended.
    4. Discontinued medications are not scheduled, and any schedule they still
       have is retired. Without this, a correction that discontinues a medication
       would have its schedules recreated here on the very next line, and the
       reminder poller would keep dispatching doses the patient was taken off.

    Retirement records *why*, because the two reasons mean opposite things to whoever
    reads the history later:

    - CANCELLED — the medication itself is no longer prescribed. Doses after this point
      were not meant to be taken, so their absence is not non-adherence.
    - SUPERSEDED — a newer schedule replaced this one: a new course start date, or a
      corrected frequency that moved the dose times. The medication is still
      prescribed and the doses already logged here were taken correctly.

    Flushes but does not commit; the caller owns the transaction.

    Raises:
        UnschedulableMedicationsError: if any frequency cannot be mapped.
    """
    all_meds = list(prescription.medications)
    # Only currently-prescribed medications get dose times. Discontinued rows are
    # kept for their history (see prescription_service.reconcile_medications) and
    # must not be revived here.
    meds = [med for med in all_meds if med.is_active]

    # 1. Validate everything up front. Only active medications are validated: a
    #    discontinued line with an unreadable frequency is not being scheduled,
    #    so it must not block verification of the ones that are.
    unmapped: list[dict[str, str]] = []
    for med in meds:
        try:
            normalize_frequency(med.frequency)
        except UnknownFrequencyError:
            unmapped.append(
                {"medicine_name": med.medicine_name, "frequency": med.frequency}
            )
    if unmapped:
        raise UnschedulableMedicationsError(unmapped)

    # 2. Index existing rows by the natural key behind uq_schedule_med_time_start.
    #    Indexed across *all* medications, not just active ones, so that step 3
    #    can retire the schedules of a medication that has just been discontinued.
    existing: dict[tuple[int, time, date], MedicationSchedule] = {}
    # A medication added in this transaction has no primary key until the caller
    # flushes; skip those rather than putting NULL into the IN clause.
    med_ids = [med.id for med in all_meds if med.id is not None]
    if med_ids:
        rows = await db.execute(
            select(MedicationSchedule).where(
                MedicationSchedule.prescribed_medication_id.in_(med_ids)
            )
        )
        for sched in rows.scalars().all():
            key = (sched.prescribed_medication_id, sched.scheduled_time, sched.start_date)
            existing[key] = sched

    created = reactivated = unchanged = 0
    as_needed: list[str] = []
    wanted: set[tuple[int, time, date]] = set()

    for med in meds:
        slots = calculate_schedule_times(med.frequency)
        if not slots:
            # As-needed medication is dispensed on demand; scheduling it would
            # generate reminders for doses the patient is not meant to take.
            as_needed.append(med.medicine_name)
            continue

        end_date = calculate_end_date(start_date, med.duration_days)
        relation = get_meal_relation(med.frequency, med.instructions)

        for slot in slots:
            key = (med.id, slot, start_date)
            wanted.add(key)
            found = existing.get(key)
            if found is not None:
                found.end_date = end_date
                found.relation_to_meal = relation
                if found.status == ScheduleLifecycle.ACTIVE.value:
                    unchanged += 1
                else:
                    # This exact (medication, slot, course start) is prescribed again,
                    # so the row is revived rather than duplicated — whether it was
                    # CANCELLED by a discontinuation that has since been reversed, or
                    # SUPERSEDED by a frequency correction that has been corrected back.
                    found.status = ScheduleLifecycle.ACTIVE.value
                    reactivated += 1
            else:
                db.add(
                    MedicationSchedule(
                        prescribed_medication_id=med.id,
                        patient_id=med.patient_id,
                        scheduled_time=slot,
                        relation_to_meal=relation,
                        start_date=start_date,
                        end_date=end_date,
                        status=ScheduleLifecycle.ACTIVE.value,
                    )
                )
                created += 1

    # 3. Retire rows this run no longer wants, recording which of the two reasons
    #    applies. The medication's own is_active flag is what separates them: if the
    #    medication is gone the schedule was cancelled, and if the medication is still
    #    prescribed then some other schedule for it has taken over.
    discontinued_med_ids = {med.id for med in all_meds if not med.is_active}

    cancelled = superseded = 0
    for key, sched in existing.items():
        if key in wanted or sched.status != ScheduleLifecycle.ACTIVE.value:
            continue
        if sched.prescribed_medication_id in discontinued_med_ids:
            sched.status = ScheduleLifecycle.CANCELLED.value
            cancelled += 1
        else:
            sched.status = ScheduleLifecycle.SUPERSEDED.value
            superseded += 1

    await db.flush()
    return ScheduleGenerationResult(
        created=created,
        reactivated=reactivated,
        cancelled=cancelled,
        superseded=superseded,
        unchanged=unchanged,
        as_needed=as_needed,
    )


async def cancel_schedules(
    db: AsyncSession,
    prescription: "Prescription",
) -> int:
    """
    Mark every live schedule of a prescription CANCELLED.

    Used when a prescription is rejected: a rejected prescription must not keep firing
    reminders. CANCELLED and not SUPERSEDED, because nothing is replacing these doses —
    the decision was that they should not be taken.

    Sets a status rather than deleting, for the same adherence-history reason as
    generate_schedules; a delete would be refused by the database anyway.

    Returns the number of rows cancelled.
    """
    med_ids = [med.id for med in prescription.medications]
    if not med_ids:
        return 0

    rows = await db.execute(
        select(MedicationSchedule).where(
            MedicationSchedule.prescribed_medication_id.in_(med_ids),
            MedicationSchedule.status == ScheduleLifecycle.ACTIVE.value,
        )
    )
    schedules = rows.scalars().all()
    for sched in schedules:
        sched.status = ScheduleLifecycle.CANCELLED.value

    await db.flush()
    return len(schedules)

