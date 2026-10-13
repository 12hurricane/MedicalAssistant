from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Any, List, Optional
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from app.schemas.prescription import (
    MedicationReconciliationSummary,
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionVerify,
    PrescriptionVerifyResponse,
    ScheduleGenerationSummary,
)
from app.models.prescription import Prescription
from app.models.prescribed_medication import PrescribedMedication
from app.models.patient import Patient
from app.schemas.auth import UserRole
from app.dependencies import get_db, get_current_user, require_role
from app.models.user import User
from app.models.types import utcnow
from app.services import prescription_service, schedule_service
from app.services.schedule_service import UnschedulableMedicationsError
from pydantic import BaseModel
from app.graph.prescription_ingestion import prescription_orchestrator

class PrescriptionUploadRequest(BaseModel):
    image_base64: Optional[str] = None
    raw_ocr_text: Optional[str] = None

router = APIRouter()

@router.post("/upload", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
async def upload_prescription(
    upload_data: PrescriptionUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Upload prescription image or text and process via LangGraph OCR orchestration."""
    result = await db.execute(select(Patient).filter(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=400, detail="User is not a patient")

    active_meds_res = await db.execute(
        select(PrescribedMedication.medicine_name).filter(
            PrescribedMedication.patient_id == patient.id,
            PrescribedMedication.is_active.is_(True),
        )
    )
    existing_meds = [row[0] for row in active_meds_res.all()]

    state = await prescription_orchestrator.ainvoke({
        "image_base64": upload_data.image_base64,
        "raw_ocr_text": upload_data.raw_ocr_text,
        "patient_id": patient.id,
        "patient_allergies": patient.allergies or [],
        "patient_conditions": patient.chronic_conditions or [],
        "existing_medications": existing_meds,
    })

    if state.get("error"):
        raise HTTPException(status_code=422, detail=state["error"])

    if not state.get("is_safe"):
        findings = "; ".join(state.get("safety_findings", []))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prescription rejected by AI safety check: {findings}",
        )

    parsed = state.get("parsed_prescription")
    if not parsed:
        raise HTTPException(status_code=422, detail="Failed to parse prescription data")

    presc_data = PrescriptionCreate(**parsed)
    prescription_dict = presc_data.model_dump(exclude={"medications"})
    prescription = Prescription(
        patient_id=patient.id,
        verification_status="PENDING",
        raw_ocr_text=state.get("raw_ocr_text"),
        **prescription_dict,
    )

    db.add(prescription)
    await db.flush()

    for med_data in presc_data.medications:
        med = PrescribedMedication(
            prescription_id=prescription.id,
            patient_id=patient.id,
            **med_data.model_dump(),
        )
        db.add(med)

    await db.commit()
    await db.refresh(prescription)
    
    stmt = select(Prescription).options(selectinload(Prescription.medications)).filter(Prescription.id == prescription.id)
    result = await db.execute(stmt)
    return result.scalars().first()


def _today_for_patient(patient: Patient) -> date:
    """
    Today's date in the patient's own timezone.

    Dose times are local to the patient, so "starts today" has to mean their today,
    not the server's — a server in UTC would otherwise start an evening dose a day
    late for a patient in Asia/Kolkata. Falls back to UTC if the stored IANA name
    is unusable, since a bad timezone string must not block verification.
    """
    try:
        tz = ZoneInfo(patient.timezone or "UTC")
    except (KeyError, ValueError, OSError):
        # ZoneInfoNotFoundError subclasses KeyError.
        tz = timezone.utc
    return datetime.now(tz).date()


@router.post("", response_model=PrescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    presc_data: PrescriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Create prescription manually."""
    # Ensure current user is a patient
    result = await db.execute(select(Patient).filter(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=400, detail="User is not a patient")
        
    prescription_dict = presc_data.model_dump(exclude={"medications"})
    prescription = Prescription(patient_id=patient.id, verification_status="PENDING", **prescription_dict)
    
    db.add(prescription)
    await db.flush()  # To get the ID
    
    for med_data in presc_data.medications:
        # patient_id is derived from the authenticated patient, never trusted from the client
        med = PrescribedMedication(
            prescription_id=prescription.id,
            patient_id=patient.id,
            **med_data.model_dump(),
        )
        db.add(med)
        
    await db.commit()
    await db.refresh(prescription)
    
    # Reload with medications relationship if needed, assuming lazy="selectin" in model
    stmt = select(Prescription).options(selectinload(Prescription.medications)).filter(Prescription.id == prescription.id)
    result = await db.execute(stmt)
    return result.scalars().first()

@router.get("", response_model=List[PrescriptionResponse])
async def list_prescriptions(
    patient_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """List patient's prescriptions (or specific patient's prescriptions for clinicians/admins)."""
    if patient_id is not None and current_user.role in (UserRole.CLINICIAN.value, UserRole.ADMIN.value):
        target_patient_id = patient_id
    else:
        result = await db.execute(select(Patient).filter(Patient.user_id == current_user.id))
        patient = result.scalars().first()
        if not patient:
            return []
        target_patient_id = patient.id
        
    stmt = select(Prescription).options(selectinload(Prescription.medications)).filter(Prescription.patient_id == target_patient_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{id}", response_model=PrescriptionResponse)
async def get_prescription(
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get prescription by ID."""
    stmt = select(Prescription).options(selectinload(Prescription.medications)).filter(Prescription.id == id)
    result = await db.execute(stmt)
    prescription = result.scalars().first()
    
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    
    # Simple auth check
    if current_user.role == "PATIENT":
        result = await db.execute(select(Patient).filter(Patient.user_id == current_user.id))
        patient = result.scalars().first()
        if not patient or prescription.patient_id != patient.id:
            raise HTTPException(status_code=403, detail="Not authorized")
            
    return prescription

@router.put("/{id}/verify", response_model=PrescriptionVerifyResponse)
async def verify_prescription(
    id: int,
    verify_data: PrescriptionVerify,
    # Same substitution as patients.py: the boundary moves out of the body and onto the
    # signature, and the vocabulary comes from the enum rather than from a string
    # literal. `require_role` returns the authenticated user, so the audit trail below
    # still has a caller to attribute the sign-off to.
    current_user: User = Depends(
        require_role(UserRole.CLINICIAN.value, UserRole.ADMIN.value)
    ),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Verify/approve prescription (Clinician/Admin only).

    Verification is the point at which dose times become real: an approved
    prescription generates its MedicationSchedule rows here. If any medication's
    frequency cannot be turned into concrete times, the whole request is rejected
    with 422 and nothing is persisted — a prescription is never left marked
    VERIFIED with no schedule behind it.
    """
    stmt = (
        select(Prescription)
        .options(
            selectinload(Prescription.medications),
            selectinload(Prescription.patient),
        )
        .filter(Prescription.id == id)
    )
    result = await db.execute(stmt)
    prescription = result.scalars().first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    prescription.verification_status = "VERIFIED" if verify_data.verified else "REJECTED"
    # Audit trail: record which clinician signed off, and when
    prescription.verified_by = current_user.id
    prescription.verified_at = utcnow()

    # Handle corrections if provided
    reconciliation = None
    if verify_data.corrections:
        # Reconciled, not replaced. Clearing the collection would delete the old
        # PrescribedMedication rows, and delete-orphan cascades from there into
        # medication_schedules and then medication_events — the patient's entire
        # adherence history for this prescription. See prescription_service.
        try:
            reconciliation = prescription_service.reconcile_medications(
                prescription, verify_data.corrections
            )
        except prescription_service.DuplicateCorrectionError as exc:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
        # Flush so newly added medications have primary keys for schedules to
        # point at, and so deactivations are visible to schedule generation.
        await db.flush()

    summary = None
    if verify_data.verified:
        try:
            generated = await schedule_service.generate_schedules(
                db, prescription, start_date=_today_for_patient(prescription.patient)
            )
        except UnschedulableMedicationsError as exc:
            # Roll back so verification_status is not persisted. The prescription
            # stays unverified and goes back to a human, which is the entire point
            # of refusing to guess an interval.
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": (
                        "Not verified: these medications have a frequency that cannot "
                        "be turned into dose times, and need human review."
                    ),
                    "unschedulable": exc.unmapped,
                },
            )
        summary = ScheduleGenerationSummary(
            created=generated.created,
            reactivated=generated.reactivated,
            deactivated=generated.deactivated,
            unchanged=generated.unchanged,
            active_total=generated.active_total,
            as_needed=generated.as_needed,
        )
    else:
        # A rejected prescription must stop firing reminders. Cancelled, not superseded:
        # nothing is replacing these doses, the decision was not to take them.
        await schedule_service.cancel_schedules(db, prescription)

    await db.commit()

    # Reload
    stmt = select(Prescription).options(selectinload(Prescription.medications)).filter(Prescription.id == id)
    result = await db.execute(stmt)
    fresh = result.scalars().first()
    return PrescriptionVerifyResponse(
        **PrescriptionResponse.model_validate(fresh).model_dump(),
        scheduling=summary,
        reconciliation=(
            MedicationReconciliationSummary(
                unchanged=reconciliation.unchanged,
                added=reconciliation.added,
                reactivated=reconciliation.reactivated,
                discontinued=reconciliation.discontinued,
                active_total=reconciliation.active_total,
            )
            if reconciliation is not None
            else None
        ),
    )

