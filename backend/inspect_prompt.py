import json
from app.rag.retriever import RetrievedEvidenceChunk, EvidenceResult, FindingEvidenceBundle
from app.rag.retriever import SUFFICIENCY_MIN_COVERAGE, SUFFICIENCY_MIN_COSINE, NON_ENTITY_MIN_COVERAGE, NON_ENTITY_MIN_COSINE
from app.llm.prompt import build_clinician_brief_prompt

def test_prompt_inspection():
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
    
    result_sufficient = EvidenceResult(
        finding_id="F-1",
        query="test",
        topic="test",
        evidence=[valid_chunk, invalid_chunk],
        has_sufficient_evidence=True
    )
    
    bundle_sufficient = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH", results=[result_sufficient])
    
    prompt_sufficient = build_clinician_brief_prompt(
        safety_assessment_json='{"status": "MOCK_SAFETY"}',
        evidence_json=json.dumps(bundle_sufficient.to_llm_projection(), indent=2),
        patient_texts=["Patient text"],
    )
    
    print("================== SUFFICIENT PROMPT ==================")
    # Extract just the VERIFIED CLINICAL EVIDENCE section
    sections = prompt_sufficient.split("VERIFIED CLINICAL EVIDENCE -- trusted, retrieved")
    if len(sections) > 1:
        evidence_section = sections[1].split("PATIENT-SELECTED SKIP REASONS")[0]
        print(evidence_section)
    
    result_insufficient = EvidenceResult(
        finding_id="F-2",
        query="test2",
        topic="test2",
        evidence=[invalid_chunk],
        has_sufficient_evidence=False
    )
    
    bundle_insufficient = FindingEvidenceBundle(patient_id=1, assessment_risk_level="HIGH", results=[result_insufficient])
    
    prompt_insufficient = build_clinician_brief_prompt(
        safety_assessment_json='{"status": "MOCK_SAFETY"}',
        evidence_json=json.dumps(bundle_insufficient.to_llm_projection(), indent=2),
        patient_texts=["Patient text"],
    )
    
    print("================== INSUFFICIENT PROMPT ==================")
    sections2 = prompt_insufficient.split("VERIFIED CLINICAL EVIDENCE -- trusted, retrieved")
    if len(sections2) > 1:
        evidence_section2 = sections2[1].split("PATIENT-SELECTED SKIP REASONS")[0]
        print(evidence_section2)

if __name__ == '__main__':
    test_prompt_inspection()
