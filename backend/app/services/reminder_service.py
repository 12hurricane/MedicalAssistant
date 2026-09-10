"""
Reminder Service

Deterministic service managing the lifecycle of medication reminders and dose adherence events.
Does NOT pre-generate weeks of future reminder rows. Reminders are created just-in-time
during the polling window, dispatched through notification providers, and tied to
MedicationEvent records upon patient confirmation or expiry.
"""

import logging
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.prescribed_medication import PrescribedMedication
from app.models.patient import Patient
from app.models.reminder import Reminder, ReminderStatus
from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.types import utcnow
from app.notifications.service import notification_service
from app.notifications.base import NotificationMessage
from app.services import schedule_service

logger = logging.getLogger(__name__)


def _get_patient_timezone(patient: Optional[Patient]) -> ZoneInfo:
    """Safely obtain the patient's timezone with UTC fallback."""
    return schedule_service.resolve_patient_timezone(patient)


async def create_due_reminders(
    db: AsyncSession,
    reference_time: Optional[datetime] = None,
    lookahead_minutes: int = 1,
    lookback_minutes: int = 120,
) -> List[Reminder]:
    """
    Find active medication schedules whose dose time is due and create Reminder rows just-in-time.
    
    Guarantees:
    1. Zero row explosion: only creates reminders for doses within the active polling window.
    2. Timezone correctness: evaluates scheduled_time against patient's local wall clock date.
    3. Idempotent: checks for existing (schedule_id, scheduled_for) rows before creating.
    """
    now_utc = reference_time or utcnow()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    # Fetch live schedules where the prescribed medication is also active. The date
    # window below completes the filter: a course that has run out is COMPLETED, which
    # is derived from end_date rather than stored, so status alone cannot exclude it.
    stmt = (
        select(MedicationSchedule)
        .join(PrescribedMedication, MedicationSchedule.prescribed_medication_id == PrescribedMedication.id)
        .join(Patient, MedicationSchedule.patient_id == Patient.id)
        .options(
            selectinload(MedicationSchedule.prescribed_medication),
            selectinload(MedicationSchedule.patient),
        )
        .where(
            MedicationSchedule.status == ScheduleLifecycle.ACTIVE.value,
            PrescribedMedication.is_active.is_(True),
        )
    )
    result = await db.execute(stmt)
    schedules = result.scalars().all()

    created_reminders: List[Reminder] = []

    for schedule in schedules:
        patient = schedule.patient
        tz = _get_patient_timezone(patient)

        # Patient's local date and time right now
        patient_local_now = now_utc.astimezone(tz)
        patient_today = patient_local_now.date()

        # Check schedule course date boundaries
        if schedule.start_date > patient_today:
            continue
        if schedule.end_date is not None and schedule.end_date < patient_today:
            continue

        # Combine patient's local date with schedule time to calculate the exact UTC instant
        dose_utc_dt = schedule_service.dose_instant_utc(
            schedule.scheduled_time, patient_today, tz
        )

        # Check if this dose falls within the due window
        is_due = (
            dose_utc_dt <= (now_utc + timedelta(minutes=lookahead_minutes))
            and dose_utc_dt >= (now_utc - timedelta(minutes=lookback_minutes))
        )

        if not is_due:
            continue

        # Idempotency check: see if a reminder already exists for this exact dose instant
        existing_stmt = select(Reminder).where(
            Reminder.schedule_id == schedule.id,
            Reminder.scheduled_for == dose_utc_dt,
        )
        existing = (await db.execute(existing_stmt)).scalars().first()

        if existing is None:
            reminder = Reminder(
                schedule_id=schedule.id,
                patient_id=schedule.patient_id,
                scheduled_for=dose_utc_dt,
                status=ReminderStatus.PENDING.value,
                channel="PUSH",
            )
            db.add(reminder)
            created_reminders.append(reminder)

    if created_reminders:
        await db.flush()

    return created_reminders


