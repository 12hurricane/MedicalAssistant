"""
DST-sensitive timezone tests for authoritative dose-time derivation.

Dose times are stored as a local wall-clock ``time`` plus the patient's IANA zone,
and turned into a UTC instant at the moment a dose is recorded or a reminder is
built. The invariant that matters clinically: a dose prescribed for 08:00 local
stays at 08:00 local all year. The UTC instant behind it therefore has to move
when the zone's offset moves.

``Asia/Karachi`` cannot demonstrate any of this. Pakistan has not observed DST
since 2009, so its offset is a flat +05:00 and a test using it passes identically
whether the code resolves the offset per-date or hard-codes one. ``America/New_York``
is used here for the real assertions, with Karachi kept as an explicit control arm
so the difference is visible rather than assumed.

The derivation under test lives in ``reminder_service`` and is always anchored to
the patient's *today*, so reaching a transition means controlling the clock:
``utcnow`` is patched at module level, which is where the service reads it.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.patient import Patient
from app.models.prescribed_medication import PrescribedMedication
from app.models.prescription import Prescription
from app.models.user import User
from app.services import reminder_service

NEW_YORK = "America/New_York"
KARACHI = "Asia/Karachi"

# US DST in 2026 begins on Sunday 8 March (02:00 EST -> 03:00 EDT). These two dates
# straddle it, and noon UTC lands on the intended local calendar day in both zones.
BEFORE_DST = datetime(2026, 3, 6, 12, 0, tzinfo=timezone.utc)
AFTER_DST = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
SPRING_FORWARD = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)


async def _seed(session, tz_name: str, dose_time: time = time(8, 0)):
    """A patient in ``tz_name`` with one active schedule at ``dose_time`` local."""
    user = User(
        name=f"DST {tz_name}",
        email=f"dst_{tz_name.replace('/', '_')}@example.com",
        # Never logged in through, so the real hash is skipped: bcrypt is slow and
        # would dominate the runtime of a test that only does datetime arithmetic.
        hashed_password="not-a-real-hash",
        role="PATIENT",
    )
    user.patient = Patient(timezone=tz_name)
    session.add(user)
    await session.flush()

    presc = Prescription(
        patient_id=user.patient.id,
        prescription_date=date(2026, 3, 1),
        verification_status="VERIFIED",
    )
    session.add(presc)
    await session.flush()

    med = PrescribedMedication(
        prescription_id=presc.id,
        patient_id=user.patient.id,
        medicine_name="Metformin",
        frequency="once daily",
        is_active=True,
    )
    session.add(med)
    await session.flush()

    sched = MedicationSchedule(
        prescribed_medication_id=med.id,
        patient_id=user.patient.id,
        scheduled_time=dose_time,
        start_date=date(2026, 3, 1),
        status=ScheduleLifecycle.ACTIVE.value,
    )
    session.add(sched)
    await session.commit()
    return user.patient.id, sched.id


async def _record_at(session, monkeypatch, patient_id, schedule_id, frozen_now):
    """Log a dose with the service's clock frozen, and return the derived instant."""
    monkeypatch.setattr(reminder_service, "utcnow", lambda: frozen_now)
    event = await reminder_service.record_patient_response(
        db=session, patient_id=patient_id, schedule_id=schedule_id, action="TAKEN"
    )
    await session.commit()
    return event.scheduled_at


async def test_local_dose_time_holds_across_a_dst_transition(session, monkeypatch):
    """
    An 08:00 local dose stays at 08:00 local either side of spring-forward, which
    means its UTC instant shifts by exactly one hour.

    If the offset were resolved once and reused, both doses would land on the same
    UTC instant and one of them would be an hour wrong in local terms — an 8am
    metformin reminder arriving at 7am or 9am, every day, for half the year.
    """
    patient_id, schedule_id = await _seed(session, NEW_YORK)

    before = await _record_at(session, monkeypatch, patient_id, schedule_id, BEFORE_DST)
    after = await _record_at(session, monkeypatch, patient_id, schedule_id, AFTER_DST)

    # EST is UTC-5, EDT is UTC-4.
    assert before == datetime(2026, 3, 6, 13, 0, tzinfo=timezone.utc), before
    assert after == datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc), after

    tz = ZoneInfo(NEW_YORK)
    assert before.astimezone(tz).time() == time(8, 0)
    assert after.astimezone(tz).time() == time(8, 0), (
        "the dose drifted off 08:00 local after the DST change"
    )

    # Same wall-clock time, one hour apart in absolute terms.
    assert (after - before) == timedelta(days=4) - timedelta(hours=1)


async def test_a_non_dst_zone_cannot_expose_the_bug(session, monkeypatch):
    """
    The control arm. Karachi's offset is a flat +05:00, so the identical scenario
    produces the identical UTC time-of-day on both dates.

    This test is not here because the behaviour is interesting — it is here to
    record that a suite using only Asia/Karachi would pass just as happily against
    code that resolved the offset once and hard-coded it.
    """
    patient_id, schedule_id = await _seed(session, KARACHI)

    before = await _record_at(session, monkeypatch, patient_id, schedule_id, BEFORE_DST)
    after = await _record_at(session, monkeypatch, patient_id, schedule_id, AFTER_DST)

    assert before == datetime(2026, 3, 6, 3, 0, tzinfo=timezone.utc), before
    assert after == datetime(2026, 3, 10, 3, 0, tzinfo=timezone.utc), after
    assert before.time() == after.time(), (
        "Karachi is expected to be offset-stable; if this ever fails the control "
        "arm is no longer a control"
    )


async def test_dose_at_a_nonexistent_local_time_resolves_forward(session, monkeypatch):
    """
    Documents what happens to a dose scheduled inside the spring-forward gap.

    On 8 March 2026 the New York wall clock jumps 02:00 -> 03:00, so 02:30 local
    never occurs. Python resolves such a time with ``fold=0``, i.e. as though the
    pre-transition offset still applied, which lands the dose at 03:30 local — an
    hour later than written, on that one day.

    This asserts the actual behaviour rather than a preference, so that if it is
    ever changed deliberately the change is visible here. It is recorded because a
    23-hour day is exactly where a dose can be silently dropped or doubled, and any
    future interval-based scheduling has to reckon with it.
    """
    patient_id, schedule_id = await _seed(session, NEW_YORK, dose_time=time(2, 30))

    derived = await _record_at(
        session, monkeypatch, patient_id, schedule_id, SPRING_FORWARD
    )

    assert derived == datetime(2026, 3, 8, 7, 30, tzinfo=timezone.utc), derived
    local = derived.astimezone(ZoneInfo(NEW_YORK))
    assert local.time() == time(3, 30), (
        "expected the nonexistent 02:30 to resolve forward to 03:30 local"
    )


@pytest.mark.parametrize("tz_name", [NEW_YORK, KARACHI, "UTC"])
async def test_derived_instant_is_always_timezone_aware_utc(
    session, monkeypatch, tz_name
):
    """
    Whatever the zone, the stored instant is aware UTC.

    UTCDateTime rejects naive values on write, so a naive derivation would surface
    as an error rather than a wrong number — but only if something actually
    exercises the zone, which is what this parametrisation does.
    """
    patient_id, schedule_id = await _seed(session, tz_name)
    derived = await _record_at(
        session, monkeypatch, patient_id, schedule_id, BEFORE_DST
    )

    assert derived.tzinfo is not None
    assert derived.utcoffset() == timedelta(0)
