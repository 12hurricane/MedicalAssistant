from datetime import date, time
import pytest
from httpx import AsyncClient
from sqlalchemy import select, func
from conftest import register, _bootstrap_admin_headers, _session_for
from app.models.patient import Patient
from app.models.user import User
from app.models.clinician_patient_assignment import ClinicianPatientAssignment
from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.medication_event_correction import MedicationEventCorrection
from app.models.medication_schedule import MedicationSchedule, ScheduleLifecycle
from app.models.prescribed_medication import PrescribedMedication
from app.models.prescription import Prescription
from app.models.types import utcnow


# ===========================================================================
# Helper Fixtures & Setup
# ===========================================================================

async def _assign_clinician(client: AsyncClient, clinician_email: str, patient_id: int):
    """Helper to assign a clinician to a patient in the per-test database."""
    async with _session_for(client) as session:
        user_clin = (
            await session.execute(select(User).where(User.email == clinician_email))
        ).scalars().one()
        assignment = ClinicianPatientAssignment(
            clinician_id=user_clin.id,
            patient_id=patient_id,
            assigned_at=utcnow(),
        )
        session.add(assignment)
        await session.commit()


# ===========================================================================
# 1. Authorization Scenarios (SEC-01 to SEC-11)
# ===========================================================================

@pytest.mark.asyncio
async def test_sec_01_admin_accesses_patient_profile(client: AsyncClient):
    """SEC-01: Admin accesses any patient profile -> 200 OK."""
    p_headers = await register(client, "patient_sec01@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    admin_headers = await _bootstrap_admin_headers(client)
    resp = await client.get(f"/api/v1/patients/{patient_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == patient_id


@pytest.mark.asyncio
async def test_sec_02_admin_accesses_patient_safety(client: AsyncClient):
    """SEC-02: Admin accesses any patient safety assessment -> 200 OK."""
    p_headers = await register(client, "patient_sec02@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    admin_headers = await _bootstrap_admin_headers(client)
    resp = await client.get(f"/api/v1/patients/{patient_id}/safety", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data


@pytest.mark.asyncio
async def test_sec_03_assigned_clinician_accesses_patient_profile(client: AsyncClient):
    """SEC-03: Assigned clinician accesses patient profile -> 200 OK."""
    p_headers = await register(client, "patient_sec03@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    c_headers = await register(client, "doc_sec03@example.com", role="CLINICIAN")
    await _assign_clinician(client, "doc_sec03@example.com", patient_id)

    resp = await client.get(f"/api/v1/patients/{patient_id}", headers=c_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == patient_id


@pytest.mark.asyncio
async def test_sec_04_assigned_clinician_accesses_patient_safety(client: AsyncClient):
    """SEC-04: Assigned clinician accesses safety assessment -> 200 OK."""
    p_headers = await register(client, "patient_sec04@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    c_headers = await register(client, "doc_sec04@example.com", role="CLINICIAN")
    await _assign_clinician(client, "doc_sec04@example.com", patient_id)

    resp = await client.get(f"/api/v1/patients/{patient_id}/safety", headers=c_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data


@pytest.mark.asyncio
async def test_sec_05_unassigned_clinician_accesses_patient_profile(client: AsyncClient):
    """SEC-05: Unassigned clinician accesses patient profile -> 403 Forbidden."""
    p_headers = await register(client, "patient_sec05@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    c_headers = await register(client, "doc_sec05@example.com", role="CLINICIAN")

    resp = await client.get(f"/api/v1/patients/{patient_id}", headers=c_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not assigned to this patient"


@pytest.mark.asyncio
async def test_sec_06_unassigned_clinician_accesses_patient_safety(client: AsyncClient):
    """SEC-06: Unassigned clinician accesses safety assessment -> 403 Forbidden."""
    p_headers = await register(client, "patient_sec06@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    c_headers = await register(client, "doc_sec06@example.com", role="CLINICIAN")

    resp = await client.get(f"/api/v1/patients/{patient_id}/safety", headers=c_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not assigned to this patient"


@pytest.mark.asyncio
async def test_sec_07_patient_accesses_own_profile(client: AsyncClient):
    """SEC-07: Patient accesses own profile via /me -> 200 OK."""
    p_headers = await register(client, "patient_sec07@example.com", role="PATIENT")
    resp = await client.get("/api/v1/patients/me", headers=p_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["timezone"] is not None


@pytest.mark.asyncio
async def test_sec_08_patient_accesses_own_safety(client: AsyncClient):
    """SEC-08: Patient accesses own safety via /me/safety -> 200 OK."""
    p_headers = await register(client, "patient_sec08@example.com", role="PATIENT")
    resp = await client.get("/api/v1/patients/me/safety", headers=p_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_level" in data


@pytest.mark.asyncio
async def test_sec_09_patient_attempts_foreign_patient_profile(client: AsyncClient):
    """SEC-09: Patient attempts to access another patient's profile -> 403 Forbidden."""
    p1_headers = await register(client, "patient_sec09_a@example.com", role="PATIENT")
    p2_headers = await register(client, "patient_sec09_b@example.com", role="PATIENT")
    p2_resp = await client.get("/api/v1/patients/me", headers=p2_headers)
    p2_id = p2_resp.json()["id"]

    resp = await client.get(f"/api/v1/patients/{p2_id}", headers=p1_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not enough permissions"


@pytest.mark.asyncio
async def test_sec_10_patient_attempts_foreign_safety(client: AsyncClient):
    """SEC-10: Patient attempts foreign safety assessment -> 403 Forbidden."""
    p1_headers = await register(client, "patient_sec10_a@example.com", role="PATIENT")
    p2_headers = await register(client, "patient_sec10_b@example.com", role="PATIENT")
    p2_resp = await client.get("/api/v1/patients/me", headers=p2_headers)
    p2_id = p2_resp.json()["id"]

    resp = await client.get(f"/api/v1/patients/{p2_id}/safety", headers=p1_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not enough permissions"


@pytest.mark.asyncio
async def test_sec_11_patient_attempts_to_access_roster(client: AsyncClient):
    """SEC-11: Patient attempts to access roster -> 403 Forbidden."""
    p_headers = await register(client, "patient_sec11@example.com", role="PATIENT")
    resp = await client.get("/api/v1/patients", headers=p_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not enough permissions"


# ===========================================================================
# 2. Unauthenticated Scenarios (SEC-12 to SEC-14)
# ===========================================================================

@pytest.mark.asyncio
async def test_sec_12_unauthenticated_roster(client: AsyncClient):
    """SEC-12: Unauthenticated request to roster -> 401 Unauthorized with WWW-Authenticate."""
    resp = await client.get("/api/v1/patients")
    assert resp.status_code == 401
    assert "bearer" in resp.headers.get("www-authenticate", "").lower()


@pytest.mark.asyncio
async def test_sec_13_unauthenticated_patient_profile(client: AsyncClient):
    """SEC-13: Unauthenticated request to patient profile -> 401 Unauthorized with WWW-Authenticate."""
    resp = await client.get("/api/v1/patients/1")
    assert resp.status_code == 401
    assert "bearer" in resp.headers.get("www-authenticate", "").lower()


@pytest.mark.asyncio
async def test_sec_14_unauthenticated_safety(client: AsyncClient):
    """SEC-14: Unauthenticated request to safety assessment -> 401 Unauthorized with WWW-Authenticate."""
    resp = await client.get("/api/v1/patients/1/safety")
    assert resp.status_code == 401
    assert "bearer" in resp.headers.get("www-authenticate", "").lower()


# ===========================================================================
# 3. Negative / 404 Scenarios (SEC-15 to SEC-16)
# ===========================================================================

@pytest.mark.asyncio
async def test_sec_15_nonexistent_patient_profile_lookup(client: AsyncClient):
    """SEC-15: Nonexistent patient profile lookup -> 404 Not Found."""
    doc_headers = await register(client, "doc_sec15@example.com", role="CLINICIAN")
    resp = await client.get("/api/v1/patients/99999", headers=doc_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found"


@pytest.mark.asyncio
async def test_sec_16_nonexistent_patient_safety_lookup(client: AsyncClient):
    """SEC-16: Nonexistent patient safety lookup -> 404 Not Found."""
    doc_headers = await register(client, "doc_sec16@example.com", role="CLINICIAN")
    resp = await client.get("/api/v1/patients/99999/safety", headers=doc_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Patient not found"


# ===========================================================================
# 4. Roster Isolation & Scoping Scenarios (SEC-17 to SEC-19)
# ===========================================================================

@pytest.mark.asyncio
async def test_sec_17_clinician_roster_returns_only_assigned_patients(client: AsyncClient):
    """SEC-17: Clinician roster returns only assigned patients."""
    p_a = await register(client, "pat_sec17_a@example.com", role="PATIENT")
    resp_a = await client.get("/api/v1/patients/me", headers=p_a)
    id_a = resp_a.json()["id"]

    await register(client, "pat_sec17_b@example.com", role="PATIENT")
    await register(client, "pat_sec17_c@example.com", role="PATIENT")

    doc_headers = await register(client, "doc_sec17@example.com", role="CLINICIAN")
    await _assign_clinician(client, "doc_sec17@example.com", id_a)

    resp = await client.get("/api/v1/patients", headers=doc_headers)
    assert resp.status_code == 200
    patients = resp.json()
    assert len(patients) == 1
    assert patients[0]["id"] == id_a


@pytest.mark.asyncio
async def test_sec_18_clinician_with_zero_assignments_receives_empty_list(client: AsyncClient):
    """SEC-18: Clinician with zero assignments receives empty list []."""
    await register(client, "pat_sec18@example.com", role="PATIENT")

    doc_headers = await register(client, "doc_sec18@example.com", role="CLINICIAN")
    resp = await client.get("/api/v1/patients", headers=doc_headers)
    assert resp.status_code == 200
    patients = resp.json()
    assert isinstance(patients, list)
    assert len(patients) == 0


@pytest.mark.asyncio
async def test_sec_19_admin_roster_returns_all_patients(client: AsyncClient):
    """SEC-19: Admin roster returns all patients system-wide."""
    await register(client, "pat_sec19_a@example.com", role="PATIENT")
    await register(client, "pat_sec19_b@example.com", role="PATIENT")

    admin_headers = await _bootstrap_admin_headers(client)
    resp = await client.get("/api/v1/patients", headers=admin_headers)
    assert resp.status_code == 200
    patients = resp.json()
    assert len(patients) >= 2
    emails = [p.get("email") for p in patients]
    assert "pat_sec19_a@example.com" in emails
    assert "pat_sec19_b@example.com" in emails


# ===========================================================================
# 5. Roster Search & Multi-Page Pagination (SEC-20 to SEC-22)
# ===========================================================================

@pytest.mark.asyncio
async def test_sec_20_clinician_search_cannot_expose_unassigned_patients(client: AsyncClient):
    """SEC-20: Clinician search cannot expose unassigned patients."""
    # Patient A assigned to Doc 1
    pa_headers = await register(client, "assigned_zebra@example.com", role="PATIENT")
    pa_resp = await client.get("/api/v1/patients/me", headers=pa_headers)
    pa_id = pa_resp.json()["id"]

    # Patient B unassigned
    await register(client, "unassigned_zebra@example.com", role="PATIENT")

    doc_headers = await register(client, "doc_sec20@example.com", role="CLINICIAN")
    await _assign_clinician(client, "doc_sec20@example.com", pa_id)

    # Search matches both, but only Patient A must appear
    resp = await client.get("/api/v1/patients?search=zebra", headers=doc_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["id"] == pa_id
    assert results[0]["email"] == "assigned_zebra@example.com"


@pytest.mark.asyncio
async def test_sec_21_clinician_pagination_scoping_precedence(client: AsyncClient):
    """SEC-21: Multi-page pagination proving assignment scoping strictly precedes pagination.
    
    Fixture:
      Doc 1: Assigned to Patient A, Patient B
      Doc 2: Assigned to Patient C
      Unassigned: Patient D
    """
    pa_headers = await register(client, "pat_sec21_a@example.com", role="PATIENT")
    pa_id = (await client.get("/api/v1/patients/me", headers=pa_headers)).json()["id"]

    pb_headers = await register(client, "pat_sec21_b@example.com", role="PATIENT")
    pb_id = (await client.get("/api/v1/patients/me", headers=pb_headers)).json()["id"]

    pc_headers = await register(client, "pat_sec21_c@example.com", role="PATIENT")
    pc_id = (await client.get("/api/v1/patients/me", headers=pc_headers)).json()["id"]

    pd_headers = await register(client, "pat_sec21_d@example.com", role="PATIENT")
    pd_id = (await client.get("/api/v1/patients/me", headers=pd_headers)).json()["id"]

    doc1_headers = await register(client, "doc_sec21_1@example.com", role="CLINICIAN")
    await register(client, "doc_sec21_2@example.com", role="CLINICIAN")

    # Assign Doc 1 -> A & B
    await _assign_clinician(client, "doc_sec21_1@example.com", pa_id)
    await _assign_clinician(client, "doc_sec21_1@example.com", pb_id)

    # Assign Doc 2 -> C
    await _assign_clinician(client, "doc_sec21_2@example.com", pc_id)

    # Page 1: limit=1
    page1_resp = await client.get("/api/v1/patients?skip=0&limit=1", headers=doc1_headers)
    assert page1_resp.status_code == 200
    page1 = page1_resp.json()
    assert len(page1) == 1
    assert page1[0]["id"] == pa_id

    # Page 2: skip=1&limit=1
    page2_resp = await client.get("/api/v1/patients?skip=1&limit=1", headers=doc1_headers)
    assert page2_resp.status_code == 200
    page2 = page2_resp.json()
    assert len(page2) == 1
    assert page2[0]["id"] == pb_id

    # Page 3: skip=2&limit=1 (should be empty for Doc 1)
    page3_resp = await client.get("/api/v1/patients?skip=2&limit=1", headers=doc1_headers)
    assert page3_resp.status_code == 200
    page3 = page3_resp.json()
    assert len(page3) == 0

    # Strict non-leakage assertion: Patients C and D never appear on any page
    seen_ids = {page1[0]["id"], page2[0]["id"]}
    assert pc_id not in seen_ids
    assert pd_id not in seen_ids


@pytest.mark.asyncio
async def test_sec_22_admin_search_and_pagination(client: AsyncClient):
    """SEC-22: Admin search and pagination remains functional system-wide across all patients."""
    await register(client, "zebra_alpha@example.com", role="PATIENT")
    await register(client, "zebra_beta@example.com", role="PATIENT")

    admin_headers = await _bootstrap_admin_headers(client)
    resp = await client.get("/api/v1/patients?search=zebra&skip=0&limit=10", headers=admin_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 2
    emails = [p["email"] for p in results]
    assert "zebra_alpha@example.com" in emails
    assert "zebra_beta@example.com" in emails


# ===========================================================================
# 6. Existing Invariant Regressions (SEC-23 to SEC-24)
# ===========================================================================

@pytest.mark.asyncio
async def test_sec_23_existing_adherence_authorization_preserved(client: AsyncClient):
    """SEC-23: Unassigned clinician calling adherence analysis receives 403 Forbidden."""
    p_headers = await register(client, "patient_sec23@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    doc_headers = await register(client, "doc_sec23@example.com", role="CLINICIAN")

    resp = await client.get(f"/api/v1/adherence/analysis?patient_id={patient_id}", headers=doc_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not assigned to this patient"


@pytest.mark.asyncio
async def test_sec_24_existing_dose_event_correction_preserved(client: AsyncClient):
    """SEC-24: Unassigned clinician calling dose event correction receives 403 & 0 audit rows created."""
    p_headers = await register(client, "patient_sec24@example.com", role="PATIENT")
    p_resp = await client.get("/api/v1/patients/me", headers=p_headers)
    patient_id = p_resp.json()["id"]

    # Seed prescription, medication, schedule, and event directly
    async with _session_for(client) as session:
        rx = Prescription(
            patient_id=patient_id,
            doctor_name="Dr. Sec",
            prescription_date=date(2026, 1, 1),
            verification_status="VERIFIED",
        )
        session.add(rx)
        await session.flush()

        pm = PrescribedMedication(
            prescription_id=rx.id,
            patient_id=patient_id,
            medicine_name="SecMed",
            dose="10mg",
            frequency="once daily",
        )
        session.add(pm)
        await session.flush()

        sched = MedicationSchedule(
            patient_id=patient_id,
            prescribed_medication_id=pm.id,
            scheduled_time=time(9, 0),
            start_date=date(2026, 1, 1),
            status=ScheduleLifecycle.ACTIVE.value,
        )
        session.add(sched)
        await session.flush()

        event = MedicationEvent(
            patient_id=patient_id,
            schedule_id=sched.id,
            status="TAKEN",
            scheduled_at=utcnow(),
            recorded_by="PATIENT",
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        event_id = event.id

    doc_headers = await register(client, "doc_sec24@example.com", role="CLINICIAN")

    payload = {
        "new_status": "SKIPPED",
        "reason": "Clinician noticed patient was fasting",
    }
    resp = await client.post(f"/api/v1/adherence/events/{event_id}/correct", json=payload, headers=doc_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Not assigned to this patient"

    # Verify zero audit rows created
    async with _session_for(client) as session:
        audit_count = (
            await session.execute(
                select(func.count(MedicationEventCorrection.id)).where(
                    MedicationEventCorrection.event_id == event_id
                )
            )
        ).scalar()
        assert audit_count == 0


# ===========================================================================
# 7. Additional Profile Baseline Check
# ===========================================================================

@pytest.mark.asyncio
async def test_update_current_patient(client: AsyncClient):
    """Preserved baseline: Patient updates own profile."""
    headers = await register(client, "updatepatient@example.com", role="PATIENT")
    payload = {"timezone": "Europe/London"}
    resp = await client.put("/api/v1/patients/me", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["timezone"] == "Europe/London"
