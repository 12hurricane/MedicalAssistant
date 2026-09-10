"""Administrative user management.

Exists because ``POST /auth/register`` must not be able to create anything but a
PATIENT. Somebody still has to be able to create clinicians, so that capability lives
here, behind an authenticated ADMIN, instead of behind a role field on a public form.

The first ADMIN cannot be created through this endpoint — that would be circular. It is
created by ``python -m app.cli create-admin``, a local command that needs shell access
to the deployment rather than a network request. See ``app/cli.py``.
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, require_role
from app.models.user import User
from app.schemas.auth import AdminUserCreate, UserResponse, UserRole
from app.services.auth_service import auth_service

router = APIRouter()


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a privileged user (ADMIN only)",
    responses={
        403: {"description": "Caller is authenticated but is not an ADMIN"},
        400: {"description": "Email already registered"},
    },
)
async def create_user(
    user_data: AdminUserCreate,
    # The authorization boundary. Declared as a dependency rather than checked in the
    # body so that it runs before the handler, appears in the OpenAPI schema, and
    # cannot be skipped by an early return added later.
    _admin: User = Depends(require_role(UserRole.ADMIN.value)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a CLINICIAN or an ADMIN.

    PATIENT is not accepted: ``AdminUserCreate.role`` is a
    :class:`~app.schemas.auth.PrivilegedRole`, so a patient account cannot be created
    here even by an admin. Patients register themselves, which is also the path that
    creates their profile row.

    The retired DOCTOR and CAREGIVER values are not accepted either, for the same
    reason and by the same mechanism — they are absent from the enum, so they fail
    request validation with 422 rather than reaching this handler.
    """
    return await auth_service.create_privileged_user(db, user_data)
