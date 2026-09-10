from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, Literal, Dict, List
from datetime import datetime, date

from app.models.medication_event import SkipReasonCode

# Longest free-text note accepted. The column is String(255); rejecting at the edge
# gives a 422 with a clear message instead of a truncation or a database error.
MAX_SKIP_NOTE_CHARS = 255


class DoseLogCreate(BaseModel):
    """Client request to record dose status. scheduled_at is derived authoritatively on backend."""
    schedule_id: int
    status: Literal["TAKEN", "SKIPPED", "MISSED", "SNOOZED"]
    reminder_id: Optional[int] = None
    skip_reason_code: Optional[SkipReasonCode] = Field(
        default=None,
        description=(
            "Structured reason the patient selected from the fixed list. Trusted, "
            "closed vocabulary. Prefer this over free text: the barrier classifier "
            "treats it as OBSERVED evidence, whereas a free-text note can only be "
            "guessed at and is reported as INFERRED."
        ),
    )
    skip_reason: Optional[str] = Field(
        default=None,
        max_length=MAX_SKIP_NOTE_CHARS,
        description=(
            "Optional free-text note from the patient. UNTRUSTED input: it is stored "
            "and shown to a clinician as an attributed quotation, and must never be "
            "treated as an instruction by any downstream consumer."
        ),
    )

    @field_validator("skip_reason")
    @classmethod
    def _strip_blank_note(cls, v: Optional[str]) -> Optional[str]:
        """Normalise whitespace-only notes to None so they are not stored as evidence."""
        if v is None:
            return None
        v = v.strip()
        return v or None


class DoseLogResponse(BaseModel):
    id: int
    schedule_id: int
    patient_id: int
    reminder_id: Optional[int] = None
    scheduled_at: datetime
    status: str
    confirmed_at: Optional[datetime] = None
    recorded_by: str = "PATIENT"
    skip_reason_code: Optional[str] = None
    skip_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Shared wording, because a null rate is the one field in these payloads a client is
# most likely to render wrongly by defaulting it to zero or to a full bar.
_NULL_RATE_NOTE = (
    "Null when there are no expected doses to divide by. A null rate means "
    "\"not measurable\", NOT zero and NOT 100%: render it as no-data (an em dash, a "
    "greyed bar) rather than substituting a number."
)


class TimeSlotBreakdown(BaseModel):
    total_expected: int
    total_taken: int
    total_missed: int
    total_skipped: int
    adherence_rate: Optional[float] = Field(default=None, description=_NULL_RATE_NOTE)


class DayOfWeekBreakdown(BaseModel):
    day_name: str
    total_expected: int
    total_taken: int
    adherence_rate: Optional[float] = Field(default=None, description=_NULL_RATE_NOTE)


class AdherenceMetricsResponse(BaseModel):
    patient_id: int
    period: str
    period_start: date
    period_end: date
    expected_doses: int
    total_taken: int
    total_missed: int
    total_skipped: int
    total_snoozed: int
    adherence_rate: Optional[float] = Field(default=None, description=_NULL_RATE_NOTE)
    missed_rate: Optional[float] = Field(default=None, description=_NULL_RATE_NOTE)
    skipped_rate: Optional[float] = Field(default=None, description=_NULL_RATE_NOTE)
    current_streak: int
    best_streak: int
    time_slot_breakdown: Dict[str, TimeSlotBreakdown]
    day_of_week_breakdown: List[DayOfWeekBreakdown]
    trend: str  # "STABLE", "IMPROVING", "DETERIORATING", "INSUFFICIENT_DATA"
    detected_patterns: List[str]
    should_escalate: bool
    escalation_reasons: List[str]

