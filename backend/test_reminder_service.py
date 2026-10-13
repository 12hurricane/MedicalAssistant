import pytest
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.prescribed_medication import PrescribedMedication
from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.reminder import Reminder, ReminderStatus
from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.services.reminder_service import (
    create_due_reminders,
    dispatch_pending_reminders,
    process_expired_reminders,
    record_patient_response,
)
from app.notifications.service import notification_service
from app.notifications.base import NotificationResult

# Helper to create state
async def setup_patient_schedule(session: AsyncSession, tz_str: str = "UTC"):
    user = User(
        name="Reminder Test User",
        email="remind@example.com",
        hashed_password="hash",
        role="PATIENT",
        phone="+123456789"
    )
    patient = Patient(timezone=tz_str)
    user.patient = patient
    session.add(user)
    await session.flush()

    prescription = Prescription(patient_id=patient.id, prescription_date=date(2026, 1, 1))
    session.add(prescription)
    await session.flush()

    medication = PrescribedMedication(
        prescription_id=prescription.id,
        patient_id=patient.id,
        medicine_name="Test Med",
        frequency="ONCE_DAILY",
        is_active=True
    )
    session.add(medication)
    await session.flush()

    schedule = MedicationSchedule(
        prescribed_medication_id=medication.id,
        patient_id=patient.id,
        start_date=date(2026, 1, 1),
        scheduled_time=time(9, 0),
        status=ScheduleLifecycle.ACTIVE.value
    )
    session.add(schedule)
    await session.flush()

    return patient, schedule

@pytest.mark.asyncio
async def test_create_due_reminders(session: AsyncSession):
    patient, schedule = await setup_patient_schedule(session)
    
    # Fake UTC time that exactly matches 9:00 AM UTC on 2026-01-10
    ref_time = datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc)
    
    created = await create_due_reminders(session, reference_time=ref_time)
    
    assert len(created) == 1
    reminder = created[0]
    assert reminder.schedule_id == schedule.id
    assert reminder.patient_id == patient.id
    assert reminder.status == ReminderStatus.PENDING.value
    
    # Test idempotency
    created_again = await create_due_reminders(session, reference_time=ref_time)
    assert len(created_again) == 0

@pytest.mark.asyncio
async def test_create_due_reminders_out_of_window(session: AsyncSession):
    patient, schedule = await setup_patient_schedule(session)
    
    # 6:00 AM UTC, dose is at 9:00 AM UTC, outside lookahead
    ref_time = datetime(2026, 1, 10, 6, 0, tzinfo=timezone.utc)
    
    created = await create_due_reminders(session, reference_time=ref_time)
    assert len(created) == 0

@pytest.mark.asyncio
async def test_dispatch_pending_reminders(session: AsyncSession, monkeypatch):
    patient, schedule = await setup_patient_schedule(session)
    
    # Create a pending reminder manually
    reminder = Reminder(
        schedule_id=schedule.id,
        patient_id=patient.id,
        scheduled_for=datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc),
        status=ReminderStatus.PENDING.value,
        channel="PUSH"
    )
    session.add(reminder)
    await session.flush()
    
    # Mock the notification service
    async def mock_send(msg):
        return NotificationResult(success=True, channel="PUSH")
    monkeypatch.setattr(notification_service, "send", mock_send)
    
    # Dispatch
    ref_time = datetime(2026, 1, 10, 9, 5, tzinfo=timezone.utc)
    dispatched = await dispatch_pending_reminders(session, reference_time=ref_time)
    
    assert len(dispatched) == 1
    assert dispatched[0].id == reminder.id
    assert dispatched[0].status == ReminderStatus.SENT.value

@pytest.mark.asyncio
async def test_process_expired_reminders(session: AsyncSession):
    patient, schedule = await setup_patient_schedule(session)
    
    # Sent reminder far in the past
    reminder = Reminder(
        schedule_id=schedule.id,
        patient_id=patient.id,
        scheduled_for=datetime(2026, 1, 10, 9, 0, tzinfo=timezone.utc),
        status=ReminderStatus.SENT.value,
        channel="PUSH"
    )
    session.add(reminder)
    await session.flush()
    
    # Expire
    # 4 hours later, grace period is 120 mins
    ref_time = datetime(2026, 1, 10, 13, 0, tzinfo=timezone.utc)
    expired = await process_expired_reminders(session, reference_time=ref_time)
    
    assert len(expired) == 1
    assert expired[0].id == reminder.id
    assert expired[0].status == ReminderStatus.EXPIRED.value
    
    # Check if MedicationEvent was created
    stmt = select(MedicationEvent).where(MedicationEvent.reminder_id == reminder.id)
    event = (await session.execute(stmt)).scalars().first()
    assert event is not None
    assert event.status == MedicationEventStatus.MISSED.value

@pytest.mark.asyncio
async def test_record_patient_response_taken(session: AsyncSession):
    patient, schedule = await setup_patient_schedule(session)
    
    # Respond TAKEN
    event = await record_patient_response(
        session,
        patient_id=patient.id,
        schedule_id=schedule.id,
        action=MedicationEventStatus.TAKEN.value
    )
    
    assert event.status == MedicationEventStatus.TAKEN.value
    assert event.patient_id == patient.id
    assert event.schedule_id == schedule.id
    assert event.recorded_by == "PATIENT"
    assert event.confirmed_at is not None
