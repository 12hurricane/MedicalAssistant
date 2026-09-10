"""
Patient dose schedule endpoints.

Exists because nothing exposed MedicationSchedule to a client. POST /adherence/log
requires a ``schedule_id``, and no endpoint returned one — so dose logging was
unreachable from any client despite the service layer behind it being complete.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.medication_event import MedicationEventStatus
from app.models.patient import Patient
from app.models.types import utcnow
from app.models.user import User
from app.schemas.schedule import TodayDoseResponse, TodayScheduleResponse
from app.services import schedule_service

router = APIRouter()


@router.get("/today", response_model=TodayScheduleResponse)
async def get_today_schedule(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Today's doses for the signed-in patient, in chronological order.

    "Today" is the patient's local calendar day, not the server's. A dose with no
    MedicationEvent yet is reported as PENDING.

    Only active schedules of currently-prescribed medications appear. A discontinued
    medication is absent, matching what the reminder poller will and will not fire.
    """
    result = await db.execute(select(Patient).where(Patient.user_id == current_user.id))
    patient = result.scalars().first()
    if not patient:
        raise HTTPException(status_code=400, detail="User is not a patient")

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
