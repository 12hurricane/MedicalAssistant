"""Phase 9 Step 3: Audit Trail Verification for MedicationEventCorrection.

Establishes that every authorized event correction produces an accurate,
attributable, complete audit record, and that rejected/failed corrections
create zero audit records and do not mutate event history.

Test Coverage:
1. Authorized clinician correction creates exactly one audit row.
2. Audit row contains correct event_id, previous_status, new_status, corrected_by, reason, corrected_at.
3. Event status after correction equals new_status.
4. The audit row's previous_status equals the event status immediately prior to correction.
5. Rejected unauthorized correction creates zero audit rows and leaves event untouched.
6. Nonexistent event creates zero audit rows.
7. Invalid status creates zero audit rows and leaves event untouched.
8. No-op correction creates zero audit rows and leaves event untouched.
9. Legitimate sequential corrections create distinct audit records with the correct status chain.
10. Audit records identify the actual correcting clinician.
11. Admin corrections record the admin as corrected_by.
12. Correction reason is preserved verbatim (including 255-character max constraint).
13. Audit timestamps are valid aware UTC instants.
14. Unrelated audit records are not modified by new corrections.
15. Observable atomicity: event mutation and audit creation are committed together.
"""

from datetime import date, datetime, time, timezone, timedelta

import pytest
from sqlalchemy import func, select

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


# ---------------------------------------------------------------------------
# Setup Helper
# ---------------------------------------------------------------------------

async def _setup_audit_scenario(client):
    """Seed patient, prescribed medication, active schedule, events, and assignments."""
    headers_pat = await register(client, "audit_patient@example.com", role="PATIENT")
    headers_clin_1 = await register(client, "audit_clinician_1@example.com", role="CLINICIAN")
    headers_clin_2 = await register(client, "audit_clinician_2@example.com", role="CLINICIAN")
    headers_admin = await _bootstrap_admin_headers(client)

    async with _session_for(client) as session:
        user_pat = (
            await session.execute(select(User).where(User.email == "audit_patient@example.com"))
        ).scalars().one()
        pat = (
            await session.execute(select(Patient).where(Patient.user_id == user_pat.id))
        ).scalars().one()
        pat.timezone = "UTC"

        user_c1 = (
            await session.execute(select(User).where(User.email == "audit_clinician_1@example.com"))
        ).scalars().one()
        user_c2 = (
            await session.execute(select(User).where(User.email == "audit_clinician_2@example.com"))
        ).scalars().one()
        user_admin = (
            await session.execute(select(User).where(User.email == "bootstrap-admin@example.com"))
        ).scalars().one()

        # Medication & Prescription
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
            doctor_name="Dr. Audit",
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

        # Event 1: TAKEN
        ev1 = MedicationEvent(
            schedule_id=sched.id,
            patient_id=pat.id,
            scheduled_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
            status=MedicationEventStatus.TAKEN.value,
            confirmed_at=datetime(2026, 9, 20, 9, 5, tzinfo=timezone.utc),
            recorded_by="PATIENT",
        )
        # Event 2: SKIPPED
        ev2 = MedicationEvent(
            schedule_id=sched.id,
            patient_id=pat.id,
            scheduled_at=datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc),
            status=MedicationEventStatus.SKIPPED.value,
            skip_reason="Patient was nauseous",
            skip_reason_code="SIDE_EFFECTS",
            recorded_by="PATIENT",
        )
        session.add_all([ev1, ev2])
        await session.flush()

        # Assign Clinician 1 to Patient; Clinician 2 remains unassigned
        assign1 = ClinicianPatientAssignment(
            clinician_id=user_c1.id,
            patient_id=pat.id,
            assigned_at=utcnow(),
        )
        session.add(assign1)
        await session.commit()

        return {
            "patient_id": pat.id,
            "ev1_id": ev1.id,
            "ev2_id": ev2.id,
            "clin_1_id": user_c1.id,
            "clin_2_id": user_c2.id,
            "admin_id": user_admin.id,
            "headers_pat": headers_pat,
            "headers_clin_1": headers_clin_1,
            "headers_clin_2": headers_clin_2,
            "headers_admin": headers_admin,
        }


