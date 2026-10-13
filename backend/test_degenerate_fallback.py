import pytest
from app.analysis.schemas import LLMPatientContextExtraction, ClinicalBrief
from app.analysis.adherence_analysis_service import AdherenceAnalysisService
from app.rules.safety_assessment import SafetyAssessment
from app.rag.retriever import FindingEvidenceBundle
import anyio

class DummyMetrics:
    def __init__(self, adherence_rate):
        self.patient_id = 1
        self.period = "7d"
        self.expected_doses = 10
        self.total_taken = 10 if adherence_rate == 100.0 else 5
        self.total_missed = 0 if adherence_rate == 100.0 else 5
        self.adherence_rate = adherence_rate
        self.trend = "UNKNOWN"
        self.time_slot_breakdown = {}
        self.detected_patterns = []
        self.escalation_reasons = []
        self.reasoned_events = []
        self.current_streak = 0

@pytest.mark.asyncio
async def test_degenerate_generative_output_fallback():
    service = AdherenceAnalysisService()
    
    metrics = DummyMetrics(50.0) # Suboptimal adherence -> baseline will have concerns
    safety = SafetyAssessment(patient_id=1, evaluated_at="2023-01-01T00:00:00Z", risk_level="HIGH", requires_human_review=True, recommended_action="Follow-up")
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH")

    # Mock _generate_clinical_brief to return empty arrays
    async def mock_generate(*args, **kwargs):
        return LLMPatientContextExtraction(barrier_context=[]), "GENERATED_OLLAMA"
    
    service._generate_clinical_brief = mock_generate
    
    class MockDB: pass
    import app.services.adherence_service as ad_srv
    import app.analysis.adherence_analysis_service as aas
    
    original_calc = ad_srv.calculate_adherence_score
    original_eval = aas.evaluate_patient_safety
    original_run_sync = anyio.to_thread.run_sync
    
    async def mock_calc(*args, **kwargs): return metrics
    async def mock_eval(*args, **kwargs): return safety
    async def mock_run_sync(*args, **kwargs): return bundle
    
    ad_srv.calculate_adherence_score = mock_calc
    aas.evaluate_patient_safety = mock_eval
    anyio.to_thread.run_sync = mock_run_sync
    
    try:
        result = await service.evaluate_and_generate(db=MockDB(), patient_id=1)
        
        # Output is accepted (status GENERATED_OLLAMA) and deterministic concerns remain intact
        assert result.generation_status.value == "GENERATED_OLLAMA"
        assert len(result.clinical_brief.insights.concerning_patterns) > 0
        assert "Suboptimal overall adherence: 50.0%" in result.clinical_brief.insights.concerning_patterns
    finally:
        ad_srv.calculate_adherence_score = original_calc
        aas.evaluate_patient_safety = original_eval
        anyio.to_thread.run_sync = original_run_sync

@pytest.mark.asyncio
async def test_inverse_degenerate_generative_output():
    service = AdherenceAnalysisService()
    
    metrics = DummyMetrics(100.0) # Perfect adherence -> baseline will have NO concerns
    safety = SafetyAssessment(patient_id=1, evaluated_at="2023-01-01T00:00:00Z", risk_level="LOW", requires_human_review=False, recommended_action="Routine")
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="LOW")

    # Mock _generate_clinical_brief to return empty arrays
    async def mock_generate(*args, **kwargs):
        return LLMPatientContextExtraction(barrier_context=[]), "GENERATED_OLLAMA"
    
    service._generate_clinical_brief = mock_generate
    
    class MockDB: pass
    import app.services.adherence_service as ad_srv
    import app.analysis.adherence_analysis_service as aas
    
    original_calc = ad_srv.calculate_adherence_score
    original_eval = aas.evaluate_patient_safety
    original_run_sync = anyio.to_thread.run_sync
    
    async def mock_calc(*args, **kwargs): return metrics
    async def mock_eval(*args, **kwargs): return safety
    async def mock_run_sync(*args, **kwargs): return bundle
    
    ad_srv.calculate_adherence_score = mock_calc
    aas.evaluate_patient_safety = mock_eval
    anyio.to_thread.run_sync = mock_run_sync
    
    try:
        result = await service.evaluate_and_generate(db=MockDB(), patient_id=1)
        
        # Baseline had NO concerns, so empty LLM array is perfectly valid -> GENERATED_OLLAMA
        assert result.generation_status.value == "GENERATED_OLLAMA"
        assert len(result.clinical_brief.insights.concerning_patterns) == 0
    finally:
        ad_srv.calculate_adherence_score = original_calc
        aas.evaluate_patient_safety = original_eval
        anyio.to_thread.run_sync = original_run_sync

@pytest.mark.asyncio
async def test_llm_failure_triggers_fallback_and_retains_deterministic_findings():
    service = AdherenceAnalysisService()
    
    metrics = DummyMetrics(50.0) # Suboptimal adherence
    safety = SafetyAssessment(patient_id=1, evaluated_at="2023-01-01T00:00:00Z", risk_level="HIGH", requires_human_review=True, recommended_action="Follow-up")
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH")

    # Mock _generate_clinical_brief to raise an error (e.g. malformed JSON / ValidationError / ValueError)
    async def mock_generate(*args, **kwargs):
        raise ValueError("Invalid LLM output or parsing failure")
    
    service._generate_clinical_brief = mock_generate
    
    class MockDB: pass
    import app.services.adherence_service as ad_srv
    import app.analysis.adherence_analysis_service as aas
    
    original_calc = ad_srv.calculate_adherence_score
    original_eval = aas.evaluate_patient_safety
    original_run_sync = anyio.to_thread.run_sync
    
    async def mock_calc(*args, **kwargs): return metrics
    async def mock_eval(*args, **kwargs): return safety
    async def mock_run_sync(*args, **kwargs): return bundle
    
    ad_srv.calculate_adherence_score = mock_calc
    aas.evaluate_patient_safety = mock_eval
    anyio.to_thread.run_sync = mock_run_sync
    
    try:
        result = await service.evaluate_and_generate(db=MockDB(), patient_id=1)
        
        # Output must fallback gracefully
        assert result.generation_status.value == "FALLBACK"
        assert result.clinical_brief.generation_status.value == "FALLBACK"
        # Deterministic concerns remain 100% intact
        assert len(result.clinical_brief.insights.concerning_patterns) > 0
        assert "Suboptimal overall adherence: 50.0%" in result.clinical_brief.insights.concerning_patterns
        assert result.clinical_brief.safety_risk_level == "HIGH"
        assert result.clinical_brief.requires_human_review is True
    finally:
        ad_srv.calculate_adherence_score = original_calc
        aas.evaluate_patient_safety = original_eval
        anyio.to_thread.run_sync = original_run_sync

if __name__ == '__main__':
    pytest.main(['-v', __file__])
