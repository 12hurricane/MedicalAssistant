from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Any
from app.schemas.patient import PatientResponse, PatientUpdate
from app.schemas.auth import UserRole
from app.models.patient import Patient
from app.dependencies import get_db, get_current_user, require_role
from app.models.user import User

router = APIRouter()

@router.get("/me", response_model=PatientResponse)
async def get_current_patient(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get current patient's profile."""
    result = await db.execute(select(Patient).filter(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    return patient

@router.put("/me", response_model=PatientResponse)
async def update_current_patient(
    patient_data: PatientUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Update current patient's profile."""
    result = await db.execute(select(Patient).filter(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    
    update_data = patient_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(patient, key, value)
        
    await db.commit()
    await db.refresh(patient)
    return patient

from app.rules.safety_assessment import evaluate_patient_safety
from app.schemas.safety import SafetyAssessmentResponse


@router.get("/me/safety", response_model=SafetyAssessmentResponse)
async def get_my_safety_assessment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get current patient's clinical safety assessment."""
    result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")

    assessment = await evaluate_patient_safety(db, patient.id)
    return assessment


@router.get("/{patient_id}/safety", response_model=SafetyAssessmentResponse)
async def get_patient_safety_assessment(
    patient_id: int,
    # The role boundary is a dependency, not four lines of handler body.
    #
    # This read `if current_user.role not in ["ADMIN", "DOCTOR", "CAREGIVER"]`. Two
    # problems, beyond the retired vocabulary: bare strings in a list are invisible to
    # a rename (which is how DOCTOR survived here while everything around it said
    # clinician), and an in-body check appears nowhere in the OpenAPI schema, so the
    # generated client cannot see that this route is privileged. Naming the enum
    # members means a removed role is an ImportError/AttributeError at startup instead
    # of a silently unsatisfiable comparison.
    _clinician: User = Depends(
        require_role(UserRole.CLINICIAN.value, UserRole.ADMIN.value)
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Clinician or Admin: evaluate another patient's clinical safety assessment.

    A patient reads their own via ``GET /patients/me/safety``, which needs no role
    check because it resolves the profile from the caller's own user id.
    """
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    assessment = await evaluate_patient_safety(db, patient.id)
    return assessment