# ---------------------------------------------------------------------------
# Tests: Authorized Correction and Audit Record Integrity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authorized_clinician_correction_creates_single_complete_audit_record(client):
    """Items 1, 2, 3, 4: Authorized correction creates exactly 1 audit row with complete, accurate fields."""
    data = await _setup_audit_scenario(client)

    payload = {
        "new_status": "MISSED",
        "reason": "Patient confirmed they did not take this morning dose",
    }
    t_before = utcnow() - timedelta(seconds=1)

    response = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    resp_body = response.json()

    t_after = utcnow() + timedelta(seconds=1)

    # 1. API Response verification
    assert resp_body["event_id"] == data["ev1_id"]
    assert resp_body["previous_status"] == "TAKEN"
    assert resp_body["new_status"] == "MISSED"
    assert resp_body["corrected_by"] == data["clin_1_id"]
    assert resp_body["reason"] == payload["reason"]
    assert "correction_id" in resp_body
    assert "corrected_at" in resp_body

    # 2. Database verification: exactly 1 audit row for this event
    async with _session_for(client) as session:
        audits = (
            await session.execute(
                select(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev1_id"]
                )
            )
        ).scalars().all()
        assert len(audits) == 1, f"Expected exactly 1 audit row, found {len(audits)}"

        audit = audits[0]
        # Item 2: Audit fields complete and accurate
        assert audit.id == resp_body["correction_id"]
        assert audit.event_id == data["ev1_id"]
        assert audit.previous_status == "TAKEN"
        assert audit.new_status == "MISSED"
        assert audit.corrected_by == data["clin_1_id"]
        assert audit.reason == payload["reason"]
        assert audit.corrected_at is not None

        # Item 13: Audit timestamps are valid aware UTC instants
        assert t_before <= audit.corrected_at <= t_after
        assert audit.created_at is not None

        # Item 3: Event status updated in place
        event = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev1_id"])
            )
        ).scalars().one()
        assert event.status == "MISSED"

        # Item 4: Previous status in audit matches original event status before mutation
        assert audit.previous_status == "TAKEN"


@pytest.mark.asyncio
async def test_sequential_corrections_form_valid_audit_chain(client):
    """Item 9: Legitimate sequential corrections create two distinct audit rows with correct status chain."""
    data = await _setup_audit_scenario(client)

    # Event 1 starts as TAKEN
    # Step 1: TAKEN -> SKIPPED
    payload_1 = {
        "new_status": "SKIPPED",
        "reason": "First correction: patient reported they actually skipped the dose",
    }
    r1 = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload_1,
        headers=data["headers_clin_1"],
    )
    assert r1.status_code == 200, r1.text

    # Step 2: SKIPPED -> MISSED
    payload_2 = {
        "new_status": "MISSED",
        "reason": "Second correction: patient was asleep and forgot, not a deliberate skip",
    }
    r2 = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload_2,
        headers=data["headers_clin_1"],
    )
    assert r2.status_code == 200, r2.text

    # Inspect the audit chain in the database
    async with _session_for(client) as session:
        audits = (
            await session.execute(
                select(MedicationEventCorrection)
                .where(MedicationEventCorrection.event_id == data["ev1_id"])
                .order_by(MedicationEventCorrection.id.asc())
            )
        ).scalars().all()

        assert len(audits) == 2, f"Expected 2 audit rows, got {len(audits)}"

        # Chain link 1: TAKEN -> SKIPPED
        assert audits[0].previous_status == "TAKEN"
        assert audits[0].new_status == "SKIPPED"
        assert audits[0].reason == payload_1["reason"]
        assert audits[0].corrected_by == data["clin_1_id"]

        # Chain link 2: SKIPPED -> MISSED
        assert audits[1].previous_status == "SKIPPED"
        assert audits[1].new_status == "MISSED"
        assert audits[1].reason == payload_2["reason"]
        assert audits[1].corrected_by == data["clin_1_id"]

        # Event final status is MISSED
        event = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev1_id"])
            )
        ).scalars().one()
        assert event.status == "MISSED"


