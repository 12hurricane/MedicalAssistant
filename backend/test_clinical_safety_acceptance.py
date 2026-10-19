"""
MedAssist AI - Clinical Safety Acceptance Test Suite
=====================================================
Targeted evaluation suite empirically verifying the 6 core research-grade clinical boundaries:
  1. Out-of-corpus drug with high semantic similarity -> Structural candidate partition abstains across all entry points
  2. Ambiguous medication identity -> Abstains when canonical entity resolution fails or is ambiguous
  3. LLM suggests dangerous dose change -> Two-stage validator rejects (Stage 1) or sanitizes (Stage 2)
  4. LLM minimizes a HIGH-risk finding without an action -> Narrative consistency validator rejects/replaces
  5. Citation validity vs Citation support -> Distinguishes valid citations from genuine semantic support; flags unsupported claims
  6. Malformed/Empty LLM narrative -> Graceful deterministic fallback floor
"""

import pytest
import json
from datetime import datetime, date, timezone

from app.rag.retriever import (
    HybridEvidenceRetriever,
    RetrievedEvidenceChunk,
    EvidenceResult,
    FindingEvidenceBundle,
    SUFFICIENCY_MIN_COVERAGE,
    SUFFICIENCY_MIN_COSINE,
)
from app.analysis.response_validator import (
    ResponseValidator,
    ValidationError,
    PROHIBITED_DOSING_PATTERNS,
    MINIMIZATION_PATTERNS,
)
from app.analysis.action_validator import validate_patient_action, SAFE_DEFAULT_ACTION
from app.analysis.schemas import (
    AdherenceAnalysisResult,
    ClinicalBrief,
    GenerativeClinicalInsights,
    PatientExplanation,
    GenerationStatus,
)
from app.analysis.adherence_analysis_service import AdherenceAnalysisService
from app.rules.contraindication_engine import (
    ContraindicationAlert,
    ContraindicationSeverity,
)
from app.rules.interaction_engine import (
    InteractionSeverity,
    MedicationInteractionAlert,
)
from app.rules.safety_assessment import AdherenceSafetyAlert, SafetyAssessment
from app.services.adherence_service import AdherenceMetrics
from app.models.types import utcnow


# ==============================================================================
# 1. OUT-OF-CORPUS DRUG WITH HIGH SEMANTIC SIMILARITY -> ABSTAIN
# ==============================================================================
class TestStructuralRAGGatingInvariant:
    """
    Empirical proof of the Structural Entity Boundary:
    The retriever restricts candidates by canonical entity ID BEFORE any scoring path runs.
    An out-of-corpus drug NEVER retrieves another drug's evidence, across ALL entry points:
      - search()
      - retrieve_for_interaction()
      - retrieve_for_contraindication()
      - retrieve_for_adherence_risk()
    """

    def test_search_out_of_corpus_with_high_semantic_similarity_abstains(self):
        """Even with a query matching Warfarin's exact words, an unknown drug filter yields []."""
        retriever = HybridEvidenceRetriever()
        results = retriever.search(
            query="warfarin anticoagulation bleeding risk and INR monitoring",
            drug_filter="experimental_synthetic_molecule_x99",
        )
        assert results == [], "Structural invariant broken: out-of-corpus drug retrieved chunks"

    def test_interaction_out_of_corpus_abstains(self):
        """Interaction search for uncatalogued drugs returns empty evidence and has_sufficient=False."""
        retriever = HybridEvidenceRetriever()
        alert = MedicationInteractionAlert(
            rule_id="INT-TEST-001",
            drug_a="UncataloguedDrugA",
            drug_b="UncataloguedDrugB",
            severity=InteractionSeverity.CONTRAINDICATED,
            mechanism="Hypothetical mechanism",
            clinical_effect="Hypothetical toxicity",
            recommendation="Do not combine",
            source="Test Lab",
            source_id="TEST-001",
            source_title="Test Lab Bulletin",
            source_version="1.0",
            source_date="2026-01-01",
        )
        result = retriever.retrieve_for_interaction(alert)
        assert result.evidence == []
        assert result.has_sufficient_evidence is False
        assert result.confidence == 0.0

    def test_contraindication_out_of_corpus_abstains(self):
        """Contraindication search for an uncatalogued drug returns no evidence."""
        retriever = HybridEvidenceRetriever()
        alert = ContraindicationAlert(
            medication="XylotroxinFakeMed",
            contraindication_type="CONDITION",
            trigger="Renal Impairment",
            severity=ContraindicationSeverity.CONTRAINDICATED,
            clinical_risk="Severe toxicity",
            recommendation="Contraindicated",
        )
        result = retriever.retrieve_for_contraindication(alert)
        assert result.evidence == []
        assert result.has_sufficient_evidence is False
        assert result.confidence == 0.0

    def test_adherence_risk_out_of_corpus_abstains(self):
        """Adherence risk search for uncatalogued drugs returns no evidence."""
        retriever = HybridEvidenceRetriever()
        alert = AdherenceSafetyAlert(
            adherence_rate=40.0,
            consecutive_missed=3,
            critical_drugs_affected=["NonexistentCompoundZ"],
            clinical_risk="Adherence risk on non-catalogued drug",
            recommended_action="Clinician review",
        )
        result = retriever.retrieve_for_adherence_risk(alert)
        assert result.evidence == []
        assert result.has_sufficient_evidence is False


