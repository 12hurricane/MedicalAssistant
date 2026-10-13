import pytest
import json
from app.rag.retriever import RetrievedEvidenceChunk, EvidenceResult, FindingEvidenceBundle
from app.rag.retriever import SUFFICIENCY_MIN_COVERAGE, SUFFICIENCY_MIN_COSINE, NON_ENTITY_MIN_COVERAGE, NON_ENTITY_MIN_COSINE
from app.llm.prompt import build_clinician_brief_prompt

def build_full_prompt(bundle: FindingEvidenceBundle) -> str:
    return build_clinician_brief_prompt(
        safety_assessment_json='{"status": "MOCK_SAFETY"}',
        evidence_json=json.dumps(bundle.to_llm_projection(), indent=2),
        patient_texts=["Patient text"],
    )

def test_wrong_evidence_must_not_leak():
    valid_chunk = RetrievedEvidenceChunk(
        chunk_id="CHK-WAR-001",
        document_id="DOC-1",
        drug_name="warfarin",
        source="Label",
        section="Warnings",
        text="Valid warfarin evidence text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.9,
        lexical_score=SUFFICIENCY_MIN_COVERAGE + 0.1,
        tfidf_cosine_score=SUFFICIENCY_MIN_COSINE + 0.1,
        non_entity_lexical_score=NON_ENTITY_MIN_COVERAGE + 0.1,
        non_entity_tfidf_cosine_score=NON_ENTITY_MIN_COSINE + 0.1,
        entity_verified=True
    )
    
    invalid_chunk = RetrievedEvidenceChunk(
        chunk_id="CHK-SRT-001",
        document_id="DOC-2",
        drug_name="sertraline",
        source="Label",
        section="Warnings",
        text="Invalid sertraline evidence text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.9,
        lexical_score=SUFFICIENCY_MIN_COVERAGE + 0.1,
        tfidf_cosine_score=SUFFICIENCY_MIN_COSINE + 0.1,
        non_entity_lexical_score=NON_ENTITY_MIN_COVERAGE + 0.1,
        non_entity_tfidf_cosine_score=NON_ENTITY_MIN_COSINE + 0.1,
        entity_verified=False
    )
    
    result = EvidenceResult(
        finding_id="F-1",
        query="test",
        topic="test",
        evidence=[valid_chunk, invalid_chunk],
        has_sufficient_evidence=True
    )
    
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH", results=[result])
    
    # Check projection directly
    projection = bundle.to_llm_projection()
    assert projection["results"][0]["evidence_status"] == "SUFFICIENT"
    clinical_evidence = projection["results"][0]["clinical_evidence"]
    assert len(clinical_evidence) == 1
    assert clinical_evidence[0]["medication"] == "warfarin"
    
    # Check COMPLETE prompt
    prompt = build_full_prompt(bundle)
    assert "Valid warfarin evidence text" in prompt
    assert "Invalid sertraline evidence text" not in prompt
    assert "sertraline" not in prompt
    assert '"evidence_status": "SUFFICIENT"' in prompt

def test_insufficient_evidence_must_not_leak():
    weak_chunk = RetrievedEvidenceChunk(
        chunk_id="CHK-WAR-001",
        document_id="DOC-1",
        drug_name="warfarin",
        source="Label",
        section="Warnings",
        text="Weak warfarin evidence text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.9,
        lexical_score=SUFFICIENCY_MIN_COVERAGE - 0.1,
        tfidf_cosine_score=0.0,
        non_entity_lexical_score=0.0,
        non_entity_tfidf_cosine_score=0.0,
        entity_verified=True
    )
    
    result = EvidenceResult(
        finding_id="F-1",
        query="test",
        topic="test",
        evidence=[weak_chunk],
        has_sufficient_evidence=False
    )
    
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH", results=[result])
    
    prompt = build_full_prompt(bundle)
    assert '"evidence_status": "INSUFFICIENT"' in prompt
    assert '"clinical_evidence": []' in prompt
    assert "Weak warfarin evidence text" not in prompt

