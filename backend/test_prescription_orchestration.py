"""Unit and integration tests for LangGraph prescription orchestration, OCR, and safety verification."""

import pytest
from httpx import AsyncClient
from datetime import date
from sqlalchemy import select

from app.agents.ocr_agent import extract_prescription_text, MOCK_PRESCRIPTION_TEXT
from app.agents.parsing_agent import parse_prescription_text, _heuristic_parse_prescription
from app.agents.safety_agent import verify_prescription_safety
from app.graph.prescription_ingestion import prescription_orchestrator
from app.models.patient import Patient
from app.models.prescription import Prescription
from app.models.prescribed_medication import PrescribedMedication
from app.models.user import User
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_ocr_agent_returns_provided_raw_text():
    """OCR agent should pass through raw text when provided."""
    custom_text = "Dr. Alice\nDate: 2026-11-01\n1. Amoxicillin 500mg - once daily"
    extracted = await extract_prescription_text(raw_text=custom_text)
    assert extracted == custom_text


@pytest.mark.asyncio
async def test_ocr_agent_extracts_from_image_base64():
    """OCR agent returns realistic simulated text when an image payload is provided."""
    fake_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    extracted = await extract_prescription_text(image_base64=fake_b64)
    assert "Metformin" in extracted
    assert "Lisinopril" in extracted


@pytest.mark.asyncio
async def test_ocr_agent_raises_on_empty_input():
    """OCR agent should reject empty inputs."""
    with pytest.raises(ValueError, match="No image or raw text provided"):
        await extract_prescription_text(image_base64=None, raw_text="")


@pytest.mark.asyncio
async def test_parsing_agent_structured_output():
    """Parsing agent should structure raw prescription text into PrescriptionCreate dict."""
    sample_rx = (
        "Dr. Robert Vance, MD\n"
        "City Cardiology Clinic\n"
        "Date: 2026-05-15\n"
        "1. Lisinopril 10mg - 1 tablet once daily for 30 days\n"
        "2. Atorvastatin 20mg - 1 tablet once daily at bedtime for 30 days\n"
    )
    parsed = await parse_prescription_text(sample_rx)
    assert "doctor_name" in parsed
    assert "prescription_date" in parsed
    assert len(parsed["medications"]) >= 2

    med_names = [m["medicine_name"].lower() for m in parsed["medications"]]
    assert any("lisinopril" in name for name in med_names)
    assert any("atorvastatin" in name for name in med_names)


def test_safety_agent_clean_prescription():
    """Safety agent approves safe medication regimen with no contraindications."""
    new_meds = [
        {"medicine_name": "Metformin", "dose": "500mg", "frequency": "twice daily"},
        {"medicine_name": "Lisinopril", "dose": "10mg", "frequency": "once daily"},
    ]
    result = verify_prescription_safety(
        new_medications=new_meds,
        patient_allergies=["pollen"],
        patient_conditions=["hypertension"],
        existing_medications=[],
    )
    assert result["is_safe"] is True
    assert result["risk_level"] == "LOW"
    assert len(result["safety_findings"]) == 0


def test_safety_agent_detects_allergy_contraindication():
    """Safety agent blocks penicillin-class medication when patient has penicillin allergy."""
    new_meds = [
        {"medicine_name": "Amoxicillin", "dose": "500mg", "frequency": "three times daily"},
    ]
    result = verify_prescription_safety(
        new_medications=new_meds,
        patient_allergies=["penicillin"],
        patient_conditions=[],
        existing_medications=[],
    )
    assert result["is_safe"] is False
    assert result["risk_level"] == "CRITICAL"
    assert any("CONTRAINDICATION (ALLERGY)" in f for f in result["safety_findings"])


def test_safety_agent_detects_condition_contraindication():
    """Safety agent flags beta-blockers when patient has active asthma."""
    new_meds = [
        {"medicine_name": "Propranolol", "dose": "40mg", "frequency": "twice daily"},
    ]
    result = verify_prescription_safety(
        new_medications=new_meds,
        patient_allergies=[],
        patient_conditions=["Asthma"],
        existing_medications=[],
    )
    assert result["is_safe"] is False
    assert result["risk_level"] == "CRITICAL"
    assert any("CONTRAINDICATION (CHRONIC_CONDITION)" in f for f in result["safety_findings"])


