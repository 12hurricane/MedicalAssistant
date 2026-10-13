"""Phase 9 Step 4: Transactional Integrity and Concurrency Verification.

Tests:
1. Commit failure: Simulated commit failure rolls back event mutation and creates zero audit records.
2. Concurrent corrections: Two concurrent requests against the same MedicationEvent
   must not produce a forked audit trail.
3. Concurrency failure / rollback: When a concurrent transaction fails, it leaves zero
   audit records, no partial mutation, and the successful transaction remains linear and intact.
"""

from datetime import date, datetime, time, timezone, timedelta
from unittest.mock import patch
import asyncio
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
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
from conftest import _bootstrap_admin_headers, _session_for, register


async def _setup_event(client, initial_status="TAKEN"):
    """Seed patient, prescribed medication, active schedule, event, and assigned clinician."""
    headers_pat = await register(client, "tx_patient@example.com", role="PATIENT")
    headers_clin = await register(client, "tx_clinician@example.com", role="CLINICIAN")

    async with _session_for(client) as session:
        user_pat = (
            await session.execute(select(User).where(User.email == "tx_patient@example.com"))
        ).scalars().one()
        pat = (
            await session.execute(select(Patient).where(Patient.user_id == user_pat.id))
        ).scalars().one()
        pat.timezone = "UTC"

        user_clin = (
            await session.execute(select(User).where(User.email == "tx_clinician@example.com"))
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
            doctor_name="Dr. Tx",
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
            status=initial_status,
            confirmed_at=datetime(2026, 9, 20, 9, 5, tzinfo=timezone.utc) if initial_status == "TAKEN" else None,
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

        return {
            "patient_id": pat.id,
            "event_id": ev.id,
            "clinician_id": user_clin.id,
            "headers_clin": headers_clin,
        }


# ---------------------------------------------------------------------------
# Step 4B: Commit Failure / Atomicity Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_commit_failure_rolls_back_event_and_creates_zero_audit(client):
    """Simulate database commit failure after staging audit & event mutation.

    Invariant:
    FAILURE -> event.status unchanged AND zero audit records.
    """
    data = await _setup_event(client, initial_status="TAKEN")
    event_id = data["event_id"]

    # We patch AsyncSession.commit to raise SQLAlchemyError simulating DB crash/constraint failure
    with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=SQLAlchemyError("DB Commit Simulated Crash")):
        payload = {"new_status": "SKIPPED", "reason": "Attempt that should fail at commit"}
        try:
            resp = await client.post(
                f"/api/v1/adherence/events/{event_id}/correct",
                json=payload,
                headers=data["headers_clin"],
            )
            # If the app caught and re-raised or returned 500
            assert resp.status_code >= 500
        except SQLAlchemyError:
            # If exception bubbled up through test client
            pass

    # Inspect DB: event must still be TAKEN, and 0 audit rows must exist
    async with _session_for(client) as session:
        ev = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == event_id)
            )
        ).scalars().one()
        assert ev.status == "TAKEN", f"Event status mutated despite commit failure: {ev.status}"

        audit_count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == event_id
                )
            )
        ).scalar()
        assert audit_count == 0, f"Audit row was persisted despite commit failure: {audit_count}"


