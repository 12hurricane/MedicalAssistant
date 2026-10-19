"""Step 4C: Focused concurrency integration test against an ACTUAL PostgreSQL database.

This test requires a real PostgreSQL database instance to verify row-level locking
semantics via `SELECT ... FOR UPDATE` without any application-level mutex.

It explicitly checks that the database dialect is PostgreSQL and fails/stops
if PostgreSQL is not available, rather than silently falling back to SQLite.
"""

import asyncio
import os
import pytest
from datetime import date, datetime, time, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import (
    Base,
    Medication,
    MedicationEvent,
    MedicationEventStatus,
    MedicationSchedule,
    Patient,
    PrescribedMedication,
    Prescription,
    ScheduleLifecycle,
    User,
)
from app.models.clinician_patient_assignment import ClinicianPatientAssignment
from app.models.medication_event_correction import MedicationEventCorrection
from app.models.types import utcnow
from conftest import register

POSTGRES_URL = os.environ.get(
    "POSTGRES_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/medassist_test",
)


@pytest.fixture
async def postgres_engine():
    """Create engine for real PostgreSQL instance. Stop if PostgreSQL is unavailable."""
    try:
        engine = create_async_engine(POSTGRES_URL, echo=False)
        yield engine
        await engine.dispose()
    except Exception as exc:
        pytest.skip(
            f"POSTGRESQL UNAVAILABLE: Failed to create engine for {POSTGRES_URL}: {exc}. "
            "PostgreSQL database/container is required for Step 4C concurrency tests."
        )