@pytest.mark.asyncio
async def test_admin_correction_records_admin_as_actor(client):
    """Item 11: Admin corrections record the admin user ID in corrected_by."""
    data = await _setup_audit_scenario(client)

    payload = {
        "new_status": "MISSED",
        "reason": "Administrative manual correction",
    }
    r = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload,
        headers=data["headers_admin"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["corrected_by"] == data["admin_id"]

    async with _session_for(client) as session:
        audit = (
            await session.execute(
                select(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev1_id"]
                )
            )
        ).scalars().one()
        assert audit.corrected_by == data["admin_id"]


@pytest.mark.asyncio
async def test_correction_reason_preserved_verbatim_boundaries(client):
    """Item 12: Correction reason is preserved exactly across minimum (3 chars) and maximum (255 chars)."""
    data = await _setup_audit_scenario(client)

    # 1. Minimum valid length reason (3 characters)
    payload_min = {"new_status": "SKIPPED", "reason": "Err"}
    r1 = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload_min,
        headers=data["headers_clin_1"],
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["reason"] == "Err"

    # 2. Maximum valid length reason (255 characters)
    reason_255 = "A" * 255
    payload_max = {"new_status": "TAKEN", "reason": reason_255}
    r2 = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload_max,
        headers=data["headers_clin_1"],
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["reason"] == reason_255

    # 3. Exceeding max length (256 characters) rejected by Pydantic before DB
    payload_over = {"new_status": "MISSED", "reason": "A" * 256}
    r3 = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload_over,
        headers=data["headers_clin_1"],
    )
    assert r3.status_code == 422, "Expected 422 for reason exceeding 255 characters"


@pytest.mark.asyncio
async def test_unrelated_audit_records_are_not_modified_by_new_correction(client):
    """Item 14: Correcting Event 1 does not mutate or alter the audit records of Event 2."""
    data = await _setup_audit_scenario(client)

    # Correct Event 2 first: SKIPPED -> TAKEN
    p2 = {"new_status": "TAKEN", "reason": "Event 2 initial correction"}
    r2 = await client.post(
        f"/api/v1/adherence/events/{data['ev2_id']}/correct",
        json=p2,
        headers=data["headers_clin_1"],
    )
    assert r2.status_code == 200
    ev2_audit_id = r2.json()["correction_id"]

    # Now correct Event 1: TAKEN -> MISSED
    p1 = {"new_status": "MISSED", "reason": "Event 1 distinct correction"}
    r1 = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=p1,
        headers=data["headers_clin_1"],
    )
    assert r1.status_code == 200

    # Verify Event 2's audit record remains completely unchanged
    async with _session_for(client) as session:
        ev2_audit = (
            await session.execute(
                select(MedicationEventCorrection).where(
                    MedicationEventCorrection.id == ev2_audit_id
                )
            )
        ).scalars().one()
        assert ev2_audit.event_id == data["ev2_id"]
        assert ev2_audit.previous_status == "SKIPPED"
        assert ev2_audit.new_status == "TAKEN"
        assert ev2_audit.reason == p2["reason"]