async def dispatch_pending_reminders(
    db: AsyncSession,
    reference_time: Optional[datetime] = None,
) -> List[Reminder]:
    """
    Dispatch due PENDING reminders through the notification abstraction.
    """
    now_utc = reference_time or utcnow()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    stmt = (
        select(Reminder)
        .options(
            selectinload(Reminder.schedule).selectinload(MedicationSchedule.prescribed_medication),
            selectinload(Reminder.patient).selectinload(Patient.user),
        )
        .where(
            Reminder.status == ReminderStatus.PENDING.value,
            Reminder.scheduled_for <= now_utc,
        )
    )
    result = await db.execute(stmt)
    pending_reminders = result.scalars().all()

    dispatched: List[Reminder] = []

    for reminder in pending_reminders:
        reminder.status = ReminderStatus.PROCESSING.value
        sched = reminder.schedule
        med = sched.prescribed_medication if sched else None
        patient = reminder.patient
        user = patient.user if patient else None

        medicine_name = med.medicine_name if med else "Scheduled Medication"
        dose = med.dose if med else None
        instructions = med.instructions if med else None
        relation_to_meal = sched.relation_to_meal if sched else None
        recipient_addr = user.phone or user.email if user else None

        msg = NotificationMessage(
            patient_id=reminder.patient_id,
            medicine_name=medicine_name,
            dose=dose,
            instructions=instructions,
            relation_to_meal=relation_to_meal,
            scheduled_for=reminder.scheduled_for,
            channel=reminder.channel,
            recipient_address=recipient_addr,
            reminder_id=reminder.id,
        )

        try:
            res = await notification_service.send(msg)
            if res.success:
                reminder.status = ReminderStatus.SENT.value
                reminder.sent_at = utcnow()
                dispatched.append(reminder)
            else:
                reminder.retry_count += 1
                reminder.status = (
                    ReminderStatus.FAILED.value if reminder.retry_count >= 3 else ReminderStatus.PENDING.value
                )
        except Exception as exc:
            logger.error(f"Error dispatching reminder #{reminder.id}: {exc}")
            reminder.retry_count += 1
            reminder.status = (
                ReminderStatus.FAILED.value if reminder.retry_count >= 3 else ReminderStatus.PENDING.value
            )

    if pending_reminders:
        await db.flush()

    return dispatched


async def process_expired_reminders(
    db: AsyncSession,
    grace_period_minutes: int = 120,
    reference_time: Optional[datetime] = None,
) -> List[Reminder]:
    """
    Mark unacknowledged SENT reminders as EXPIRED when grace period lapses,
    and create a MedicationEvent with MISSED status for adherence tracking.
    """
    now_utc = reference_time or utcnow()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    cutoff = now_utc - timedelta(minutes=grace_period_minutes)

    stmt = (
        select(Reminder)
        .options(selectinload(Reminder.event))
        .where(
            Reminder.status == ReminderStatus.SENT.value,
            Reminder.scheduled_for < cutoff,
        )
    )
    result = await db.execute(stmt)
    expired_reminders = result.scalars().all()

    processed: List[Reminder] = []

    for reminder in expired_reminders:
        reminder.status = ReminderStatus.EXPIRED.value

        # If no medication event exists for this reminder, record as MISSED
        if reminder.event is None:
            # Also double-check if an event for this schedule & scheduled_at already exists
            ev_stmt = select(MedicationEvent).where(
                MedicationEvent.schedule_id == reminder.schedule_id,
                MedicationEvent.scheduled_at == reminder.scheduled_for,
            )
            ev = (await db.execute(ev_stmt)).scalars().first()

            if ev is None:
                missed_event = MedicationEvent(
                    schedule_id=reminder.schedule_id,
                    patient_id=reminder.patient_id,
                    reminder_id=reminder.id,
                    scheduled_at=reminder.scheduled_for,
                    status=MedicationEventStatus.MISSED.value,
                    recorded_by="SYSTEM",
                )
                db.add(missed_event)
            elif ev.status == MedicationEventStatus.PENDING.value:
                ev.status = MedicationEventStatus.MISSED.value
                ev.reminder_id = reminder.id
        elif reminder.event.status == MedicationEventStatus.PENDING.value:
            reminder.event.status = MedicationEventStatus.MISSED.value

        processed.append(reminder)

    if expired_reminders:
        await db.flush()

    return processed


