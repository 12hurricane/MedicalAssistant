"""Phase 9 Step 1 & Step 2: Real ASGI HTTP Integration Tests for Adherence Analysis API & Event Correction.

Tests:
1. GET /api/v1/adherence/analysis
   - Patient accessing own analysis (200 OK)
   - Patient attempting to access another patient's analysis via ?patient_id= (403 Forbidden)
   - Patient supplying foreign patient_id does NOT silently fall back to own record
   - Assigned clinician accessing assigned patient (200 OK)
   - Unassigned clinician accessing unassigned patient (403 Forbidden)
   - Clinician accessing without required patient_id query parameter (400 Bad Request)
   - Admin accessing existing patient (200 OK)
   - Nonexistent patient ID (404 Not Found)
   - Unauthenticated request (401 Unauthorized)
   - Data isolation: denied requests contain zero clinical, metric, evidence, quote, or AI fields
   - Period parameter behavior (7d, 14d, 30d, invalid)
   - LLM fallback preservation (200 OK with GenerationStatus.FALLBACK, safety findings intact)

2. POST /api/v1/adherence/events/{event_id}/correct
   - Assigned clinician correcting event (200 OK, event updated, audit row created)
   - Unassigned clinician attempting correction (403 Forbidden, event untouched, zero audit rows)
   - Admin correcting event (200 OK)
   - Patient attempting correction (403 Forbidden)
   - Unauthenticated request (401 Unauthorized)
   - Nonexistent event ID (404 Not Found)
   - Invalid status string (422 Unprocessable Entity)
   - No-op correction to identical status (422 Unprocessable Entity)
   - Domain semantics check: clinician_confirmed / verifying_clinician_id preserved
"""

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.analysis.schemas import GenerationStatus
from app.llm.client import LLMUnavailable
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
# Test Fixtures & Setup Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_fast_llm_for_auth_tests(monkeypatch):
    """Provide an immediate mock response for extraction so authorization tests run in <1s.

    Preserves full RAG, response validation, merge, and HTTP serialisation boundaries
    without triggering 50s CPU Ollama inference for pure access-control assertions.
    """
    async def _fast_gen(*args, **kwargs):
        return '{"barrier_context": []}', "GENERATED_OLLAMA"

    monkeypatch.setattr(
        "app.analysis.adherence_analysis_service.get_generative_response",
        _fast_gen,
    )


