from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.adherence_analysis_service import AdherenceAnalysisService
from app.analysis.schemas import AdherenceAnalysisResult
from app.dependencies import get_current_user, get_db
from app.models.medication_event import MedicationEvent
from app.models.patient import Patient
from app.models.user import User
from app.schemas.adherence import (
    AdherenceMetricsResponse,
    DoseLogCreate,
    DoseLogResponse,
)
from app.services import adherence_service, reminder_service

router = APIRouter()


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Get comprehensive deterministic adherence metrics, streaks, patterns, and escalation flags.
    """
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
    if patient_id is not None and current_user.role == "CLINICIAN":
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

    review = await _adherence_analysis.evaluate_and_generate(
        db=db,
        patient_id=patient.id,
        days=days,
    )
    return review