def test_safety_agent_detects_drug_drug_interaction():
    """Safety agent catches major or contraindicated drug interactions."""
    # Sildenafil + Nitroglycerin
    new_meds = [
        {"medicine_name": "Sildenafil", "dose": "50mg", "frequency": "as needed"},
    ]
    result = verify_prescription_safety(
        new_medications=new_meds,
        patient_allergies=[],
        patient_conditions=[],
        existing_medications=["Nitroglycerin"],
    )
    assert result["is_safe"] is False
    assert result["risk_level"] == "CRITICAL"
    assert any("DRUG INTERACTION (CONTRAINDICATED)" in f for f in result["safety_findings"])


def test_safety_agent_detects_polypharmacy():
    """Safety agent flags polypharmacy warning when active medications exceed 5."""
    new_meds = [
        {"medicine_name": "Metformin"},
        {"medicine_name": "Lisinopril"},
    ]
    existing = ["Amlodipine", "Atorvastatin", "Omeprazole", "Levothyroxine"]
    result = verify_prescription_safety(
        new_medications=new_meds,
        patient_allergies=[],
        patient_conditions=[],
        existing_medications=existing,
    )
    assert any("POLYPHARMACY WARNING" in f for f in result["safety_findings"])


@pytest.mark.asyncio
async def test_langgraph_orchestration_end_to_end():
    """Test full LangGraph StateGraph pipeline execution."""
    fake_b64 = "fake-image-bytes-base64"
    state = await prescription_orchestrator.ainvoke({
        "image_base64": fake_b64,
        "patient_allergies": [],
        "patient_conditions": [],
        "existing_medications": [],
    })
    assert state.get("error") is None
    assert state.get("raw_ocr_text") is not None
    assert state.get("parsed_prescription") is not None
    assert state.get("is_safe") is True


@pytest.mark.asyncio
async def test_upload_prescription_api_success(client: AsyncClient, session):
    """Test POST /api/v1/prescriptions/upload creates pending prescription and parsed meds."""
    # Seed patient user
    user = User(
        name="Rx Test User",
        email="rx_upload_test@example.com",
        hashed_password="hash",
        role="PATIENT",
        token_version=1,
    )
    session.add(user)
    await session.commit()

    patient = Patient(user_id=user.id, allergies=[], chronic_conditions=[])
    session.add(patient)
    await session.commit()

    token = create_access_token(data={"sub": str(user.id)}, token_version=user.token_version)

    headers = {"Authorization": f"Bearer {token}"}
    payload = {"image_base64": "dummy-base64-prescription-image"}

    response = await client.post("/api/v1/prescriptions/upload", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    assert data["patient_id"] == patient.id
    assert data["verification_status"] == "PENDING"
    assert len(data["medications"]) >= 1


@pytest.mark.asyncio
async def test_upload_prescription_api_rejects_contraindicated(client: AsyncClient, session):
    """Test POST /api/v1/prescriptions/upload rejects prescription if contraindicated by safety check."""
    user = User(
        name="Allergic User",
        email="allergic_user@example.com",
        hashed_password="hash",
        role="PATIENT",
        token_version=1,
    )
    session.add(user)
    await session.commit()

    # Patient has penicillin allergy
    patient = Patient(user_id=user.id, allergies=["penicillin"], chronic_conditions=[])
    session.add(patient)
    await session.commit()

    # Patient already on Nitroglycerin
    presc = Prescription(patient_id=patient.id, prescription_date=date.today())
    session.add(presc)
    await session.commit()
    med = PrescribedMedication(
        prescription_id=presc.id,
        patient_id=patient.id,
        medicine_name="Nitroglycerin",
        frequency="as needed",
        is_active=True,
    )
    session.add(med)
    await session.commit()

    token = create_access_token(data={"sub": str(user.id)}, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "raw_ocr_text": (
            "Dr. Jones, MD\n"
            "City Clinic\n"
            "Date: 2026-10-01\n"
            "1. Sildenafil 50mg - 1 tablet as needed for 30 days"
        )
    }
    response = await client.post("/api/v1/prescriptions/upload", json=payload, headers=headers)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Prescription rejected by AI safety check" in detail
    assert "DRUG INTERACTION (CONTRAINDICATED)" in detail
