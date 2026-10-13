from typing import Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.security import decode_token, TOKEN_TYPE_ACCESS
from app.models.user import User  # Will be defined later
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    if payload.get("ver") != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

def require_role(*roles: str) -> Callable:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker

from app.models.patient import Patient
from app.models.clinician_patient_assignment import ClinicianPatientAssignment
from fastapi import Path

async def verify_patient_access(
    patient_id: int,
    current_user: User,
    db: AsyncSession,
) -> Patient:
    """Verify that current_user has access to the specified patient_id, enforcing role and assignment."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if current_user.role == 'ADMIN':
        return patient

    if current_user.role == 'PATIENT':
        if patient.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Patients cannot access other patients' records")
        return patient

    if current_user.role == 'CLINICIAN':
        assignment = await db.execute(
            select(ClinicianPatientAssignment).where(
                ClinicianPatientAssignment.clinician_id == current_user.id,
                ClinicianPatientAssignment.patient_id == patient.id,
            )
        )
        if not assignment.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not assigned to this patient")
        return patient

    raise HTTPException(status_code=403, detail="Not enough permissions")


async def get_patient_with_access(
    patient_id: int = Path(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    """Dependency to retrieve a patient and verify the current user has access to them."""
    return await verify_patient_access(patient_id=patient_id, current_user=current_user, db=db)

async def get_patient_for_clinician_or_admin(
    patient_id: int = Path(...),
    current_user: User = Depends(require_role('CLINICIAN', 'ADMIN')),
    db: AsyncSession = Depends(get_db)
) -> Patient:
    """Dependency that requires CLINICIAN/ADMIN and checks assignment."""
    return await get_patient_with_access(patient_id=patient_id, current_user=current_user, db=db)