def test_stronger_invariant_complex_bundle():
    valid_chunk = RetrievedEvidenceChunk(
        chunk_id="CHK-WAR-001",
        document_id="DOC-1",
        drug_name="warfarin",
        source="Label",
        section="Warnings",
        text="Valid warfarin text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.9,
        semantic_score=0.9,
        lexical_score=SUFFICIENCY_MIN_COVERAGE + 0.1,
        tfidf_cosine_score=SUFFICIENCY_MIN_COSINE + 0.1,
        non_entity_lexical_score=NON_ENTITY_MIN_COVERAGE + 0.1,
        non_entity_tfidf_cosine_score=NON_ENTITY_MIN_COSINE + 0.1,
        entity_verified=True
    )
    wrong_entity = RetrievedEvidenceChunk(
        chunk_id="CHK-SRT-001",
        document_id="DOC-2",
        drug_name="sertraline",
        source="Label",
        section="Warnings",
        text="Sertraline text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.8,
        semantic_score=0.8,
        lexical_score=SUFFICIENCY_MIN_COVERAGE + 0.1,
        tfidf_cosine_score=SUFFICIENCY_MIN_COSINE + 0.1,
        non_entity_lexical_score=NON_ENTITY_MIN_COVERAGE + 0.1,
        non_entity_tfidf_cosine_score=NON_ENTITY_MIN_COSINE + 0.1,
        entity_verified=False
    )
    weak_chunk = RetrievedEvidenceChunk(
        chunk_id="CHK-WAR-002",
        document_id="DOC-1",
        drug_name="warfarin",
        source="Label",
        section="Warnings",
        text="Weak warfarin text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.4,
        semantic_score=0.4,
        lexical_score=SUFFICIENCY_MIN_COVERAGE - 0.1,
        tfidf_cosine_score=SUFFICIENCY_MIN_COSINE + 0.1,
        non_entity_lexical_score=NON_ENTITY_MIN_COVERAGE + 0.1,
        non_entity_tfidf_cosine_score=NON_ENTITY_MIN_COSINE + 0.1,
        entity_verified=True
    )
    high_sim_wrong = RetrievedEvidenceChunk(
        chunk_id="CHK-SRT-002",
        document_id="DOC-2",
        drug_name="sertraline",
        source="Label",
        section="Warnings",
        text="High sim sertraline text",
        version="1.0",
        publication_date="2023",
        relevance_score=0.99,
        semantic_score=0.99,
        lexical_score=SUFFICIENCY_MIN_COVERAGE + 0.1,
        tfidf_cosine_score=SUFFICIENCY_MIN_COSINE + 0.1,
        non_entity_lexical_score=NON_ENTITY_MIN_COVERAGE + 0.1,
        non_entity_tfidf_cosine_score=NON_ENTITY_MIN_COSINE + 0.1,
        entity_verified=False
    )
    
    result = EvidenceResult(
        finding_id="F-1",
        query="test",
        topic="test",
        evidence=[valid_chunk, wrong_entity, weak_chunk, high_sim_wrong],
        has_sufficient_evidence=True
    )
    
    bundle = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH", results=[result])
    
    # Check projection directly
    projection = bundle.to_llm_projection()
    clinical_evidence = projection["results"][0]["clinical_evidence"]
    assert len(clinical_evidence) == 1
    assert clinical_evidence[0]["medication"] == "warfarin"
    assert clinical_evidence[0]["evidence_text"] == "Valid warfarin text"
    
    # Verify no raw fields exist in the projection
    bundle_json = json.dumps(projection)
    assert "lexical_score" not in bundle_json
    assert "semantic_score" not in bundle_json
    assert "entity_verified" not in bundle_json
    assert "relevance_score" not in bundle_json
    
    # Check COMPLETE prompt
    prompt = build_full_prompt(bundle)
    assert "Valid warfarin text" in prompt
    assert "Sertraline text" not in prompt
    assert "Weak warfarin text" not in prompt
    assert "High sim sertraline text" not in prompt
    assert "sertraline" not in prompt

if __name__ == '__main__':
    pytest.main(['-v', __file__])
