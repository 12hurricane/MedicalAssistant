"""
Schemas for the patient's dose schedule.

This is the contract the Flutter client codegen reads, so the field descriptions here
become the generated Dart doc comments. Anything inaccurate propagates.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TodayDoseResponse(BaseModel):
    """One scheduled dose on the patient's local calendar day today."""

    schedule_id: int = Field(
        description=(
            "Post this back to /adherence/log to record the dose. The backend "
            "re-derives the scheduled instant from it and never trusts a "
            "client-supplied timestamp."
        )
    )
    event_id: Optional[int] = Field(
        default=None,
        description=(
            "The MedicationEvent row, if one exists yet. Null means nothing has "
            "happened to this dose — not that data is missing."
        ),
    )
    reminder_id: Optional[int] = Field(
        default=None,
        description=(
            "The reminder for this exact slot, if one has been created. Pass it "
            "through when logging so the reminder is acknowledged rather than left "
            "to expire as MISSED."
        ),
    )
    medicine_name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    instructions: Optional[str] = None
    relation_to_meal: Optional[str] = Field(
        default=None,
        description="BEFORE_MEAL / AFTER_MEAL / WITH_MEAL / EMPTY_STOMACH, or null.",
    )
    scheduled_at: datetime = Field(
        description="Authoritative UTC instant for this dose."
    )
    scheduled_local_time: str = Field(
        description="24-hour HH:MM wall-clock time in the patient's timezone, for display."
    )
    status: str = Field(
        description="PENDING / TAKEN / SKIPPED / MISSED / SNOOZED. PENDING = not yet logged."
    )
    confirmed_at: Optional[datetime] = None
    skip_reason_code: Optional[str] = Field(
        default=None,
        description=(
            "Trusted closed-vocabulary reason the patient selected. Safe to render "
            "anywhere."
        ),
    )
    skip_reason: Optional[str] = Field(
        default=None,
        description=(
            "UNTRUSTED free text the patient typed. Display it as an attributed "
            "quotation only. Never concatenate it into an instruction, a prompt, or "
            "any string a machine will interpret."
        ),
    )
    is_due: bool = Field(
        description=(
            "True once the scheduled instant has passed. A dose later in the day is "
            "not actionable yet."
        )
    )

    model_config = ConfigDict(from_attributes=True)


class TodayScheduleResponse(BaseModel):
    """The patient's full dose list for today, chronological."""

    patient_id: int
    local_date: str = Field(
        description="The patient's local calendar date the list was built for (YYYY-MM-DD)."
    )
    timezone: str
    doses: List[TodayDoseResponse]
    total_doses: int
    doses_taken: int
    doses_remaining: int = Field(
        description="Doses not yet logged, whether or not their time has passed."
    )