# ---------------------------------------------------------------------------
# Tests: Rejected / Failed Scenarios Produce Zero Audit Rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unauthorized_clinician_creates_zero_audit_rows_and_leaves_event_intact(client):
    """Item 5: Rejected unauthorized clinician correction creates zero audit rows."""
    data = await _setup_audit_scenario(client)

    payload = {"new_status": "MISSED", "reason": "Unauthorized attempt"}
    r = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload,
        headers=data["headers_clin_2"],  # Clinician 2 is NOT assigned
    )
    assert r.status_code == 403

    async with _session_for(client) as session:
        # Assert zero audit rows
        count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev1_id"]
                )
            )
        ).scalar()
        assert count == 0

        # Assert event status untouched
        ev = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev1_id"])
            )
        ).scalars().one()
        assert ev.status == "TAKEN"


@pytest.mark.asyncio
async def test_nonexistent_event_creates_zero_audit_rows(client):
    """Item 6: Nonexistent event ID creates zero audit rows."""
    data = await _setup_audit_scenario(client)

    payload = {"new_status": "MISSED", "reason": "Nonexistent event attempt"}
    r = await client.post(
        "/api/v1/adherence/events/999999/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert r.status_code == 404

    async with _session_for(client) as session:
        count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == 999999
                )
            )
        ).scalar()
        assert count == 0


@pytest.mark.asyncio
async def test_invalid_status_creates_zero_audit_rows(client):
    """Item 7: Invalid status creates zero audit rows and leaves event untouched."""
    data = await _setup_audit_scenario(client)

    payload = {"new_status": "INVALID_STATUS_CODE", "reason": "Invalid status attempt"}
    r = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert r.status_code == 422

    async with _session_for(client) as session:
        count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev1_id"]
                )
            )
        ).scalar()
        assert count == 0

        ev = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev1_id"])
            )
        ).scalars().one()
        assert ev.status == "TAKEN"


@pytest.mark.asyncio
async def test_noop_correction_creates_zero_audit_rows(client):
    """Item 8: No-op correction to identical status creates zero audit rows."""
    data = await _setup_audit_scenario(client)

    # Event 1 is already TAKEN
    payload = {"new_status": "TAKEN", "reason": "No-op attempt to set TAKEN"}
    r = await client.post(
        f"/api/v1/adherence/events/{data['ev1_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert r.status_code == 422
    assert "already taken" in r.json()["detail"].lower()

    async with _session_for(client) as session:
        count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev1_id"]
                )
            )
        ).scalar()
        assert count == 0

        ev = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev1_id"])
            )
        ).scalars().one()
        assert ev.status == "TAKEN"


@pytest.mark.asyncio
async def test_unauthenticated_request_creates_zero_audit_rows(client):
    """Unauthenticated correction request creates zero audit rows."""
    payload = {"new_status": "MISSED", "reason": "Unauthenticated correction"}
    r = await client.post("/api/v1/adherence/events/1/correct", json=payload)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Item 15 & Atomicity Boundary Observation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_observable_atomicity_of_event_mutation_and_audit_creation(client):
    """Item 15: Event mutation and audit row creation are committed together.

    Observes that in the application pipeline:
    - If validation/authorization passes, BOTH event mutation and audit row are persisted.
    - If validation/authorization fails, NEITHER event mutation nor audit row is persisted.
    """
    data = await _setup_audit_scenario(client)

    # Baseline check
    async with _session_for(client) as session:
        initial_event = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev2_id"])
            )
        ).scalars().one()
        assert initial_event.status == "SKIPPED"

        initial_audits = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev2_id"]
                )
            )
        ).scalar()
        assert initial_audits == 0

    # Successful call
    payload = {"new_status": "TAKEN", "reason": "Observing atomic commit"}
    r = await client.post(
        f"/api/v1/adherence/events/{data['ev2_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert r.status_code == 200

    # Verify both exist together in the committed state
    async with _session_for(client) as session:
        updated_event = (
            await session.execute(
                select(MedicationEvent).where(MedicationEvent.id == data["ev2_id"])
            )
        ).scalars().one()
        audit_count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev2_id"]
                )
            )
        ).scalar()

        assert updated_event.status == "TAKEN"
        assert audit_count == 1