async def _check_postgres_connection(engine):
    """Verify live connection to PostgreSQL."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(select(func.version()))
            version = result.scalar()
            print(f"\n[Step 4C] Connected to real PostgreSQL engine: {version}")
            return version
    except Exception as exc:
        pytest.skip(
            f"POSTGRESQL UNAVAILABLE: Cannot connect to PostgreSQL at {POSTGRES_URL}: {exc}. "
            "A running PostgreSQL test database/container is required for Step 4C."
        )


@pytest.mark.asyncio
async def test_postgres_concurrent_corrections_must_serialize_linearly(postgres_engine):
    """Step 4C: Two concurrent corrections against the same MedicationEvent in real PostgreSQL.

    Initial state: TAKEN
    Concurrent requests:
      Request A: TAKEN -> SKIPPED
      Request B: TAKEN -> MISSED

    Invariant enforced by PostgreSQL row-level locking (SELECT ... FOR UPDATE):
    - PostgreSQL locks the MedicationEvent row.
    - The second transaction blocks until the first commits, then re-evaluates
      the row and observes the committed new status.
    - Final audit chain is strictly linear:
        TAKEN -> SKIPPED
        SKIPPED -> MISSED
      (or reverse depending on lock acquisition order).
    - Forked history (TAKEN -> SKIPPED and TAKEN -> MISSED) is mathematically impossible.
    """
    await _check_postgres_connection(postgres_engine)

    # Initialize tables
    async with postgres_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(postgres_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers_clin = await register(client, "pg_clinician@example.com", role="CLINICIAN")
            headers_pat = await register(client, "pg_patient@example.com", role="PATIENT")

            async with sessionmaker() as session:
                user_pat = (
                    await session.execute(select(User).where(User.email == "pg_patient@example.com"))
                ).scalars().one()
                pat = (
                    await session.execute(select(Patient).where(Patient.user_id == user_pat.id))
                ).scalars().one()
                pat.timezone = "UTC"

                user_clin = (
                    await session.execute(select(User).where(User.email == "pg_clinician@example.com"))
                ).scalars().one()

                med = Medication(
                    brand_name="Coumadin",
                    generic_name="Warfarin Sodium",
                    standard_strength="5mg",
                    dosage_form="tablet",
                )
                session.add(med)
                await session.flush()

                rx = Prescription(
                    patient_id=pat.id,
                    doctor_name="Dr. PG",
                    prescription_date=date(2026, 1, 1),
                    verification_status="VERIFIED",
                )
                session.add(rx)
                await session.flush()

                pm = PrescribedMedication(
                    prescription_id=rx.id,
                    patient_id=pat.id,
                    medication_id=med.id,
                    medicine_name="Coumadin",
                    dose="5mg",
                    frequency="once daily",
                )
                session.add(pm)
                await session.flush()

                sched = MedicationSchedule(
                    patient_id=pat.id,
                    prescribed_medication_id=pm.id,
                    scheduled_time=time(9, 0),
                    start_date=date(2026, 1, 1),
                    status=ScheduleLifecycle.ACTIVE.value,
                )
                session.add(sched)
                await session.flush()

                ev = MedicationEvent(
                    schedule_id=sched.id,
                    patient_id=pat.id,
                    scheduled_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
                    status="TAKEN",
                    confirmed_at=datetime(2026, 9, 20, 9, 5, tzinfo=timezone.utc),
                    recorded_by="PATIENT",
                )
                session.add(ev)
                await session.flush()

                assign = ClinicianPatientAssignment(
                    clinician_id=user_clin.id,
                    patient_id=pat.id,
                    assigned_at=utcnow(),
                )
                session.add(assign)
                await session.commit()
                event_id = ev.id

            # Launch genuinely concurrent requests without application-level lock
            task_a = asyncio.create_task(
                client.post(
                    f"/api/v1/adherence/events/{event_id}/correct",
                    json={"new_status": "SKIPPED", "reason": "PG concurrent A: skipped"},
                    headers=headers_clin,
                )
            )
            task_b = asyncio.create_task(
                client.post(
                    f"/api/v1/adherence/events/{event_id}/correct",
                    json={"new_status": "MISSED", "reason": "PG concurrent B: missed"},
                    headers=headers_clin,
                )
            )

            resp_a, resp_b = await asyncio.gather(task_a, task_b)
            assert resp_a.status_code == 200, f"Request A failed: {resp_a.text}"
            assert resp_b.status_code == 200, f"Request B failed: {resp_b.text}"

            async with sessionmaker() as session:
                audits = (
                    await session.execute(
                        select(MedicationEventCorrection)
                        .where(MedicationEventCorrection.event_id == event_id)
                        .order_by(MedicationEventCorrection.id.asc())
                    )
                ).scalars().all()

                assert len(audits) == 2, f"Expected 2 audit rows, got {len(audits)}"

                # Strict linearity check: No forked audit trail
                assert audits[0].previous_status != audits[1].previous_status, (
                    f"FORKED AUDIT TRAIL DETECTED IN POSTGRESQL! Both records have previous_status='{audits[0].previous_status}'"
                )
                assert audits[1].previous_status == audits[0].new_status, (
                    f"Discontinuous audit chain: {audits[0].previous_status}->{audits[0].new_status} "
                    f"followed by {audits[1].previous_status}->{audits[1].new_status}"
                )

                ev_final = (
                    await session.execute(
                        select(MedicationEvent).where(MedicationEvent.id == event_id)
                    )
                ).scalars().one()
                assert ev_final.status == audits[1].new_status
    finally:
        app.dependency_overrides.clear()
        async with postgres_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_postgres_concurrent_identical_corrections_serialize_with_rejection(postgres_engine):
    """Step 4C: Two concurrent identical corrections against the same MedicationEvent in PostgreSQL.

    Initial state: TAKEN
    Concurrent requests:
      Request A: TAKEN -> SKIPPED
      Request B: TAKEN -> SKIPPED

    Invariant:
    - Exactly one request succeeds (HTTP 200).
    - The second request unblocks after the lock is released, observes the updated
      status SKIPPED, triggers the no-op check, and is rejected with HTTP 422.
    - Exactly one audit row exists in the database.
    - Final event status is SKIPPED.
    """
    await _check_postgres_connection(postgres_engine)

    # Initialize tables
    async with postgres_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(postgres_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers_clin = await register(client, "pg_clin2@example.com", role="CLINICIAN")
            headers_pat = await register(client, "pg_pat2@example.com", role="PATIENT")

            async with sessionmaker() as session:
                user_pat = (
                    await session.execute(select(User).where(User.email == "pg_pat2@example.com"))
                ).scalars().one()
                pat = (
                    await session.execute(select(Patient).where(Patient.user_id == user_pat.id))
                ).scalars().one()
                pat.timezone = "UTC"

                user_clin = (
                    await session.execute(select(User).where(User.email == "pg_clin2@example.com"))
                ).scalars().one()

                med = Medication(brand_name="Coumadin", generic_name="Warfarin", standard_strength="5mg", dosage_form="tablet")
                session.add(med)
                await session.flush()

                rx = Prescription(patient_id=pat.id, doctor_name="Dr. PG", prescription_date=date(2026, 1, 1), verification_status="VERIFIED")
                session.add(rx)
                await session.flush()

                pm = PrescribedMedication(prescription_id=rx.id, patient_id=pat.id, medication_id=med.id, medicine_name="Coumadin", dose="5mg", frequency="once daily")
                session.add(pm)
                await session.flush()

                sched = MedicationSchedule(patient_id=pat.id, prescribed_medication_id=pm.id, scheduled_time=time(9, 0), start_date=date(2026, 1, 1), status=ScheduleLifecycle.ACTIVE.value)
                session.add(sched)
                await session.flush()

                ev = MedicationEvent(schedule_id=sched.id, patient_id=pat.id, scheduled_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), status="TAKEN", confirmed_at=datetime(2026, 9, 20, 9, 5, tzinfo=timezone.utc), recorded_by="PATIENT")
                session.add(ev)
                await session.flush()

                assign = ClinicianPatientAssignment(clinician_id=user_clin.id, patient_id=pat.id, assigned_at=utcnow())
                session.add(assign)
                await session.commit()
                event_id = ev.id

            task_a = asyncio.create_task(
                client.post(
                    f"/api/v1/adherence/events/{event_id}/correct",
                    json={"new_status": "SKIPPED", "reason": "PG identical A"},
                    headers=headers_clin,
                )
            )
            task_b = asyncio.create_task(
                client.post(
                    f"/api/v1/adherence/events/{event_id}/correct",
                    json={"new_status": "SKIPPED", "reason": "PG identical B"},
                    headers=headers_clin,
                )
            )

            resp_a, resp_b = await asyncio.gather(task_a, task_b)
            status_codes = sorted([resp_a.status_code, resp_b.status_code])
            assert status_codes == [200, 422], f"Expected [200, 422], got {status_codes}"

            async with sessionmaker() as session:
                audits = (
                    await session.execute(
                        select(MedicationEventCorrection)
                        .where(MedicationEventCorrection.event_id == event_id)
                    )
                ).scalars().all()
                assert len(audits) == 1, f"Expected exactly 1 audit row, got {len(audits)}"
                assert audits[0].previous_status == "TAKEN"
                assert audits[0].new_status == "SKIPPED"

                ev_final = (
                    await session.execute(
                        select(MedicationEvent).where(MedicationEvent.id == event_id)
                    )
                ).scalars().one()
                assert ev_final.status == "SKIPPED"
    finally:
        app.dependency_overrides.clear()
        async with postgres_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
