"""Phase 10.2C Step 3: Clinician Dose-Event Retrieval and Authorization Integration Tests.

Validates:
1. Assigned clinician can retrieve assigned patient's today schedule/events (HTTP 200).
2. Unassigned clinician receives HTTP 403 ("Not assigned to this patient").
3. Patient cannot retrieve another patient's events (HTTP 403).
4. Patient can retrieve their own events without patient_id or with their own patient_id.
5. Admin can retrieve any patient's events.
6. Missing patient scope for clinician returns HTTP 400.
7. Nonexistent patient ID returns HTTP 404.
8. Returned events come from persisted database state with correct patient_id and status.
9. Logged event IDs match persisted MedicationEvent.id.
10. No unrelated patient's events are leaked.
11. Correcting an event via POST /adherence/events/{event_id}/correct reflects immediately
    in subsequent GET /schedule/today?patient_id={id}.
12. Successful correction creates exactly one audit record.
13. No-op correction is cleanly rejected (HTTP 422) and creates zero audit records.
"""

from datetime import date, datetime, time, timezone
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


async def _setup_scenario(client):
    headers_pat1 = await register(client, "pat1@example.com", role="PATIENT")
    headers_pat2 = await register(client, "pat2@example.com", role="PATIENT")
    headers_clin_assigned = await register(client, "clin_assigned@example.com", role="CLINICIAN")
    headers_clin_unassigned = await register(client, "clin_unassigned@example.com", role="CLINICIAN")
    headers_admin = await _bootstrap_admin_headers(client)

    async with _session_for(client) as session:
        u_p1 = (await session.execute(select(User).where(User.email == "pat1@example.com"))).scalars().one()
        p1 = (await session.execute(select(Patient).where(Patient.user_id == u_p1.id))).scalars().one()
        p1.timezone = "UTC"

        u_p2 = (await session.execute(select(User).where(User.email == "pat2@example.com"))).scalars().one()
        p2 = (await session.execute(select(Patient).where(Patient.user_id == u_p2.id))).scalars().one()
        p2.timezone = "UTC"

        u_c1 = (await session.execute(select(User).where(User.email == "clin_assigned@example.com"))).scalars().one()
        u_c2 = (await session.execute(select(User).where(User.email == "clin_unassigned@example.com"))).scalars().one()
        u_admin = (await session.execute(select(User).where(User.email == "bootstrap-admin@example.com"))).scalars().one()

        # Med and prescription for Patient 1
        med = Medication(
            brand_name="Glucophage",
            generic_name="Metformin",
            standard_strength="500mg",
            dosage_form="tablet",
        )
        session.add(med)
        await session.flush()

        rx1 = Prescription(
            patient_id=p1.id,
            doctor_name="Dr. Smith",
            prescription_date=date(2026, 1, 1),
            verification_status="VERIFIED",
        )
        session.add(rx1)
        await session.flush()

        pm1 = PrescribedMedication(
            prescription_id=rx1.id,
            patient_id=p1.id,
            medication_id=med.id,
            medicine_name="Glucophage",
            dose="500mg",
            frequency="once daily",
            is_active=True,
        )
        session.add(pm1)
        await session.flush()

        # Today schedule for Patient 1
        today = utcnow().date()
        sched1 = MedicationSchedule(
            patient_id=p1.id,
            prescribed_medication_id=pm1.id,
            scheduled_time=time(8, 0),
            start_date=today,
            status=ScheduleLifecycle.ACTIVE.value,
        )
        session.add(sched1)
        await session.flush()

        # Event for Patient 1: SKIPPED
        scheduled_instant = datetime.combine(today, time(8, 0), tzinfo=timezone.utc)
        ev1 = MedicationEvent(
            schedule_id=sched1.id,
            patient_id=p1.id,
            scheduled_at=scheduled_instant,
            status=MedicationEventStatus.SKIPPED.value,
            skip_reason="Felt nauseous",
            skip_reason_code="SIDE_EFFECTS",
            recorded_by="PATIENT",
        )
        session.add(ev1)
        await session.flush()

        # Assign clin_assigned to Patient 1 ONLY
        assign = ClinicianPatientAssignment(
            clinician_id=u_c1.id,
            patient_id=p1.id,
            assigned_at=utcnow(),
        )
        session.add(assign)
        await session.commit()

        return {
            "p1_id": p1.id,
            "p2_id": p2.id,
            "ev1_id": ev1.id,
            "sched1_id": sched1.id,
            "c1_id": u_c1.id,
            "c2_id": u_c2.id,
            "admin_id": u_admin.id,
            "headers_p1": headers_pat1,
            "headers_p2": headers_pat2,
            "headers_c1": headers_clin_assigned,
            "headers_c2": headers_clin_unassigned,
            "headers_admin": headers_admin,
        }