async def record_patient_response(
    db: AsyncSession,
    patient_id: int,
    schedule_id: int,
    action: str,
    reminder_id: Optional[int] = None,
    skip_reason: Optional[str] = None,
    skip_reason_code: Optional[str] = None,
    snooze_minutes: int = 30,
) -> MedicationEvent:
    """
    Record patient response (TAKEN, SKIPPED, SNOOZED) to a dose.
    
    Authoritatively determines scheduled_at from the MedicationSchedule or Reminder.
    Never trusts a client-supplied scheduled timestamp.
    """
    normalized_action = action.upper()
    if normalized_action not in [
        MedicationEventStatus.TAKEN.value,
        MedicationEventStatus.SKIPPED.value,
        MedicationEventStatus.MISSED.value,
        MedicationEventStatus.SNOOZED.value,
    ]:
        raise ValueError(f"Invalid medication event action: {action}")

    now = utcnow()
    reminder: Optional[Reminder] = None
    target_scheduled_at: Optional[datetime] = None

    if reminder_id is not None:
        reminder = await db.get(Reminder, reminder_id)
        if reminder is None or reminder.patient_id != patient_id:
            raise ValueError(f"Reminder #{reminder_id} not found for patient #{patient_id}")
        target_scheduled_at = reminder.scheduled_for
    else:
        # Self-logged: authoritatively derive scheduled_at from schedule & patient timezone
        sched_stmt = (
            select(MedicationSchedule)
            .options(selectinload(MedicationSchedule.patient))
            .where(
                MedicationSchedule.id == schedule_id,
                MedicationSchedule.patient_id == patient_id,
            )
        )
        schedule = (await db.execute(sched_stmt)).scalars().first()
        if schedule is None:
            raise ValueError(f"Schedule #{schedule_id} not found for patient #{patient_id}")

        patient = schedule.patient
        tz = _get_patient_timezone(patient)
        patient_local_now = now.astimezone(tz)
        patient_today = patient_local_now.date()

        target_scheduled_at = schedule_service.dose_instant_utc(
            schedule.scheduled_time, patient_today, tz
        )

        # Check if an existing reminder exists for this slot
        rem_stmt = select(Reminder).where(
            Reminder.schedule_id == schedule_id,
            Reminder.scheduled_for == target_scheduled_at,
        )
        reminder = (await db.execute(rem_stmt)).scalars().first()
        if reminder:
            reminder_id = reminder.id

    # Find or create MedicationEvent for this exact scheduled dose
    stmt = select(MedicationEvent).where(
        MedicationEvent.schedule_id == schedule_id,
        MedicationEvent.scheduled_at == target_scheduled_at,
    )
    event = (await db.execute(stmt)).scalars().first()

    if event is None:
        event = MedicationEvent(
            schedule_id=schedule_id,
            patient_id=patient_id,
            reminder_id=reminder_id,
            scheduled_at=target_scheduled_at,
            status=normalized_action,
            confirmed_at=now if normalized_action in [MedicationEventStatus.TAKEN.value, MedicationEventStatus.SKIPPED.value] else None,
            recorded_by="PATIENT",
            skip_reason_code=skip_reason_code,
            skip_reason=skip_reason,
        )
        db.add(event)
    else:
        event.status = normalized_action
        if reminder_id:
            event.reminder_id = reminder_id
        if normalized_action in [MedicationEventStatus.TAKEN.value, MedicationEventStatus.SKIPPED.value]:
            event.confirmed_at = now
        if skip_reason_code:
            event.skip_reason_code = skip_reason_code
        if skip_reason:
            event.skip_reason = skip_reason

    # Handle Reminder lifecycle transitions
    if reminder is not None:
        if normalized_action in [MedicationEventStatus.TAKEN.value, MedicationEventStatus.SKIPPED.value]:
            reminder.status = ReminderStatus.ACKNOWLEDGED.value
        elif normalized_action == MedicationEventStatus.SNOOZED.value:
            snooze_until = now + timedelta(minutes=snooze_minutes)
            event.snooze_until = snooze_until
            reminder.status = ReminderStatus.PENDING.value
            reminder.scheduled_for = snooze_until

    await db.flush()
    return event



async def poll_and_process_reminders(
    db: AsyncSession,
    reference_time: Optional[datetime] = None,
    grace_period_minutes: int = 120,
) -> dict:
    """
    Main polling orchestration step executed every 60 seconds:
    1. Create due reminders just-in-time
    2. Dispatch pending reminders via notification providers
    3. Expire overdue unacknowledged reminders and mark missed events
    """
    created = await create_due_reminders(db, reference_time=reference_time)
    dispatched = await dispatch_pending_reminders(db, reference_time=reference_time)
    expired = await process_expired_reminders(db, grace_period_minutes=grace_period_minutes, reference_time=reference_time)

    return {
        "created_count": len(created),
        "dispatched_count": len(dispatched),
        "expired_count": len(expired),
    }