async def _setup_clinical_scenario(client):
    """Seed two distinct patients, medication history, schedules, and assignments.

    - Patient A: Has 2 logged doses (1 TAKEN, 1 SKIPPED with secret skip text)
    - Patient B: Has 1 logged dose (1 MISSED with confidential skip text)
    - Clinician 1: Assigned to Patient A via ClinicianPatientAssignment
    - Clinician 2: NOT assigned to Patient A
    - Admin: Superuser with system-wide access
    """
    headers_pat_a = await register(client, "patient_a@example.com", role="PATIENT")
    headers_pat_b = await register(client, "patient_b@example.com", role="PATIENT")
    headers_clin_1 = await register(client, "clinician_1@example.com", role="CLINICIAN")
    headers_clin_2 = await register(client, "clinician_2@example.com", role="CLINICIAN")
    headers_admin = await _bootstrap_admin_headers(client)

    async with _session_for(client) as session:
        # Fetch Patient A & User
        user_a = (
            await session.execute(select(User).where(User.email == "patient_a@example.com"))
        ).scalars().one()
        pat_a = (
            await session.execute(select(Patient).where(Patient.user_id == user_a.id))
        ).scalars().one()
        pat_a.timezone = "UTC"

        # Fetch Patient B & User
        user_b = (
            await session.execute(select(User).where(User.email == "patient_b@example.com"))
        ).scalars().one()
        pat_b = (
            await session.execute(select(Patient).where(Patient.user_id == user_b.id))
        ).scalars().one()
        pat_b.timezone = "UTC"

        # Fetch Clinician Users
        user_c1 = (
            await session.execute(select(User).where(User.email == "clinician_1@example.com"))
        ).scalars().one()
        user_c2 = (
            await session.execute(select(User).where(User.email == "clinician_2@example.com"))
        ).scalars().one()

        # Create Medication & Prescription for Patient A
        med_a = Medication(
            brand_name="Coumadin",
            generic_name="Warfarin Sodium",
            standard_strength="5mg",
            dosage_form="tablet",
        )
        session.add(med_a)
        await session.flush()

        rx_a = Prescription(
            patient_id=pat_a.id,
            doctor_name="Dr. Smith",
            prescription_date=date(2026, 1, 1),
            verification_status="VERIFIED",
        )
        session.add(rx_a)
        await session.flush()

        pm_a = PrescribedMedication(
            prescription_id=rx_a.id,
            patient_id=pat_a.id,
            medication_id=med_a.id,
            medicine_name="Coumadin",
            dose="5mg",
            frequency="once daily",
        )
        session.add(pm_a)
        await session.flush()

        sched_a = MedicationSchedule(
            patient_id=pat_a.id,
            prescribed_medication_id=pm_a.id,
            scheduled_time=time(9, 0),
            start_date=date(2026, 1, 1),
            status=ScheduleLifecycle.ACTIVE.value,
        )
        session.add(sched_a)
        await session.flush()

        # Events for Patient A
        ev_a1 = MedicationEvent(
            schedule_id=sched_a.id,
            patient_id=pat_a.id,
            scheduled_at=datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc),
            status=MedicationEventStatus.TAKEN.value,
            confirmed_at=datetime(2026, 9, 20, 9, 5, tzinfo=timezone.utc),
            recorded_by="PATIENT",
        )
        ev_a2 = MedicationEvent(
            schedule_id=sched_a.id,
            patient_id=pat_a.id,
            scheduled_at=datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc),
            status=MedicationEventStatus.SKIPPED.value,
            skip_reason="Patient A secret skip reason: procedure scheduled",
            skip_reason_code="CLINICIAN_INSTRUCTED",
            recorded_by="PATIENT",
        )
        session.add_all([ev_a1, ev_a2])
        await session.flush()

        # Create Medication & Event for Patient B
        med_b = Medication(
            brand_name="Glucophage",
            generic_name="Metformin HCl",
            standard_strength="500mg",
            dosage_form="tablet",
        )
        session.add(med_b)
        await session.flush()

        rx_b = Prescription(
            patient_id=pat_b.id,
            doctor_name="Dr. Jones",
            prescription_date=date(2026, 1, 1),
            verification_status="VERIFIED",
        )
        session.add(rx_b)
        await session.flush()

        pm_b = PrescribedMedication(
            prescription_id=rx_b.id,
            patient_id=pat_b.id,
            medication_id=med_b.id,
            medicine_name="Glucophage",
            dose="500mg",
            frequency="once daily",
        )
        session.add(pm_b)
        await session.flush()

        sched_b = MedicationSchedule(
            patient_id=pat_b.id,
            prescribed_medication_id=pm_b.id,
            scheduled_time=time(12, 0),
            start_date=date(2026, 1, 1),
            status=ScheduleLifecycle.ACTIVE.value,
        )
        session.add(sched_b)
        await session.flush()

        ev_b1 = MedicationEvent(
            schedule_id=sched_b.id,
            patient_id=pat_b.id,
            scheduled_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
            status=MedicationEventStatus.MISSED.value,
            skip_reason="Patient B confidential note: severe financial hardship",
            skip_reason_code="COST",
            recorded_by="PATIENT",
        )
        session.add(ev_b1)
        await session.flush()

        # Create Clinician 1 Assignment to Patient A only
        assignment = ClinicianPatientAssignment(
            clinician_id=user_c1.id,
            patient_id=pat_a.id,
            assigned_at=utcnow(),
        )
        session.add(assignment)
        await session.commit()

        return {
            "pat_a_id": pat_a.id,
            "pat_b_id": pat_b.id,
            "ev_a1_id": ev_a1.id,
            "ev_a2_id": ev_a2.id,
            "ev_b1_id": ev_b1.id,
            "clin_1_user_id": user_c1.id,
            "clin_2_user_id": user_c2.id,
            "headers_pat_a": headers_pat_a,
            "headers_pat_b": headers_pat_b,
            "headers_clin_1": headers_clin_1,
            "headers_clin_2": headers_clin_2,
            "headers_admin": headers_admin,
        }