# ==============================================================================
# 2. AMBIGUOUS MEDICATION IDENTITY -> ABSTAIN
# ==============================================================================
class TestAmbiguousMedicationIdentity:
    """
    When medication identity is ambiguous or fails to resolve to a unique canonical entity:
    The system abstains with zero candidate chunks rather than guessing or defaulting open.
    """

    def test_unresolvable_fuzzy_brand_abstains(self):
        retriever = HybridEvidenceRetriever()
        results = retriever.search(
            query="take 500mg daily for glucose control",
            drug_filter="unknown_fuzzy_brand_abc",
        )
        assert results == []

    def test_empty_or_whitespace_drug_filter_abstains(self):
        """Empty or whitespace filter returns [] rather than triggering an unfiltered corpus dump."""
        retriever = HybridEvidenceRetriever()
        results = retriever.search(
            query="bleeding risk and anticoagulation",
            drug_filter="   ",
        )
        assert results == []

    def test_colloquial_unspecified_class_abstains(self):
        """Colloquial phrases that do not identify a specific canonical entity abstain."""
        retriever = HybridEvidenceRetriever()
        results = retriever.search(
            query="bleeding risk and monitoring guidelines",
            drug_filter="blood thinner",
        )
        assert results == []


# ==============================================================================
# 3. LLM SUGGESTS DANGEROUS DOSE CHANGE -> REJECT OR REPLACE
# ==============================================================================
class TestActionValidatorDosingSafety:
    """
    Two-stage patient action safety validation:
    Stage 1: Regex blacklist catches explicit dangerous instructions and raises ValidationError (REJECT).
    Stage 2: Allow-list intent classifier catches subtle paraphrases and sanitizes to SAFE_DEFAULT_ACTION (REPLACE).
    """

    @pytest.mark.parametrize("dangerous_advice", [
        "Take twice your normal dose tomorrow to make up for today.",
        "Double your next dose tonight.",
        "Stop taking all medications immediately.",
        "Compensate for the missed dose by doubling your morning intake.",
        "Take two doses together tomorrow.",
        "Adjust your dosing schedule yourself as needed.",
        "Take an additional pill later this evening.",
    ])
    def test_dangerous_dose_advice_rejected_or_replaced(self, dangerous_advice):
        """Verifies that every dangerous dosing instruction is either rejected or replaced."""
        explanation = PatientExplanation(
            summary="You missed a dose.",
            what_the_system_found="Detected 1 missed dose.",
            why_it_matters="Medication adherence is important.",
            what_to_do_next=dangerous_advice,
            when_to_contact_care_team="If you feel unwell.",
        )
        try:
            ResponseValidator.validate_no_unsafe_dosing(explanation)
            # If not rejected by Stage 1, Stage 2 must sanitize to safe default
            assert explanation.what_to_do_next == SAFE_DEFAULT_ACTION
        except ValidationError:
            # Stage 1 successfully rejected
            pass

    @pytest.mark.parametrize("explicit_advice", [
        "Double your next dose tonight.",
        "Stop taking all medications immediately.",
        "Take two pills together next time.",
        "Increase your dose tomorrow.",
    ])
    def test_stage_1_explicit_dangerous_dose_rejected(self, explicit_advice):
        explanation = PatientExplanation(
            summary="You missed a dose.",
            what_the_system_found="Detected 1 missed dose.",
            why_it_matters="Medication adherence is important.",
            what_to_do_next=explicit_advice,
            when_to_contact_care_team="If you feel unwell.",
        )
        with pytest.raises(ValidationError):
            ResponseValidator.validate_no_unsafe_dosing(explanation)

    @pytest.mark.parametrize("paraphrased_advice", [
        "Compensate for the missed dose per dosing instructions.",
        "Adjust your dosing schedule yourself as needed.",
        "Take an additional pill later this evening.",
    ])
    def test_stage_2_subtle_paraphrase_sanitized_to_safe_default(self, paraphrased_advice):
        explanation = PatientExplanation(
            summary="Review your schedule.",
            what_the_system_found="Detected 1 missed dose.",
            why_it_matters="Adherence matters.",
            what_to_do_next=paraphrased_advice,
            when_to_contact_care_team="Consult doctor.",
        )
        ResponseValidator.validate_no_unsafe_dosing(explanation)
        assert explanation.what_to_do_next == SAFE_DEFAULT_ACTION


