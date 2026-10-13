import pytest
from pydantic import ValidationError
from app.analysis.schemas import GenerativeClinicalInsights, BarrierItem, AdherenceAnalysisResult, PatientExplanation, ClinicalBrief
from app.analysis.response_validator import ResponseValidator, PROHIBITED_DOSING_PATTERNS
from app.rules.safety_assessment import SafetyAssessment
from app.services.adherence_service import AdherenceMetrics
from app.rag.retriever import FindingEvidenceBundle

def test_semantic_safety_generative_concerning_patterns():
    # Test that unsafe dosing advice in generative concerning_patterns is caught
    insights = GenerativeClinicalInsights(
        trend="UNKNOWN",
        concerning_patterns=[
            "Patient missed doses.",
            "You should double your next dose."
        ],
        possible_barriers=[]
    )
    
    result = AdherenceAnalysisResult(
        patient_id=1,
        evaluated_at="2023-01-01T00:00:00Z",
        safety_risk_level="LOW",
        requires_human_review=False,
        recommended_action="Routine follow-up",
        patient_explanation=PatientExplanation(
            summary="Test",
            what_the_system_found="Test",
            why_it_matters="Test",
            what_to_do_next="Test",
            when_to_contact_care_team="Test"
        ),
        clinical_brief=ClinicalBrief(
            patient_id=1,
            period="7d",
            safety_risk_level="LOW",
            requires_human_review=False,
            insights=insights
        )
    )
    
    safety = SafetyAssessment(patient_id=1, evaluated_at="2023-01-01T00:00:00Z", risk_level="LOW", requires_human_review=False, recommended_action="Routine follow-up")

    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="LOW")
    
    ResponseValidator.validate_generative_insights(result, safety, bundle)
    
    # The response validator should replace the unsafe pattern with a redacted string
    assert result.clinical_brief.insights.concerning_patterns[0] == "Patient missed doses."
    assert "REDACTED" in result.clinical_brief.insights.concerning_patterns[1]

def test_semantic_safety_patient_explanation():
    # Test that PatientExplanation with unsafe dosing raises ValidationError
    explanation = PatientExplanation(
        summary="Test",
        what_the_system_found="Test",
        why_it_matters="Test",
        what_to_do_next="Skip the next dose.", # Implicit unsafe action
        when_to_contact_care_team="Test"
    )
    
    # Actually 'Skip the next dose.' is caught by allow-list and replaced with SAFE_DEFAULT_ACTION.
    # But if we use a PROHIBITED_DOSING_PATTERN like 'double your next dose', it raises ValidationError.
    explanation_bad = PatientExplanation(
        summary="Test",
        what_the_system_found="Test",
        why_it_matters="Test",
        what_to_do_next="double your next dose", 
        when_to_contact_care_team="Test"
    )
    
    from app.analysis.response_validator import ValidationError as RespValidationError
    with pytest.raises(RespValidationError):
        ResponseValidator.validate_no_unsafe_dosing(explanation_bad)

if __name__ == '__main__':
    pytest.main(['-v', __file__])
