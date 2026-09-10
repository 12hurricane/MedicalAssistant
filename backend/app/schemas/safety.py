from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class MedicationInteractionAlertResponse(BaseModel):
    drug_a: str
    drug_b: str
    severity: str
    mechanism: str
    clinical_effect: str
    recommendation: str
    source: str

    model_config = ConfigDict(from_attributes=True)


class ContraindicationAlertResponse(BaseModel):
    medication: str
    contraindication_type: str
    trigger: str
    severity: str
    clinical_risk: str
    recommendation: str

    model_config = ConfigDict(from_attributes=True)


class DuplicateTherapyAlertResponse(BaseModel):
    medications: List[str]
    drug_class: str
    severity: str
    clinical_risk: str
    recommendation: str

    model_config = ConfigDict(from_attributes=True)


class AdherenceSafetyAlertResponse(BaseModel):
    # Non-optional on purpose, matching AdherenceSafetyAlert: the alert is only built
    # behind an `expected_doses >= 3` guard, so a measurable rate is a precondition of
    # it existing. Unlike the rates on AdherenceMetricsResponse, this one is never null.
    adherence_rate: float
    consecutive_missed: int
    critical_drugs_affected: List[str]
    clinical_risk: str
    recommended_action: str

    model_config = ConfigDict(from_attributes=True)


class SafetyEvidenceResponse(BaseModel):
    category: str
    finding: str
    severity: str
    reference_source: str

    model_config = ConfigDict(from_attributes=True)


class SafetyAssessmentResponse(BaseModel):
    patient_id: int
    evaluated_at: datetime
    risk_level: str
    requires_human_review: bool
    recommended_action: str
    medication_interactions: List[MedicationInteractionAlertResponse] = []
    contraindications: List[ContraindicationAlertResponse] = []
    duplicate_therapies: List[DuplicateTherapyAlertResponse] = []
    adherence_risks: List[AdherenceSafetyAlertResponse] = []
    evidence: List[SafetyEvidenceResponse] = []

    model_config = ConfigDict(from_attributes=True)