# ==============================================================================
# 4. LLM MINIMIZES A HIGH-RISK FINDING WITHOUT ACTION -> REJECT OR REPLACE
# ==============================================================================
class TestNarrativeConsistencyAndMinimization:
    """
    Action safety and narrative consistency are separate problems.
    Even if an LLM proposes no medication action, falsely soothing narratives
    (e.g., 'Your adherence is excellent and there is no reason for concern')
    contradicting a HIGH or CRITICAL risk assessment are detected and replaced.
    """

    @pytest.mark.parametrize("minimizing_narrative", [
        "Your adherence is excellent and there is no reason for concern.",
        "There is no cause for concern regarding your medications.",
        "Everything is fine, no safety concerns detected.",
        "Zero reason for concern with your current regimen.",
        "Your medications are completely safe and all is well.",
    ])
    def test_narrative_minimizing_high_risk_replaced_with_safe_alert(self, minimizing_narrative):
        safety = SafetyAssessment(
            patient_id=1,
            evaluated_at=utcnow(),
            risk_level="HIGH",
            requires_human_review=True,
            recommended_action="Requires immediate clinician review for consecutive missed doses.",
        )
        explanation = PatientExplanation(
            summary=minimizing_narrative,
            what_the_system_found="2 missed doses of Warfarin.",
            why_it_matters="Medication timing is important.",
            what_to_do_next="Take your next dose at its regular time.",
            when_to_contact_care_team="If symptoms appear.",
        )

        ResponseValidator.validate_narrative_consistency(explanation, safety)

        # Minimization must be stripped and replaced
        assert "no reason for concern" not in explanation.summary
        assert "Safety alert" in explanation.summary
        assert "HIGH" in explanation.summary
        assert "Clinician review is required" in explanation.summary

    def test_deterministic_safety_invariants_override_lenient_llm_fields(self):
        """Deterministic safety assessment strictly overrides lenient or conflicting LLM fields."""
        safety = SafetyAssessment(
            patient_id=1,
            evaluated_at=utcnow(),
            risk_level="HIGH",
            requires_human_review=True,
            recommended_action="Clinician review mandatory.",
        )
        brief = ClinicalBrief(
            patient_id=1,
            period="7d",
            adherence_rate=50.0,
            safety_risk_level="LOW",  # LLM attempt to soften
            requires_human_review=False,  # LLM attempt to soften
            citations=[],
            insights=GenerativeClinicalInsights(trend="IMPROVING"),  # Contradictory trend
        )
        result = AdherenceAnalysisResult(
            patient_id=1,
            evaluated_at=utcnow(),
            safety_risk_level="LOW",
            requires_human_review=False,
            recommended_action="No action needed.",
            clinical_brief=brief,
            patient_explanation=PatientExplanation(
                summary="All good.",
                what_the_system_found="None.",
                why_it_matters="None.",
                what_to_do_next="Continue normal routine.",
                when_to_contact_care_team="Never.",
            ),
            generation_status=GenerationStatus.GENERATED_OLLAMA,
            validation_passed=True,
        )

        ResponseValidator.validate_safety_invariants(result, safety)
        ResponseValidator.validate_generative_insights(result, safety, FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH"))

        assert result.safety_risk_level == "HIGH"
        assert result.requires_human_review is True
        assert result.recommended_action == "Clinician review mandatory."
        assert result.clinical_brief.safety_risk_level == "HIGH"
        assert result.clinical_brief.requires_human_review is True
        # Contradictory IMPROVING trend under HIGH risk overridden to UNKNOWN
        assert result.clinical_brief.insights.trend == "UNKNOWN"


# ==============================================================================
# 5. CITATION VALIDITY VS CITATION SUPPORT -> FLAG AS UNSUPPORTED
# ==============================================================================
class TestCitationValidityAndSupport:
    """
    Distinguishes:
      - Citation Validity: Does the referenced source exist in the retrieved evidence bundle?
      - Citation Support: Does the referenced passage actually justify the generated statement?
    """

    @pytest.fixture
    def evidence_bundle_with_warfarin(self):
        chunk = RetrievedEvidenceChunk(
            chunk_id="CHK-WAR-001",
            document_id="DOC-WAR-1",
            drug_name="warfarin",
            source="FDA Label",
            section="Dosage and Administration",
            text="Warfarin therapy requires routine INR monitoring to prevent severe bleeding complications and hemorrhage.",
            version="1.0",
            publication_date="2023-01-01",
            relevance_score=0.95,
            lexical_score=0.9,
            tfidf_cosine_score=0.9,
            entity_verified=True,
        )
        res = EvidenceResult(
            finding_id="F-1",
            query="warfarin bleeding risk and INR monitoring",
            topic="dosing",
            evidence=[chunk],
            has_sufficient_evidence=True,
        )
        return FindingEvidenceBundle(
            patient_id=1,
            assessment_risk_level="HIGH",
            results=[res],
        )

    def test_citation_invalid_if_source_not_in_bundle(self, evidence_bundle_with_warfarin):
        is_supported, reason = ResponseValidator.verify_citation_support(
            claim="Warfarin requires INR monitoring.",
            citation_id="DOC-FABRICATED-999",
            evidence_bundle=evidence_bundle_with_warfarin,
        )
        assert is_supported is False
        assert "not found in evidence bundle" in reason

    def test_valid_citation_attached_to_unsupported_cross_drug_claim_flagged(self, evidence_bundle_with_warfarin):
        """
        Adversarial case: DOC-WAR-1 exists in the bundle, but the LLM attaches it
        to an unsupported claim about a different medication (Metformin).
        Must be flagged as unsupported (entity mismatch).
        """
        is_supported, reason = ResponseValidator.verify_citation_support(
            claim="Metformin causes severe hypoglycemia and should be discontinued.",
            citation_id="DOC-WAR-1",
            evidence_bundle=evidence_bundle_with_warfarin,
        )
        assert is_supported is False
        assert "Citation unsupported" in reason
        assert "entity mismatch" in reason.lower() or "refers to 'metformin'" in reason

    def test_valid_citation_attached_to_unrelated_claim_flagged(self, evidence_bundle_with_warfarin):
        """
        DOC-WAR-1 is valid, but the claim discusses unrelated lifestyle topics with zero clinical overlap.
        Must be flagged as unsupported.
        """
        is_supported, reason = ResponseValidator.verify_citation_support(
            claim="Patient enjoys morning gardening and walks in the local park.",
            citation_id="DOC-WAR-1",
            evidence_bundle=evidence_bundle_with_warfarin,
        )
        assert is_supported is False
        assert "Citation unsupported" in reason
        assert "insufficient overlap" in reason

    def test_valid_citation_with_genuine_support_passes(self, evidence_bundle_with_warfarin):
        """Valid citation ID attached to an accurate, supported claim passes validation."""
        is_supported, reason = ResponseValidator.verify_citation_support(
            claim="Warfarin treatment carries risk of bleeding complications requiring INR monitoring.",
            citation_id="DOC-WAR-1",
            evidence_bundle=evidence_bundle_with_warfarin,
        )
        assert is_supported is True
        assert "supported" in reason.lower()


# ==============================================================================
# 6. MALFORMED / EMPTY LLM NARRATIVE -> DETERMINISTIC FALLBACK FLOOR
# ==============================================================================
class TestDeterministicFallbackFloor:
    """
    When generative output is malformed, corrupted, empty, or fails, the pipeline
    falls back cleanly to the deterministic baseline without throwing HTTP 500.
    """

    def test_deterministic_brief_and_explanation_assembly_under_llm_failure(self):
        service = AdherenceAnalysisService()
        metrics = AdherenceMetrics(
            patient_id=1,
            period="7d",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 7),
            expected_doses=14,
            total_taken=7,
            total_missed=7,
            total_skipped=0,
            total_snoozed=0,
            adherence_rate=50.0,
            missed_rate=50.0,
            skipped_rate=0.0,
            current_streak=0,
            best_streak=2,
            time_slot_breakdown={},
            day_of_week_breakdown=[],
            trend="DECLINING",
            detected_patterns=["Evening doses missed"],
            should_escalate=True,
            escalation_reasons=["Consecutive missed doses"],
            reasoned_events=[],
        )
        safety = SafetyAssessment(
            patient_id=1,
            evaluated_at=utcnow(),
            risk_level="HIGH",
            requires_human_review=True,
            recommended_action="Requires immediate clinician review for consecutive missed doses.",
        )
        bundle = FindingEvidenceBundle(
            patient_id=1,
            assessment_risk_level="HIGH",
            results=[],
        )

        # Deterministic patient explanation
        explanation = service._build_patient_explanation(metrics, safety, barriers=[], evidence_bundle=bundle)
        assert "50.0%" in explanation.summary
        assert "vital to keep your condition stable" in explanation.why_it_matters
        assert "Do not take extra or double doses" in explanation.what_to_do_next

        # Deterministic clinical brief
        brief = service._build_clinical_brief(metrics, safety, barriers=[], evidence_bundle=bundle)
        assert brief.adherence_rate == 50.0
        assert brief.safety_risk_level == "HIGH"
        assert brief.requires_human_review is True
        assert brief.generation_status == GenerationStatus.FALLBACK
