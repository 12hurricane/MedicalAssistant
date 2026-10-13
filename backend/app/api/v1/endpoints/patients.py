from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.schemas.patient import PatientResponse, PatientUpdate
from app.schemas.auth import UserRole
from app.models.patient import Patient
from app.models.clinician_patient_assignment import ClinicianPatientAssignment
from app.dependencies import get_db, get_current_user, require_role, get_patient_for_clinician_or_admin
from app.models.user import User

router = APIRouter()

@router.get("", response_model=List[PatientResponse])
async def list_patients(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    current_user: User = Depends(
        require_role(UserRole.CLINICIAN.value, UserRole.ADMIN.value)
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Clinician or Admin: List patient roster with optional search.
    
    Clinicians only receive patients assigned to them via ClinicianPatientAssignment.
    Admins retain system-wide unscoped access.
    """
    stmt = select(Patient).options(selectinload(Patient.user)).join(User)

    if current_user.role == UserRole.CLINICIAN.value:
        stmt = stmt.join(
            ClinicianPatientAssignment,
            ClinicianPatientAssignment.patient_id == Patient.id,
        ).filter(
            ClinicianPatientAssignment.clinician_id == current_user.id
        )

    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.filter(
            (User.name.ilike(search_pattern)) | (User.email.ilike(search_pattern))
        )
    stmt = stmt.order_by(Patient.id.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/me", response_model=PatientResponse)
async def get_current_patient(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get current patient's profile."""
    result = await db.execute(
        select(Patient).options(selectinload(Patient.user)).filter(Patient.user_id == current_user.id)
    )
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    return patient


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient_profile(
    patient: Patient = Depends(get_patient_for_clinician_or_admin),
) -> Any:
    """Clinician or Admin: Get a specific patient's profile."""
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
    patient: Patient = Depends(get_patient_for_clinician_or_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Clinician or Admin: evaluate an assigned patient's clinical safety assessment.

    A patient reads their own via ``GET /patients/me/safety``, which needs no role
    check because it resolves the profile from the caller's own user id.
    """
    assessment = await evaluate_patient_safety(db, patient.id)
    return assessment

