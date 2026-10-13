import pytest
from app.analysis.schemas import GenerationStatus
from app.analysis.adherence_analysis_service import AdherenceAnalysisService
from app.llm.client import LLMUnavailable
from app.rules.safety_assessment import SafetyAssessment
from app.rag.retriever import FindingEvidenceBundle
import anyio

class DummyMetrics:
    def __init__(self):
        self.patient_id = 1
        self.period = "7d"
        self.expected_doses = 10
        self.total_taken = 5
        self.total_missed = 5
        self.adherence_rate = 50.0
        self.trend = "UNKNOWN"
        self.time_slot_breakdown = {}
        self.detected_patterns = []
        self.escalation_reasons = []
        self.reasoned_events = []
        self.current_streak = 0

@pytest.mark.asyncio
async def test_provider_failure_fails_closed():
    service = AdherenceAnalysisService()
    
    metrics = DummyMetrics()
    safety = SafetyAssessment(patient_id=1, evaluated_at="2023-01-01T00:00:00Z", risk_level="LOW", requires_human_review=False, recommended_action="Routine")
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="LOW")

    async def mock_generate_fail(*args, **kwargs):
        raise LLMUnavailable("Provider offline")
    
    service._generate_clinical_brief = mock_generate_fail
    
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
        assert result.generation_status.value == "FALLBACK"
        assert result.clinical_brief.insights.trend == "UNKNOWN"
        assert result.clinical_brief.generation_status.value == "FALLBACK"
    finally:
        ad_srv.calculate_adherence_score = original_calc
        aas.evaluate_patient_safety = original_eval
        anyio.to_thread.run_sync = original_run_sync

if __name__ == '__main__':
    pytest.main(['-v', __file__])
