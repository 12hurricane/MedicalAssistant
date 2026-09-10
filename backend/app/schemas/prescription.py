from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime, date

class PrescribedMedicationCreate(BaseModel):
    medicine_name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    frequency: str
    duration_days: Optional[int] = None
    instructions: Optional[str] = None

class PrescriptionCreate(BaseModel):
    doctor_name: Optional[str] = None
    clinic_name: Optional[str] = None
    prescription_date: date
    medications: List[PrescribedMedicationCreate]

class PrescribedMedicationResponse(BaseModel):
    id: int
    prescription_id: int
    patient_id: int
    medicine_name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    frequency: str
    duration_days: Optional[int] = None
    instructions: Optional[str] = None
    medication_id: Optional[int] = None
    # Exposed because a correction discontinues superseded lines instead of
    # deleting them (their adherence history has to survive). Without this field a
    # client cannot tell a current medication from one the patient was taken off,
    # and would show discontinued drugs as if they were still prescribed.
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class PrescriptionResponse(BaseModel):
    id: int
    patient_id: int
    doctor_name: Optional[str] = None
    clinic_name: Optional[str] = None
    prescription_date: date
    image_url: Optional[str] = None
    verification_status: str
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None
    created_at: datetime
    medications: List[PrescribedMedicationResponse] = []

    model_config = ConfigDict(from_attributes=True)

class PrescriptionVerify(BaseModel):
    verified: bool
    corrections: Optional[List[PrescribedMedicationCreate]] = None


class ScheduleGenerationSummary(BaseModel):
    """What schedule generation actually did, reported back to the verifier."""

    created: int
    reactivated: int
    deactivated: int
    unchanged: int
    active_total: int
    # Medications left unscheduled on purpose because they are taken as needed.
    as_needed: List[str] = []


class MedicationReconciliationSummary(BaseModel):
    """What a correction actually changed, reported back to the verifier."""

    unchanged: int
    added: int
    reactivated: int
    #: Dropped or superseded lines. Retained as inactive rows so their recorded
    #: doses survive; a non-zero count here is not a deletion count.
    discontinued: int
    active_total: int


class PrescriptionVerifyResponse(PrescriptionResponse):
    """
    Verify response: the prescription plus scheduling and correction summaries.

    The scheduling summary matters because "verified" alone hides useful facts —
    notably that an as-needed medication was deliberately given no dose times, so
    the clinician is not left wondering why no reminders appeared for it. Null
    when the prescription was rejected.

    The reconciliation summary makes a correction's effect visible: how many
    lines were kept, added, brought back, and discontinued. Null when the request
    carried no corrections.
    """

    scheduling: Optional[ScheduleGenerationSummary] = None
    reconciliation: Optional[MedicationReconciliationSummary] = None