@pytest.mark.asyncio
async def test_assigned_clinician_can_retrieve_patient_events(client):
    """Assigned clinician can retrieve patient's events."""
    data = await _setup_scenario(client)
    resp = await client.get(
        f"/api/v1/schedule/today?patient_id={data['p1_id']}",
        headers=data["headers_c1"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_id"] == data["p1_id"]
    assert len(body["doses"]) == 1
    dose = body["doses"][0]
    assert dose["event_id"] == data["ev1_id"]
    assert dose["status"] == "SKIPPED"
    assert dose["medicine_name"] == "Glucophage"


@pytest.mark.asyncio
async def test_unassigned_clinician_receives_403(client):
    """Unassigned clinician receives 403 Forbidden without leaking dose data."""
    data = await _setup_scenario(client)
    resp = await client.get(
        f"/api/v1/schedule/today?patient_id={data['p1_id']}",
        headers=data["headers_c2"],
    )
    assert resp.status_code == 403, resp.text
    assert "not assigned" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patient_cannot_retrieve_other_patient_events(client):
    """Patient 2 cannot access Patient 1's events."""
    data = await _setup_scenario(client)
    resp = await client.get(
        f"/api/v1/schedule/today?patient_id={data['p1_id']}",
        headers=data["headers_p2"],
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_patient_can_retrieve_own_events(client):
    """Patient 1 can retrieve own events with or without patient_id."""
    data = await _setup_scenario(client)
    # Without parameter
    r1 = await client.get("/api/v1/schedule/today", headers=data["headers_p1"])
    assert r1.status_code == 200
    assert r1.json()["patient_id"] == data["p1_id"]

    # With self patient_id
    r2 = await client.get(f"/api/v1/schedule/today?patient_id={data['p1_id']}", headers=data["headers_p1"])
    assert r2.status_code == 200
    assert r2.json()["patient_id"] == data["p1_id"]


@pytest.mark.asyncio
async def test_admin_can_retrieve_patient_events(client):
    """Admin can retrieve any patient's events."""
    data = await _setup_scenario(client)
    resp = await client.get(
        f"/api/v1/schedule/today?patient_id={data['p1_id']}",
        headers=data["headers_admin"],
    )
    assert resp.status_code == 200
    assert resp.json()["patient_id"] == data["p1_id"]


@pytest.mark.asyncio
async def test_clinician_missing_patient_id_returns_400(client):
    """Clinician calling without patient_id receives 400 Bad Request."""
    data = await _setup_scenario(client)
    resp = await client.get("/api/v1/schedule/today", headers=data["headers_c1"])
    assert resp.status_code == 400
    assert "patient_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_nonexistent_patient_id_returns_404(client):
    """Nonexistent patient ID returns 404 Not Found."""
    data = await _setup_scenario(client)
    resp = await client.get("/api/v1/schedule/today?patient_id=999999", headers=data["headers_c1"])
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_correction_reflected_in_subsequent_retrieval_with_single_audit(client):
    """Integration: Correcting an event updates GET /schedule/today state and records 1 audit."""
    data = await _setup_scenario(client)
    ev_id = data["ev1_id"]

    # 1. Initial retrieval: SKIPPED
    r1 = await client.get(f"/api/v1/schedule/today?patient_id={data['p1_id']}", headers=data["headers_c1"])
    assert r1.status_code == 200
    assert r1.json()["doses"][0]["status"] == "SKIPPED"

    # 2. Correct: SKIPPED -> TAKEN
    corr_payload = {"new_status": "TAKEN", "reason": "Patient took dose with lunch"}
    r_corr = await client.post(
        f"/api/v1/adherence/events/{ev_id}/correct",
        json=corr_payload,
        headers=data["headers_c1"],
    )
    assert r_corr.status_code == 200, r_corr.text
    assert r_corr.json()["new_status"] == "TAKEN"

    # 3. Subsequent retrieval: TAKEN
    r2 = await client.get(f"/api/v1/schedule/today?patient_id={data['p1_id']}", headers=data["headers_c1"])
    assert r2.status_code == 200
    assert r2.json()["doses"][0]["status"] == "TAKEN"

    # 4. Verify exactly 1 audit record in DB
    async with _session_for(client) as session:
        audits = (
            await session.execute(
                select(MedicationEventCorrection).where(MedicationEventCorrection.event_id == ev_id)
            )
        ).scalars().all()
        assert len(audits) == 1
        assert audits[0].previous_status == "SKIPPED"
        assert audits[0].new_status == "TAKEN"

    # 5. No-op correction: attempting TAKEN again fails with 422 and creates NO new audit
    r_noop = await client.post(
        f"/api/v1/adherence/events/{ev_id}/correct",
        json=corr_payload,
        headers=data["headers_c1"],
    )
    assert r_noop.status_code == 422

    async with _session_for(client) as session:
        audit_count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == ev_id
                )
            )
        ).scalar()
        assert audit_count == 1
