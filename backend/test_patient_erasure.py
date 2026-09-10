import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, time, timezone

from app.models.patient import Patient
from app.models.user import User
from app.models.prescription import Prescription
from app.models.prescribed_medication import PrescribedMedication
from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.medication_event import MedicationEvent, MedicationEventStatus

async def _seed_hierarchy(session):
    user = User(
        name="Test Patient",
        email="cascade@example.com",
        hashed_password="xxx",
        role="PATIENT"
    )
    session.add(user)
    await session.commit()
    
    patient = Patient(user_id=user.id)
    session.add(patient)
    await session.commit()

    prescription = Prescription(
        patient_id=patient.id,
        prescription_date=date(2026, 1, 1)
    )
    session.add(prescription)
    await session.commit()

    pm = PrescribedMedication(
        prescription_id=prescription.id,
        patient_id=patient.id,
        medicine_name="Test Med",
        frequency="Daily"
    )
    session.add(pm)
    await session.commit()

    schedule = MedicationSchedule(
        prescribed_medication_id=pm.id,
        patient_id=patient.id,
        scheduled_time=time(9, 0),
        start_date=date(2026, 1, 1),
        status=ScheduleLifecycle.ACTIVE.value
    )
    session.add(schedule)
    await session.commit()

    event = MedicationEvent(
        schedule_id=schedule.id,
        patient_id=patient.id,
        scheduled_at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        status=MedicationEventStatus.TAKEN.value
    )
    session.add(event)
    await session.commit()

    return patient.id, schedule.id, pm.id

from app.services.patient_service import patient_service
from app.models.consent import ConsentRecord

@pytest.mark.asyncio
async def test_patient_erasure_deletes_history_but_retains_consent(session):
    """
    DATA-1 Verification: Patient erasure should explicitly delete the dependency tree
    bottom-up to satisfy the HIST-1 RESTRICT constraint, and retain consent records
    unlinked from the patient.
    """
    patient_id, schedule_id, pm_id = await _seed_hierarchy(session)
    
    # Add a consent record to verify it gets retained
    consent = ConsentRecord(patient_id=patient_id, consent_type="TERMS")
    session.add(consent)
    await session.commit()
    consent_id = consent.id

    # Erase the patient deterministically
    await patient_service.delete_patient_and_history(session, patient_id)

    # Verify patient, user, and history are gone
    assert await session.get(Patient, patient_id) is None
    assert await session.get(MedicationSchedule, schedule_id) is None
    assert await session.get(MedicationEvent, 1) is None

    # Verify consent record remains but is detached
    retained_consent = await session.get(ConsentRecord, consent_id)
    assert retained_consent is not None
    assert retained_consent.patient_id is None

@pytest.mark.asyncio
async def test_schedule_deletion_is_restricted_by_history(session):
    """
    HIST-1 Verification: Deleting a schedule directly MUST be blocked by RESTRICT
    if it has events.
    """
    patient_id, schedule_id, pm_id = await _seed_hierarchy(session)

    schedule = await session.get(MedicationSchedule, schedule_id)
    await session.delete(schedule)
    
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed|RESTRICT"):
        await session.commit()
    
    await session.rollback()

@pytest.mark.asyncio
async def test_prescribed_medication_deletion_is_restricted_by_history(session):
    """
    HIST-1 Verification: Deleting a prescribed medication cascades to schedules,
    which then hits the RESTRICT from events.
    """
    patient_id, schedule_id, pm_id = await _seed_hierarchy(session)

    pm = await session.get(PrescribedMedication, pm_id)
    await session.delete(pm)
    
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed|RESTRICT"):
        await session.commit()
    
    await session.rollback()