# ===========================================================================
# 1. GET /api/v1/adherence/analysis Authorization Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_patient_can_access_own_adherence_analysis(client):
    """1. Patient accessing their own adherence analysis returns 200 OK."""
    data = await _setup_clinical_scenario(client)

    response = await client.get("/api/v1/adherence/analysis", headers=data["headers_pat_a"])
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    body = response.json()

    assert body["patient_id"] == data["pat_a_id"]
    assert "safety_risk_level" in body
    assert "requires_human_review" in body
    assert "patient_explanation" in body
    assert "clinical_brief" in body


@pytest.mark.asyncio
async def test_patient_cannot_access_another_patients_analysis(client):
    """2 & 3. Patient supplying another patient's ID must be rejected with 403, NOT fall back."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        f"/api/v1/adherence/analysis?patient_id={data['pat_b_id']}",
        headers=data["headers_pat_a"],
    )

    assert response.status_code == 403, (
        f"Security violation: Patient was able to request another patient's analysis! "
        f"Expected 403 Forbidden, got {response.status_code}"
    )

    body = response.text
    assert "Patient B confidential note" not in body
    assert "financial hardship" not in body
    assert str(data["pat_b_id"]) not in body


@pytest.mark.asyncio
async def test_authorized_clinician_can_access_assigned_patient_analysis(client):
    """4. Assigned clinician accessing assigned patient returns 200 OK."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        f"/api/v1/adherence/analysis?patient_id={data['pat_a_id']}",
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    body = response.json()

    assert body["patient_id"] == data["pat_a_id"]
    assert "clinical_brief" in body
    assert "safety_risk_level" in body


@pytest.mark.asyncio
async def test_unauthorized_clinician_cannot_access_unassigned_patient_analysis(client):
    """5. Unassigned clinician accessing unassigned patient must be rejected with 403 Forbidden."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        f"/api/v1/adherence/analysis?patient_id={data['pat_a_id']}",
        headers=data["headers_clin_2"],
    )

    assert response.status_code == 403, (
        f"Access control failure: Unassigned clinician was granted access to Patient A! "
        f"Expected 403 Forbidden, got {response.status_code}: {response.text}"
    )

    body = response.text
    assert "Patient A secret skip reason" not in body
    assert "Warfarin" not in body
    assert "clinical_brief" not in body


@pytest.mark.asyncio
async def test_clinician_without_patient_id_rejected(client):
    """6. Clinician requesting analysis without required patient_id returns 400 Bad Request."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        "/api/v1/adherence/analysis",
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 400, f"Expected 400 Bad Request, got {response.status_code}: {response.text}"
    assert "patient_id" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_can_access_any_patient_analysis(client):
    """7. Admin accessing an existing patient returns 200 OK."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        f"/api/v1/adherence/analysis?patient_id={data['pat_a_id']}",
        headers=data["headers_admin"],
    )
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["patient_id"] == data["pat_a_id"]


@pytest.mark.asyncio
async def test_nonexistent_patient_returns_404(client):
    """8. Request for nonexistent patient_id returns 404 Not Found."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        "/api/v1/adherence/analysis?patient_id=99999",
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 404, f"Expected 404 Not Found, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client):
    """9. Unauthenticated request returns 401 Unauthorized."""
    response = await client.get("/api/v1/adherence/analysis")
    assert response.status_code == 401, f"Expected 401 Unauthorized, got {response.status_code}"


@pytest.mark.asyncio
async def test_data_isolation_on_all_denied_responses(client):
    """10. Verify that all denied responses contain zero clinical, metric, evidence, or AI fields."""
    data = await _setup_clinical_scenario(client)

    denied_calls = [
        # Unauthenticated
        client.get("/api/v1/adherence/analysis"),
        # Patient A accessing Patient B
        client.get(f"/api/v1/adherence/analysis?patient_id={data['pat_b_id']}", headers=data["headers_pat_a"]),
        # Unassigned Clinician accessing Patient A
        client.get(f"/api/v1/adherence/analysis?patient_id={data['pat_a_id']}", headers=data["headers_clin_2"]),
        # Clinician without patient_id
        client.get("/api/v1/adherence/analysis", headers=data["headers_clin_1"]),
        # Nonexistent patient
        client.get("/api/v1/adherence/analysis?patient_id=99999", headers=data["headers_clin_1"]),
        # Invalid Bearer Token
        client.get("/api/v1/adherence/analysis", headers={"Authorization": "Bearer invalid.token.value"}),
    ]

    forbidden_clinical_keys = [
        "safety_risk_level",
        "requires_human_review",
        "recommended_action",
        "patient_explanation",
        "clinical_brief",
        "possible_barriers",
        "citations",
        "concerning_patterns",
    ]

    for req_coro in denied_calls:
        resp = await req_coro
        assert resp.status_code in (400, 401, 403, 404), f"Unexpected status: {resp.status_code}"
        body = resp.text

        for key in forbidden_clinical_keys:
            assert f'"{key}"' not in body, f"Data leakage detected for key '{key}' in denied response: {body}"

        assert "secret skip reason" not in body
        assert "confidential note" not in body


