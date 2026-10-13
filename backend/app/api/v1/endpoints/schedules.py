"""
Patient dose schedule endpoints.

Exists because nothing exposed MedicationSchedule to a client. POST /adherence/log
requires a ``schedule_id``, and no endpoint returned one — so dose logging was
unreachable from any client despite the service layer behind it being complete.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, verify_patient_access
from app.models.medication_event import MedicationEventStatus
from app.models.medication_schedule import MedicationSchedule
from app.models.patient import Patient
from app.models.schedule_version import ScheduleVersion
from app.models.types import utcnow
from app.models.user import User
from app.schemas.auth import UserRole
from app.schemas.schedule import TodayDoseResponse, TodayScheduleResponse
from app.services import schedule_service

router = APIRouter()


class ScheduleVersionResponse(BaseModel):
    """One historical snapshot of a schedule's state."""
    id: int
    schedule_id: int
    version_number: int
    valid_from: str
    valid_to: Optional[str] = None
    schedule_data: dict

    model_config = ConfigDict(from_attributes=True)


@router.get("/today", response_model=TodayScheduleResponse)
async def get_today_schedule(
    patient_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Today's doses for the patient, in chronological order.

    "Today" is the patient's local calendar day, not the server's. A dose with no
    MedicationEvent yet is reported as PENDING.

    Clinicians and administrators can view doses for an assigned patient by
    providing the patient_id query parameter.
    """
    if current_user.role in (UserRole.CLINICIAN.value, UserRole.ADMIN.value):
        if patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="patient_id query parameter is required for clinicians and administrators (user is not a patient)",
            )
        patient = await verify_patient_access(patient_id=patient_id, current_user=current_user, db=db)
    elif current_user.role == UserRole.PATIENT.value:
        if patient_id is not None:
            patient = await verify_patient_access(patient_id=patient_id, current_user=current_user, db=db)
        else:
            result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
            patient = result.scalars().first()
            if not patient:
                raise HTTPException(status_code=400, detail="User is not a patient")
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access schedule",
        )

    doses = await schedule_service.get_todays_doses(db, patient.id)
    tz = schedule_service.resolve_patient_timezone(patient)

    taken = sum(1 for d in doses if d.status == MedicationEventStatus.TAKEN.value)
    remaining = sum(
        1 for d in doses if d.status == MedicationEventStatus.PENDING.value
    )
    local_date = utcnow().astimezone(tz).date()

    return TodayScheduleResponse(
        patient_id=patient.id,
        local_date=local_date.isoformat(),
        timezone=str(tz),
        doses=[TodayDoseResponse.model_validate(d) for d in doses],
        total_doses=len(doses),
        doses_taken=taken,
        doses_remaining=remaining,
    )


@router.get("/{schedule_id}/versions", response_model=List[ScheduleVersionResponse])
async def get_schedule_versions(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve the version history (audit trail) for a specific schedule.

    Clinicians and admins can inspect the full history of schedule changes to
    understand when and why dose times, frequencies, or statuses were altered.
    """
    if current_user.role not in (UserRole.CLINICIAN.value, UserRole.ADMIN.value):
        raise HTTPException(status_code=403, detail="Only clinicians can view schedule version history")

    # Verify the schedule exists
    sched = await db.execute(
        select(MedicationSchedule).where(MedicationSchedule.id == schedule_id)
    )
    if not sched.scalars().first():
        raise HTTPException(status_code=404, detail="Schedule not found")

    rows = await db.execute(
        select(ScheduleVersion)
        .where(ScheduleVersion.schedule_id == schedule_id)
        .order_by(ScheduleVersion.version_number.desc())
    )
    versions = rows.scalars().all()

    return [
        ScheduleVersionResponse(
            id=v.id,
            schedule_id=v.schedule_id,
            version_number=v.version_number,
            valid_from=v.valid_from.isoformat() if v.valid_from else "",
            valid_to=v.valid_to.isoformat() if v.valid_to else None,
            schedule_data=v.schedule_data,
        )
        for v in versions
    ]


async def snapshot_schedule_version(
    db: AsyncSession,
    schedule: MedicationSchedule,
) -> ScheduleVersion:
    """Persist a point-in-time snapshot of a schedule for audit purposes.

    Called by schedule generation when a schedule is created, reactivated,
    cancelled, or superseded. The snapshot captures the schedule's full state
    at the moment of the change.
    """
    # Find the next version number for this schedule
    max_ver = await db.execute(
        select(func.max(ScheduleVersion.version_number))
        .where(ScheduleVersion.schedule_id == schedule.id)
    )
    current_max = max_ver.scalar() or 0

    # Close previous version's valid_to
    prev = await db.execute(
        select(ScheduleVersion)
        .where(
            ScheduleVersion.schedule_id == schedule.id,
            ScheduleVersion.valid_to.is_(None),
        )
    )
    prev_version = prev.scalars().first()
    now = utcnow()
    if prev_version:
        prev_version.valid_to = now

    snapshot = ScheduleVersion(
        schedule_id=schedule.id,
        version_number=current_max + 1,
        valid_from=now,
        valid_to=None,
        schedule_data={
            "prescribed_medication_id": schedule.prescribed_medication_id,
            "patient_id": schedule.patient_id,
            "scheduled_time": schedule.scheduled_time.isoformat() if schedule.scheduled_time else None,
            "relation_to_meal": schedule.relation_to_meal,
            "start_date": schedule.start_date.isoformat() if schedule.start_date else None,
            "end_date": schedule.end_date.isoformat() if schedule.end_date else None,
            "status": schedule.status,
        },
    )
    db.add(snapshot)
    return snapshot