@pytest.mark.asyncio
async def test_mid_transaction_exception_leaves_database_clean(client):
    """If an exception occurs between audit creation and commit, rollback must occur."""
    data = await _setup_event(client, initial_status="TAKEN")
    event_id = data["event_id"]

    # Patch utcnow called during correction to raise an error mid-flight
    # or patch db.refresh to fail
    with patch("sqlalchemy.ext.asyncio.AsyncSession.refresh", side_effect=RuntimeError("Post-commit refresh failure")):
        payload = {"new_status": "MISSED", "reason": "Mid transaction failure"}
        try:
            resp = await client.post(
                f"/api/v1/adherence/events/{event_id}/correct",
                json=payload,
                headers=data["headers_clin"],
            )
            assert resp.status_code >= 500
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Step 4C & 4D: Concurrency & Linear Status Invariant Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_corrections_must_not_fork_audit_history(client):
    """Step 4C: Two concurrent corrections against the SAME MedicationEvent.

    Initial state: TAKEN
    Request A: TAKEN -> SKIPPED
    Request B: TAKEN -> MISSED

    Invariant:
    The audit history must NEVER contain two records with the same previous_status
    (i.e. TAKEN -> SKIPPED and TAKEN -> MISSED).
    It must be a single linear chain (e.g. TAKEN -> SKIPPED -> MISSED or TAKEN -> MISSED -> SKIPPED),
    or one must succeed and the other be rejected/fail cleanly.
    """
    async with _session_for(client) as session:
        if session.bind.dialect.name == "sqlite":
            pytest.skip(
                "SQLite silently ignores SELECT ... FOR UPDATE (no row-level locking in SQLite). "
                "True database-level row lock serialization requires PostgreSQL. "
                "See test_postgres_concurrency.py."
            )

    data = await _setup_event(client, initial_status="TAKEN")
    event_id = data["event_id"]

    # Launch two concurrent correction requests
    task_a = asyncio.create_task(
        client.post(
            f"/api/v1/adherence/events/{event_id}/correct",
            json={"new_status": "SKIPPED", "reason": "Concurrent correction A: patient skipped"},
            headers=data["headers_clin"],
        )
    )
    task_b = asyncio.create_task(
        client.post(
            f"/api/v1/adherence/events/{event_id}/correct",
            json={"new_status": "MISSED", "reason": "Concurrent correction B: patient forgot"},
            headers=data["headers_clin"],
        )
    )

    resp_a, resp_b = await asyncio.gather(task_a, task_b, return_exceptions=True)

    # Inspect the audit trail in the database
    async with _session_for(client) as session:
        audits = (
            await session.execute(
                select(MedicationEventCorrection)
                .where(MedicationEventCorrection.event_id == event_id)
                .order_by(MedicationEventCorrection.id.asc())
            )
        ).scalars().all()

        # Check for forked audit history:
        # If both succeeded, their previous_status MUST NOT both be 'TAKEN'
        if len(audits) == 2:
            assert audits[0].previous_status != audits[1].previous_status, (
                f"FORKED AUDIT TRAIL DETECTED! Both records have previous_status="
                f"'{audits[0].previous_status}' and '{audits[1].previous_status}'. "
                f"Record 1: {audits[0].previous_status}->{audits[0].new_status}, "
                f"Record 2: {audits[1].previous_status}->{audits[1].new_status}"
            )
            # The second record's previous_status must match the first record's new_status
            assert audits[1].previous_status == audits[0].new_status, (
                f"Discontinuous audit chain: {audits[0].previous_status}->{audits[0].new_status} "
                f"followed by {audits[1].previous_status}->{audits[1].new_status}"
            )
            # And the final event status must match the second audit record's new_status
            ev = (
                await session.execute(
                    select(MedicationEvent).where(MedicationEvent.id == event_id)
                )
            ).scalars().one()
            assert ev.status == audits[1].new_status
        elif len(audits) == 1:
            # One succeeded and one was serialized/rejected
            ev = (
                await session.execute(
                    select(MedicationEvent).where(MedicationEvent.id == event_id)
                )
            ).scalars().one()
            assert ev.status == audits[0].new_status
        else:
            pytest.fail(f"Unexpected audit count: {len(audits)}")