@pytest.mark.asyncio
async def test_supported_period_parameters(client):
    """Supported periods (7d, 14d, 30d) execute successfully."""
    data = await _setup_clinical_scenario(client)

    for p in ["7d", "14d", "30d", "7D", "14D", "30D"]:
        response = await client.get(
            f"/api/v1/adherence/analysis?period={p}",
            headers=data["headers_pat_a"],
        )
        assert response.status_code == 200, f"Period {p} failed with {response.status_code}: {response.text}"
        body = response.json()
        assert body["patient_id"] == data["pat_a_id"]


@pytest.mark.asyncio
async def test_invalid_period_parameter_handling(client):
    """Unsupported or malformed period parameters default safely or reject."""
    data = await _setup_clinical_scenario(client)

    response = await client.get(
        "/api/v1/adherence/analysis?period=invalid_period_999d",
        headers=data["headers_pat_a"],
    )
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        body = response.json()
        assert body["patient_id"] == data["pat_a_id"]


@pytest.mark.asyncio
async def test_llm_failure_triggers_fallback_and_retains_safety_findings(client):
    """When the generative model fails, the HTTP endpoint returns GenerationStatus.FALLBACK with intact safety."""
    data = await _setup_clinical_scenario(client)

    with patch(
        "app.analysis.adherence_analysis_service.get_generative_response",
        new=AsyncMock(side_effect=LLMUnavailable("Ollama timed out during inference")),
    ):
        response = await client.get(
            "/api/v1/adherence/analysis",
            headers=data["headers_pat_a"],
        )

        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
        body = response.json()

        assert body["generation_status"] == GenerationStatus.FALLBACK.value
        assert body["clinical_brief"]["generation_status"] == GenerationStatus.FALLBACK.value
        assert "safety_risk_level" in body
        assert isinstance(body["requires_human_review"], bool)
        assert body["validation_passed"] is True
        cb = body["clinical_brief"]
        assert "trend" in cb["insights"]
        assert isinstance(cb["insights"]["concerning_patterns"], list)
        assert isinstance(cb["insights"]["possible_barriers"], list)
        assert isinstance(cb["citations"], list)


