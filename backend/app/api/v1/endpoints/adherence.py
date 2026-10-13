from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.adherence_analysis_service import AdherenceAnalysisService
from app.analysis.schemas import AdherenceAnalysisResult
from app.dependencies import get_current_user, get_db, verify_patient_access
from app.models.medication_event import MedicationEvent, MedicationEventStatus
from app.models.medication_event_correction import MedicationEventCorrection
from app.models.patient import Patient
from app.models.types import utcnow
from app.models.user import User
from app.schemas.adherence import (
    AdherenceMetricsResponse,
    DoseLogCreate,
    DoseLogResponse,
)
from app.schemas.auth import UserRole
from app.services import adherence_service, reminder_service

router = APIRouter()


class EventCorrectionRequest(BaseModel):
    """Clinician request to correct a mislogged dose event."""
    new_status: str = Field(
        description="The corrected status: TAKEN, SKIPPED, or MISSED."
    )
    reason: str = Field(
        min_length=3,
        max_length=255,
        description="Mandatory clinical reason for the correction."
    )


class EventCorrectionResponse(BaseModel):
    """Confirmation of a dose event correction with audit trail."""
    correction_id: int
    event_id: int
    previous_status: str
    new_status: str
    corrected_by: Optional[int]
    corrected_at: str
    reason: str


@router.post("/log", response_model=DoseLogResponse, status_code=status.HTTP_201_CREATED)
async def log_dose(
    log_data: DoseLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Log a dose event (TAKEN, SKIPPED, SNOOZED).
    
    The backend authoritatively derives the scheduled instant from the schedule/reminder.
    """
    result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=400, detail="User is not a patient")

    try:
        dose_event = await reminder_service.record_patient_response(
            db=db,
            patient_id=patient.id,
            schedule_id=log_data.schedule_id,
            action=log_data.status,
            reminder_id=log_data.reminder_id,
            skip_reason=log_data.skip_reason,
            skip_reason_code=(
                log_data.skip_reason_code.value if log_data.skip_reason_code else None
            ),
        )
        await db.commit()
        await db.refresh(dose_event)
        return dose_event
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/score", response_model=AdherenceMetricsResponse)
async def get_adherence_score(
    period: str = "7d",
    patient_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Get comprehensive deterministic adherence metrics, streaks, patterns, and escalation flags.
    """
    if patient_id is not None and current_user.role in (UserRole.CLINICIAN.value, UserRole.ADMIN.value):
        result = await db.execute(select(Patient).where(Patient.id == patient_id))
        patient = result.scalars().first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
    else:
        result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        patient = result.scalars().first()
        if not patient:
            raise HTTPException(status_code=400, detail="User is not a patient")

    days_map = {"7d": 7, "14d": 14, "30d": 30}
    days = days_map.get(period.lower(), 7)

    metrics = await adherence_service.calculate_adherence_score(
        session=db,
        patient_id=patient.id,
        days=days,
    )
    return metrics


_adherence_analysis = AdherenceAnalysisService()


@router.get("/analysis", response_model=AdherenceAnalysisResult)
async def get_adherence_analysis(
    period: str = "7d",
    patient_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Deterministic adherence analysis: patient explanation, barrier assessment and
    clinician brief, composed from the safety assessment, the adherence metrics and
    retrieved clinical evidence.

    This is not AI and not an LLM — there is no model call in the pipeline. Output is
    reproducible for identical inputs. Deterministic safety invariants (risk level,
    human-review flag) and evidence citations are preserved exactly as the rules
    """
    if current_user.role in (UserRole.CLINICIAN.value, UserRole.ADMIN.value):
        if patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_id query parameter is required for clinicians and administrators",
            )
        patient = await verify_patient_access(patient_id=patient_id, current_user=current_user, db=db)
    elif current_user.role == UserRole.PATIENT.value:
        result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
        caller_patient = result.scalars().first()
        if not caller_patient:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not a patient")
        if patient_id is not None and patient_id != caller_patient.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients cannot access other patients' analysis",
            )
        patient = caller_patient
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access adherence analysis",
        )

    days_map = {"7d": 7, "14d": 14, "30d": 30}
    days = days_map.get(period.lower(), 7)

    review = await _adherence_analysis.evaluate_and_generate(
        db=db,
        patient_id=patient.id,
        days=days,
    )
    return review


@router.post(
    "/events/{event_id}/correct",
    response_model=EventCorrectionResponse,
    status_code=status.HTTP_200_OK,
)
async def correct_event(
    event_id: int,
    correction: EventCorrectionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Correct a previously logged dose event and record an immutable audit row.

    Only assigned clinicians (or administrators) can correct events.
    Does not allow correcting to the same status (no-op corrections pollute
    the audit trail with entries that changed nothing).
    """
    if current_user.role not in (UserRole.CLINICIAN.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinicians can correct dose events",
        )

    # Validate new_status
    valid_statuses = {s.value for s in MedicationEventStatus}
    if correction.new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{correction.new_status}'. Must be one of: {sorted(valid_statuses)}",
        )

    # Fetch the event with row-level lock
    result = await db.execute(
        select(MedicationEvent).where(MedicationEvent.id == event_id).with_for_update()
    )
    event = result.scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Medication event not found")

    # Authorize clinician / admin for the patient who owns this event
    await verify_patient_access(patient_id=event.patient_id, current_user=current_user, db=db)

    if event.status == correction.new_status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Event is already {correction.new_status}; no change needed",
        )

    previous_status = event.status
    now = utcnow()

    # Write audit row
    audit = MedicationEventCorrection(
        event_id=event.id,
        previous_status=previous_status,
        new_status=correction.new_status,
        corrected_by=current_user.id,
        corrected_at=now,
        reason=correction.reason,
    )
    db.add(audit)

    # Update the event in place
    event.status = correction.new_status
    if correction.new_status == MedicationEventStatus.TAKEN.value:
        event.confirmed_at = now

    try:
        await db.commit()
        await db.refresh(audit)
    except Exception:
        await db.rollback()
        raise

    return EventCorrectionResponse(
        correction_id=audit.id,
        event_id=event.id,
        previous_status=previous_status,
        new_status=correction.new_status,
        corrected_by=current_user.id,
        corrected_at=now.isoformat(),
        reason=correction.reason,
    )