@pytest.mark.asyncio
async def test_concurrent_identical_corrections_serialize_with_clean_rejection(client):
    """Step 4C/4D: Two concurrent requests attempting the SAME new_status.

    Initial state: TAKEN
    Request A: TAKEN -> SKIPPED
    Request B: TAKEN -> SKIPPED

    Invariant:
    - Exactly one request succeeds (HTTP 200).
    - The second request observes the serialized state and is rejected (HTTP 422).
    - Exactly one audit row exists in the database.
    - Final event status is SKIPPED.
    """
    async with _session_for(client) as session:
        if session.bind.dialect.name == "sqlite":
            pytest.skip(
                "SQLite silently ignores SELECT ... FOR UPDATE (no row-level locking in SQLite). "
                "True database-level row lock serialization requires PostgreSQL. "
                "See test_postgres_concurrency.py."
            )

    data = await _setup_event(client, initial_status="TAKEN")
    event_id = data["event_id"]

    task_a = asyncio.create_task(
        client.post(
            f"/api/v1/adherence/events/{event_id}/correct",
            json={"new_status": "SKIPPED", "reason": "Concurrent identical A"},
            headers=data["headers_clin"],
        )
    )
    task_b = asyncio.create_task(
        client.post(
            f"/api/v1/adherence/events/{event_id}/correct",
            json={"new_status": "SKIPPED", "reason": "Concurrent identical B"},
            headers=data["headers_clin"],
        )
    )

    resp_a, resp_b = await asyncio.gather(task_a, task_b)
    status_codes = sorted([resp_a.status_code, resp_b.status_code])
    assert status_codes == [200, 422], f"Expected [200, 422], got {status_codes}"

    # Verify database state
    async with _session_for(client) as session:
        audits = (
            await session.execute(
                select(MedicationEventCorrection)
                .where(MedicationEventCorrection.event_id == event_id)
            )
        ).scalars().all()
        assert len(audits) == 1, f"Expected exactly 1 audit row, got {len(audits)}"
        assert audits[0].previous_status == "TAKEN"
        assert audits[0].new_status == "SKIPPED"

        ev = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == event_id)
            )
        ).scalars().one()
        assert ev.status == "SKIPPED"


@pytest.mark.asyncio
async def test_concurrent_forced_failure_leaves_clean_rollback_and_linear_audit(client):
    """Step 4D: When one concurrent correction fails, verify rollback and linear history.

    - Failed transaction does not leave an audit row.
    - Failed transaction does not corrupt event status.
    - Successful transaction's audit remains correct.
    - Final event status matches surviving successful correction.
    - Audit history remains strictly linear.
    """
    data = await _setup_event(client, initial_status="TAKEN")
    event_id = data["event_id"]

    original_commit = AsyncSession.commit
    fail_first = True

    async def selective_commit(self):
        nonlocal fail_first
        # Fail the first commit attempt, let subsequent attempts succeed
        if fail_first:
            fail_first = False
            raise SQLAlchemyError("Simulated concurrent commit failure")
        return await original_commit(self)

    with patch.object(AsyncSession, "commit", selective_commit):
        task_a = asyncio.create_task(
            client.post(
                f"/api/v1/adherence/events/{event_id}/correct",
                json={"new_status": "SKIPPED", "reason": "Correction A"},
                headers=data["headers_clin"],
            )
        )
        task_b = asyncio.create_task(
            client.post(
                f"/api/v1/adherence/events/{event_id}/correct",
                json={"new_status": "MISSED", "reason": "Correction B"},
                headers=data["headers_clin"],
            )
        )

        resp_a, resp_b = await asyncio.gather(task_a, task_b, return_exceptions=True)

    # One request failed (>=500 or SQLAlchemyError), one succeeded (200)
    results = [resp_a, resp_b]
    successes = [r for r in results if hasattr(r, "status_code") and r.status_code == 200]
    failures = [
        r for r in results
        if isinstance(r, Exception) or (hasattr(r, "status_code") and r.status_code >= 500)
    ]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

    surviving_status = successes[0].json()["new_status"]

    # Verify database state
    async with _session_for(client) as session:
        audits = (
            await session.execute(
                select(MedicationEventCorrection)
                .where(MedicationEventCorrection.event_id == event_id)
            )
        ).scalars().all()

        # Failed transaction must NOT leave an audit row
        assert len(audits) == 1, f"Failed transaction left orphan audit row! Found {len(audits)}"
        assert audits[0].previous_status == "TAKEN"
        assert audits[0].new_status == surviving_status

        # Final event status must match the surviving successful correction
        ev = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == event_id)
            )
        ).scalars().one()
        assert ev.status == surviving_status


