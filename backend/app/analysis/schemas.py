"""
Adherence Analysis Schemas

Structured Pydantic contracts separating patient-facing explanations from clinician briefs,
with explicit barrier categorization, confidence levels, and immutable safety invariants.

These are deterministic composition outputs, not model outputs — see
``app/analysis/adherence_analysis_service.py`` for why the distinction matters.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BarrierCategory(str, Enum):
    FORGETFULNESS = "Forgetfulness"
    SCHEDULE_CONFLICT = "Schedule conflict"
    MEDICATION_MISUNDERSTANDING = "Medication misunderstanding"
    SIDE_EFFECTS = "Side effects"
    ACCESS_AVAILABILITY = "Access / availability"
    COST = "Cost"
    INTENTIONAL_NON_ADHERENCE = "Intentional non-adherence"
    COMPLEXITY = "Complexity"
    # Not a barrier. A dose the patient was *told* to hold is a clinical decision,
    # and presenting it to a clinician as non-adherence is actively misleading —
    # they may be looking at the consequence of their own instruction. Kept in this
    # enum because the classifier has to be able to say so; see SkipReasonCode.
    CLINICIAN_DIRECTED = "Clinician-directed hold"
    UNKNOWN = "Unknown / Insufficient data"


class EvidenceStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class GenerationStatus(str, Enum):
    GENERATED_OLLAMA = "GENERATED_OLLAMA"
    GENERATED_GEMINI = "GENERATED_GEMINI"
    FALLBACK = "FALLBACK"


class BarrierItem(BaseModel):
    """
    Structured adherence barrier hypothesis.

    The two text fields have different trust levels and must not be merged:

    - ``observed_pattern`` is composed by this system from its own numbers. Trusted.
    - ``patient_reported_text`` is whatever the patient typed. UNTRUSTED. It is
      carried in its own field precisely so a downstream consumer never has to
      string-parse it back out of trusted prose, and so a prompt builder can place
      it inside a fenced untrusted block instead of concatenating it into
      instructions. See ``app/llm/prompt.py``.
    """
    category: BarrierCategory
    status: EvidenceStatus
    confidence: ConfidenceLevel
    observed_pattern: str
    hypothesis_rationale: str
    follow_up_question: str
    patient_reported_text: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class LLMBarrierContext(BaseModel):
    barrier_category: BarrierCategory
    patient_quote: Optional[str] = None
    follow_up_question: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class LLMPatientContextExtraction(BaseModel):
    barrier_context: List[LLMBarrierContext] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PatientExplanation(BaseModel):
    """Patient-friendly, jargon-free adherence summary and guidance."""
    summary: str
    what_the_system_found: str
    why_it_matters: str
    what_to_do_next: str
    when_to_contact_care_team: str
    citations: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class GenerativeClinicalInsights(BaseModel):
    """
    Narrative components synthesized by the generative model.
    The LLM ONLY generates these fields. It does not touch safety or adherence arithmetic.
    """
    trend: Optional[str] = "UNKNOWN"
    concerning_patterns: List[str] = Field(default_factory=list)
    possible_barriers: List[BarrierItem] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ClinicalBrief(BaseModel):
    """Clinician-facing adherence review and barrier brief."""
    patient_id: int
    period: str
    # Null when no doses were expected in the period. A clinician brief is the last
    # place to substitute a number for missing data: see ``AdherenceMetrics``.
    adherence_rate: Optional[float] = None
    
    # Deterministic fields
    safety_risk_level: str
    requires_human_review: bool
    citations: List[str] = Field(default_factory=list)
    generation_status: GenerationStatus = GenerationStatus.FALLBACK
    
    # Generative insights (nullable if LLM fails)
    insights: Optional[GenerativeClinicalInsights] = None

    model_config = ConfigDict(from_attributes=True)


class AdherenceAnalysisResult(BaseModel):
    """
    Master output contract from the Adherence Analysis Service.

    ``validation_passed`` refers to the deterministic invariant checks in
    ResponseValidator (risk level preserved, human-review flag preserved, no unsafe
    dosing advice, no untraceable citation). It is not a statement about a model.
    """
    patient_id: int
    evaluated_at: datetime
    safety_risk_level: str
    requires_human_review: bool
    recommended_action: str
    patient_explanation: PatientExplanation
    clinical_brief: ClinicalBrief
    validation_passed: bool = True
    generation_status: GenerationStatus = GenerationStatus.FALLBACK

    model_config = ConfigDict(from_attributes=True)
