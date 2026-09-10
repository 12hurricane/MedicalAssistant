"""
Authoritative dose logging and adherence metrics.

Converted from a standalone ``asyncio.run`` script into real pytest tests. The
original opened ``AsyncSessionLocal`` directly, so once pytest was configured it
was collected and run against ``medication.db``, growing the real ``prescriptions``
table on every invocation while reporting a pass. It now runs on the per-test
throwaway database like everything else; ``conftest.forbid_production_database``
enforces that.

Two behaviours are covered:

1. ``scheduled_at`` is derived from the schedule and the patient's timezone, never
   taken from the client. A client-supplied dose time would let a patient log a
   missed dose as taken by backdating it, which is the one field adherence
   reporting cannot afford to have wrong.
2. The adherence calculation, its per-slot breakdown, pattern detection and
   escalation trigger, over a seeded 7-day history with a deliberate evening
   breakdown.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import (
    MedicationEvent,
    MedicationEventStatus,
    MedicationSchedule,
    Patient,
    PrescribedMedication,
    Prescription,
    User,
)
from app.services import adherence_service, reminder_service, schedule_service

TZ_NAME = "Asia/Kolkata"


@pytest.fixture
async def pipeline(session):
    """
    A verified twice-daily prescription with its 08:00 and 20:00 schedules.

    ``start_date`` is six days back so a 7-day lookback covers the whole seeded
    history rather than clipping it.
    """
    user = User(
        name="Adherence Test Patient",
        email="adh_metrics_test@example.com",
        # No login happens in these tests, so the bcrypt round trip is skipped.
        hashed_password="not-a-real-hash",
        role="PATIENT",
    )
    user.patient = Patient(
        date_of_birth=date(1985, 3, 20), preferred_language="en", timezone=TZ_NAME
    )
    session.add(user)
    await session.flush()
    patient = user.patient

    presc = Prescription(
        patient_id=patient.id,
        doctor_name="Dr. Adams",
        clinic_name="Metro Health",
        prescription_date=date.today() - timedelta(days=10),
        verification_status="VERIFIED",
    )
    session.add(presc)
    await session.flush()

    session.add(
        PrescribedMedication(
            prescription_id=presc.id,
            patient_id=patient.id,
            medicine_name="Metformin 500mg",
            dose="1 tab",
            frequency="twice daily",  # 08:00 and 20:00
            duration_days=14,
            instructions="with food",
            is_active=True,
        )
    )
    await session.commit()

    loaded = (
        await session.execute(
            select(Prescription)
            .options(selectinload(Prescription.medications))
            .where(Prescription.id == presc.id)
        )
    ).scalars().first()
    await schedule_service.generate_schedules(
        session, loaded, start_date=date.today() - timedelta(days=6)
    )
    await session.commit()

    schedules = (
        await session.execute(
            select(MedicationSchedule)
            .where(MedicationSchedule.patient_id == patient.id)
            .order_by(MedicationSchedule.scheduled_time.asc())
        )
    ).scalars().all()
    assert len(schedules) == 2, [s.scheduled_time for s in schedules]

    return {
        "patient_id": patient.id,
        "morning": schedules[0],  # 08:00
        "evening": schedules[1],  # 20:00
        "tz": ZoneInfo(TZ_NAME),
    }


async def _log_todays_morning_dose(session, pipeline):
    """Patient logs the morning dose supplying no timestamp of any kind."""
    event = await reminder_service.record_patient_response(
        db=session,
        patient_id=pipeline["patient_id"],
        schedule_id=pipeline["morning"].id,
        action="TAKEN",
    )
    await session.commit()
    return event


async def test_scheduled_at_is_derived_from_the_schedule_not_the_client(
    session, pipeline
):
    """
    The recorded dose time is reconstructed from the schedule's local time and the
    patient's zone, with zero client input.
    """
    event = await _log_todays_morning_dose(session, pipeline)

    tz = pipeline["tz"]
    expected = datetime.combine(
        datetime.now(tz).date(), time(8, 0), tzinfo=tz
    ).astimezone(timezone.utc)

    assert event.scheduled_at == expected, (
        f"expected the 08:00 local slot resolved to {expected}, got {event.scheduled_at}"
    )
    assert event.status == MedicationEventStatus.TAKEN.value


async def test_adherence_metrics_slot_breakdown_and_escalation(session, pipeline):
    """
    Six days of twice-daily doses with the evenings deliberately failing.

    Mornings: 6/6 taken. Evenings: 2 taken, 4 missed. Plus today's morning dose
    logged through the service, for 13 recorded doses in the 7-day window. The
    evening collapse is the signal the escalation logic exists to catch.
    """
    await _log_todays_morning_dose(session, pipeline)

    tz = pipeline["tz"]
    morning, evening = pipeline["morning"], pipeline["evening"]
    patient_id = pipeline["patient_id"]

    for i in range(6):
        day = datetime.now(tz).date() - timedelta(days=6 - i)

        dt_morn = datetime.combine(day, time(8, 0), tzinfo=tz).astimezone(timezone.utc)
        session.add(
            MedicationEvent(
                schedule_id=morning.id,
                patient_id=patient_id,
                scheduled_at=dt_morn,
                status=MedicationEventStatus.TAKEN.value,
                confirmed_at=dt_morn,
                recorded_by="PATIENT",
            )
        )

        dt_eve = datetime.combine(day, time(20, 0), tzinfo=tz).astimezone(timezone.utc)
        taken = i < 2
        session.add(
            MedicationEvent(
                schedule_id=evening.id,
                patient_id=patient_id,
                scheduled_at=dt_eve,
                status=(
                    MedicationEventStatus.TAKEN.value
                    if taken
                    else MedicationEventStatus.MISSED.value
                ),
                confirmed_at=dt_eve if taken else None,
                recorded_by="PATIENT" if taken else "SYSTEM",
            )
        )

    await session.commit()

    metrics = await adherence_service.calculate_adherence_score(
        session=session, patient_id=patient_id, days=7
    )

    assert metrics.expected_doses == 13, metrics.expected_doses
    assert metrics.total_missed == 4, metrics.total_missed
    assert metrics.time_slot_breakdown["morning"].adherence_rate == 100.0
    assert metrics.time_slot_breakdown["evening"].adherence_rate < 50.0

    assert any("evening" in pattern.lower() for pattern in metrics.detected_patterns), (
        f"no pattern identified the evening misses: {metrics.detected_patterns}"
    )
    assert metrics.should_escalate is True, (
        f"evening breakdown should escalate; reasons were {metrics.escalation_reasons}"
    )
