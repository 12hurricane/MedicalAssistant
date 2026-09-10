from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Annotated, Optional
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    """The complete set of roles this system has. Three, and no synonyms.

    CLINICIAN was DOCTOR. The two coexisted — the role value said DOCTOR while every
    docstring, schema and analysis module said "clinician" — which is not a naming
    quibble: the split is exactly the shape of bug where a migration updates
    ``users.role`` to one term and an authorization list keeps checking the other,
    locking out the accounts it was meant to admit. CLINICIAN is also the wider and
    more accurate word for who performs review here (a pharmacist or a nurse
    practitioner is not a doctor). Migration: ``9f2c1d7ab4e0``.

    CAREGIVER is gone. It had no live rows, no endpoint that granted it anything, no
    client route and no product scope behind it — an unimplemented role in an
    authorization enum is a liability, because it reads as a capability that exists.

    Deliberately no back-compatibility alias for either. Both values are now rejected
    everywhere a role is writable; see ``test_role_vocabulary.py``.

    Note this is the *technical* vocabulary. Display labels ("Clinician") belong to the
    client, and ``prescriptions.doctor_name`` is unrelated — that is a prescriber's
    name as free text, not a role.
    """
    PATIENT = "PATIENT"
    CLINICIAN = "CLINICIAN"
    ADMIN = "ADMIN"


class PrivilegedRole(str, Enum):
    """The roles only an existing ADMIN may hand out.

    A separate enum from :class:`UserRole` rather than a validator over it, so that
    PATIENT is not merely rejected by ``POST /admin/users`` — it is not expressible
    in that request at all. Patients are created by self-service registration, which
    is the one path that also builds their profile row.

    Because this enum is the request contract, an unsupported role here is a 422 from
    Pydantic before any handler runs. That is what makes the retired DOCTOR and
    CAREGIVER values unwritable rather than merely unused.
    """
    CLINICIAN = "CLINICIAN"
    ADMIN = "ADMIN"


# A floor of 8 characters, and no character-class rules. Length is a real constraint
# on a search space; "must contain one uppercase and one symbol" mostly produces
# Password1! and a false sense of having required something.
PASSWORD_MIN_CHARS = 8

# The ceiling is not a strength requirement, it is a cost bound. bcrypt hashes
# whatever it is given, and registration is anonymous, so without a limit a caller
# chooses how much CPU the server spends per request. Note that only the first 72
# bytes affect the hash (see app/core/security.py) — everything between 72 and 128 is
# accepted and ignored rather than rejected, because silently-ignored tail bytes are
# the historical bcrypt behaviour and rejecting them would lock out existing accounts.
PASSWORD_MAX_CHARS = 128

Password = Annotated[
    str,
    Field(
        min_length=PASSWORD_MIN_CHARS,
        max_length=PASSWORD_MAX_CHARS,
        description=(
            f"Between {PASSWORD_MIN_CHARS} and {PASSWORD_MAX_CHARS} characters. "
            "No character-class requirements."
        ),
    ),
]


class UserRegister(BaseModel):
    """Public self-service registration. Creates a PATIENT, and can create nothing else.

    There is deliberately no ``role`` field. It was removed rather than validated,
    because the two are not equivalent: a rejected-if-not-PATIENT check still
    publishes ``role`` in the OpenAPI schema, still advertises the enum of roles that
    exist, and still leaves one edit away from being writable again. An absent field
    cannot be smuggled through, cannot be forgotten in a refactor, and does not tell
    an anonymous caller that ADMIN is a thing this system has.

    Privileged accounts are created by ``POST /admin/users``, which requires an
    authenticated ADMIN. See :class:`AdminUserCreate`.
    """
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: Password
    phone: Optional[str] = Field(default=None, max_length=50)


class AdminUserCreate(BaseModel):
    """Privileged account creation. Reachable only by an authenticated ADMIN.

    This is the only place ``role`` is writable over HTTP, and the values it accepts
    are constrained by :class:`PrivilegedRole` rather than by :class:`UserRole`.
    """
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: Password
    phone: Optional[str] = Field(default=None, max_length=50)
    role: PrivilegedRole


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefresh(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
