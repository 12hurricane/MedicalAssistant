from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from datetime import date, datetime
from zoneinfo import available_timezones


def _validate_timezone(value: Optional[str]) -> Optional[str]:
    """
    Reject anything that is not a real IANA zone name.

    This has to be enforced at the write boundary, not at the readers. Three
    places turn this string into a ZoneInfo to decide *when a dose happens* --
    reminder_service (when a reminder fires), adherence_service (which local day
    a dose counts toward) and prescriptions.py (the derived start_date). Only
    reminder_service catches a bad value and falls back to UTC; the other two
    call ZoneInfo() unguarded, so an unvalidated string stored here surfaces
    later as a 500 in an unrelated endpoint, or as a silent UTC fallback that
    quietly shifts every reminder. Validating once, here, covers all three.
    """
    if value is None:
        return None
    if value not in available_timezones():
        raise ValueError(
            f"{value!r} is not a valid IANA timezone name. Use a zone like "
            f"'Asia/Kolkata' or 'America/New_York', not an abbreviation or offset."
        )
    return value


class PatientCreate(BaseModel):
    emergency_contact: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: List[str] = []
    chronic_conditions: List[str] = []
    preferred_language: str = "en"
    timezone: str = "UTC"

    _check_tz = field_validator("timezone")(_validate_timezone)

class PatientUpdate(BaseModel):
    emergency_contact: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[List[str]] = None
    chronic_conditions: Optional[List[str]] = None
    preferred_language: Optional[str] = None
    timezone: Optional[str] = None

    _check_tz = field_validator("timezone")(_validate_timezone)

class PatientResponse(BaseModel):
    id: int
    user_id: int
    emergency_contact: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: List[str] = []
    chronic_conditions: List[str] = []
    preferred_language: str
    # Exposed so a client can tell which zone its dose times are being
    # interpreted in. Without it the value was unreadable as well as unsettable.
    timezone: str
    name: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