# ===========================================================================
# 2. POST /api/v1/adherence/events/{event_id}/correct Authorization Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_correction_assigned_clinician_allowed(client):
    """Assigned clinician correcting an event is authorized; event updates and audit record is created."""
    data = await _setup_clinical_scenario(client)

    payload = {
        "new_status": "TAKEN",
        "reason": "Patient called confirming dose was taken at 9:15 AM",
    }
    response = await client.post(
        f"/api/v1/adherence/events/{data['ev_a2_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    body = response.json()

    assert body["event_id"] == data["ev_a2_id"]
    assert body["previous_status"] == "SKIPPED"
    assert body["new_status"] == "TAKEN"
    assert body["reason"] == payload["reason"]
    assert body["corrected_by"] == data["clin_1_user_id"]

    # Verify database state
    async with _session_for(client) as session:
        ev = (
            await session.execute(select(MedicationEvent).where(MedicationEvent.id == data["ev_a2_id"]))
        ).scalars().one()
        assert ev.status == "TAKEN"
        assert ev.confirmed_at is not None

        # Domain semantics verification: correction does NOT falsely claim clinical verification
        assert ev.clinician_confirmed is False
        assert ev.verifying_clinician_id is None

        # Audit row verification
        audit = (
            await session.execute(
                select(MedicationEventCorrection).where(MedicationEventCorrection.event_id == data["ev_a2_id"])
            )
        ).scalars().one()
        assert audit.previous_status == "SKIPPED"
        assert audit.new_status == "TAKEN"
        assert audit.corrected_by == data["clin_1_user_id"]
        assert audit.reason == payload["reason"]


@pytest.mark.asyncio
async def test_correction_unassigned_clinician_rejected(client):
    """Unassigned clinician attempting correction must be rejected with 403; event untouched, 0 audit rows."""
    data = await _setup_clinical_scenario(client)

    payload = {
        "new_status": "TAKEN",
        "reason": "Unauthorized clinician attempting event edit",
    }
    response = await client.post(
        f"/api/v1/adherence/events/{data['ev_a2_id']}/correct",
        json=payload,
        headers=data["headers_clin_2"],
    )
    assert response.status_code == 403, (
        f"Security violation: Unassigned clinician was allowed to correct Patient A's event! "
        f"Expected 403, got {response.status_code}: {response.text}"
    )

    # Invariant: Event must remain untouched, zero audit rows created
    async with _session_for(client) as session:
        ev = (
            await session.execute(select(MedicationEvent).where(MedicationEvent.id == data["ev_a2_id"]))
        ).scalars().one()
        assert ev.status == "SKIPPED"  # Status unchanged

        audit_count = (
            await session.execute(
                select(func.count()).select_from(MedicationEventCorrection).where(
                    MedicationEventCorrection.event_id == data["ev_a2_id"]
                )
            )
        ).scalar()
        assert audit_count == 0, "Audit record was erroneously created on rejected correction!"


@pytest.mark.asyncio
async def test_correction_admin_allowed(client):
    """Admin correcting an event is authorized by role."""
    data = await _setup_clinical_scenario(client)

    payload = {
        "new_status": "MISSED",
        "reason": "Administrative correction for testing",
    }
    response = await client.post(
        f"/api/v1/adherence/events/{data['ev_a1_id']}/correct",
        json=payload,
        headers=data["headers_admin"],
    )
    assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["event_id"] == data["ev_a1_id"]
    assert body["new_status"] == "MISSED"


@pytest.mark.asyncio
async def test_correction_patient_rejected(client):
    """Patients cannot call the correction endpoint (403 Forbidden)."""
    data = await _setup_clinical_scenario(client)

    payload = {"new_status": "TAKEN", "reason": "Patient attempting self-correction"}
    response = await client.post(
        f"/api/v1/adherence/events/{data['ev_a2_id']}/correct",
        json=payload,
        headers=data["headers_pat_a"],
    )
    assert response.status_code == 403, f"Expected 403 Forbidden, got {response.status_code}"


@pytest.mark.asyncio
async def test_correction_unauthenticated_rejected(client):
    """Unauthenticated correction request returns 401 Unauthorized."""
    payload = {"new_status": "TAKEN", "reason": "Anonymous attempt"}
    response = await client.post("/api/v1/adherence/events/1/correct", json=payload)
    assert response.status_code == 401, f"Expected 401 Unauthorized, got {response.status_code}"


@pytest.mark.asyncio
async def test_correction_nonexistent_event_returns_404(client):
    """Correction request for nonexistent event returns 404 Not Found."""
    data = await _setup_clinical_scenario(client)

    payload = {"new_status": "TAKEN", "reason": "Nonexistent event"}
    response = await client.post(
        "/api/v1/adherence/events/99999/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 404, f"Expected 404 Not Found, got {response.status_code}"


@pytest.mark.asyncio
async def test_correction_invalid_status_returns_422(client):
    """Correction request with invalid status value returns 422 Unprocessable Entity."""
    data = await _setup_clinical_scenario(client)

    payload = {"new_status": "INVALID_STATUS_VALUE", "reason": "Invalid status test"}
    response = await client.post(
        f"/api/v1/adherence/events/{data['ev_a2_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 422, f"Expected 422 Unprocessable Entity, got {response.status_code}"


@pytest.mark.asyncio
async def test_correction_noop_status_returns_422(client):
    """No-op correction to the identical status returns 422 Unprocessable Entity."""
    data = await _setup_clinical_scenario(client)

    # ev_a1 is already TAKEN
    payload = {"new_status": "TAKEN", "reason": "No-op identical status test"}
    response = await client.post(
        f"/api/v1/adherence/events/{data['ev_a1_id']}/correct",
        json=payload,
        headers=data["headers_clin_1"],
    )
    assert response.status_code == 422, f"Expected 422 Unprocessable Entity, got {response.status_code}"
    assert "already taken" in response.json()["detail"].lower()
