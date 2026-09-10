from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class RetrievedEvidenceChunkResponse(BaseModel):
    chunk_id: str
    document_id: str
    drug_name: str
    source: str
    section: str
    text: str
    version: str
    publication_date: str
    relevance_score: float
    lexical_score: float
    tfidf_cosine_score: float
    # Defaults False: a safety flag must be earned, never assumed. A payload that
    # somehow omits this field describes evidence whose drug attribution was not
    # checked, and "not checked" must not deserialize into "verified".
    entity_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class EvidenceResultResponse(BaseModel):
    finding_id: str
    query: str
    topic: str
    evidence: List[RetrievedEvidenceChunkResponse] = []
    confidence: float
    has_sufficient_evidence: bool
    retrieval_timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingEvidenceBundleResponse(BaseModel):
    patient_id: int
    assessment_risk_level: str
    results: List[EvidenceResultResponse] = []
    total_evidence_chunks: int
    all_findings_supported: bool

    model_config = ConfigDict(from_attributes=True)
