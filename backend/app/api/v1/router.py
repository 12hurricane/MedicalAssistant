from fastapi import APIRouter
from app.api.v1.endpoints import (
    adherence,
    admin,
    auth,
    medications,
    patients,
    prescriptions,
    schedules,
)

api_router = APIRouter()

from app.core.config import settings

@api_router.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.VERSION}

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(medications.router, prefix="/medications", tags=["medications"])
api_router.include_router(prescriptions.router, prefix="/prescriptions", tags=["prescriptions"])
api_router.include_router(schedules.router, prefix="/schedule", tags=["schedule"])
api_router.include_router(adherence.router, prefix="/adherence", tags=["adherence"])
