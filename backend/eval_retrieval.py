"""
Retrieval evaluation harness (Phase 2.1 Experimental).

Evaluates the LEXICAL baseline against experimental SEMANTIC and HYBRID modes
using a structured test set and formal metrics (Recall@k, Precision@k, MRR@k,
Wrong-drug rate, Unsupported-query FP rate, Sufficiency accuracy).

The entity boundary remains mandatory in all modes.
"""

from typing import Dict, List, NamedTuple, Optional, Tuple

from app.rag.indexer import canonical_entity, ClinicalCorpusIndex
from app.rag.retriever import HybridEvidenceRetriever, RetrievalMode, SUFFICIENCY_MIN_COVERAGE, SUFFICIENCY_MIN_COSINE, NON_ENTITY_MIN_COVERAGE, NON_ENTITY_MIN_COSINE
from app.rag.embeddings import OllamaEmbedder

class Case(NamedTuple):
    cls: str
    query: str
    expected_entity: Optional[str] = None
    expected_chunks: Tuple[str, ...] = ()
    should_have_evidence: bool = False

CASES: List[Case] = [
    # -- CLEAR ------------------------------
    Case("CLEAR", "warfarin ibuprofen gastrointestinal bleeding interaction", "warfarin", ("CHK-WAR-001",), True),
    Case("CLEAR", "sildenafil nitrates contraindicated hypotension", "sildenafil", ("CHK-SIL-001", "CHK-SIL-002"), True),
    Case("CLEAR", "propranolol bronchial asthma bronchospasm contraindication", "propranolol", ("CHK-IND-001",), True),
    Case("CLEAR", "metformin severe renal impairment lactic acidosis", "metformin", ("CHK-MET-001",), True),
    Case("CLEAR", "clopidogrel omeprazole CYP2C19 antiplatelet efficacy", "clopidogrel", ("CHK-CLP-001",), True),
    Case("CLEAR", "sertraline tramadol serotonin syndrome", "sertraline", ("CHK-SRT-001",), True),
    Case("CLEAR", "lisinopril spironolactone hyperkalemia renal failure", "lisinopril", ("CHK-LSP-001",), True),
    Case("CLEAR", "amoxicillin penicillin anaphylaxis hypersensitivity", "amoxicillin", ("CHK-AMX-001",), True),
    Case("CLEAR", "warfarin bleeding aspirin clopidogrel antiplatelet", "warfarin", ("CHK-WAR-002",), True),

    # -- REAL_FINDING -----------------------
    Case("REAL_FINDING", "Propranolol Asthma CHRONIC_CONDITION contraindication Life-threatening bronchospasm", "propranolol", ("CHK-IND-001",), True),
    Case("REAL_FINDING", "Sildenafil Nitroglycerin interaction Additive vasodilation Severe hypotension", "sildenafil", ("CHK-SIL-001", "CHK-SIL-002"), True),
    Case("REAL_FINDING", "Warfarin Ibuprofen interaction Displaced protein binding Major bleeding risk", "warfarin", ("CHK-WAR-001",), True),

    # -- NAME_ONLY (must fail sufficiency) --
    Case("NAME_ONLY", "warfarin", "warfarin", (), False),
    Case("NAME_ONLY", "metformin", "metformin", (), False),
    Case("NAME_ONLY", "coumadin", "warfarin", (), False),

    # -- PARAPHRASE -------------------------
    Case("PARAPHRASE", "blood thinner", "warfarin", ("CHK-WAR-001", "CHK-WAR-002"), True),
    Case("PARAPHRASE", "blood thinner bleeding risk", "warfarin", ("CHK-WAR-001", "CHK-WAR-002"), True),
    Case("PARAPHRASE", "clot prevention drug", "warfarin", ("CHK-WAR-001", "CHK-WAR-002"), True),
    Case("PARAPHRASE", "stomach sugar pill", "metformin", ("CHK-MET-001",), True),

    # -- BOUNDARY ---------------------------
    Case("BOUNDARY", "sildenafil contraindicated", "sildenafil", ("CHK-SIL-001", "CHK-SIL-002"), True),

    # -- WITHIN_ENTITY_FP (wrong-topic, correct drug) ---
    # The original RAG-2 failure: a real, multi-word, clinically-phrased query on the
    # WRONG TOPIC (bleeding vs the corpus's actual metformin content, lactic acidosis).
    # Used to clear sufficiency because the drug name alone carried enough rare-token
    # weight. The non-entity floors catch this — ne_coverage and ne_cosine are both
    # hard 0.000 because the wrong-topic tokens (gastrointestinal, bleeding) literally
    # don't appear in the metformin chunk. This defence is structural (wrong words
    # absent) rather than threshold-sensitive, but the case must stay here: a corpus
    # change that adds bleeding vocabulary to a metformin chunk would shift the scores
    # off the structural zero and into the threshold-sensitive zone.
    Case("WITHIN_ENTITY_FP", "metformin gastrointestinal bleeding interaction", "metformin", (), False),

    # -- SEMANTIC FALSE POSITIVES (Unsupported Queries) --
    # Plausible queries for drugs/topics not in the corpus. Must not return evidence.
    Case("FALSE_POSITIVE", "aspirin bleeding risk", "aspirin", (), False),
    Case("FALSE_POSITIVE", "rivaroxaban clot prevention", "rivaroxaban", (), False),
    Case("FALSE_POSITIVE", "insulin hypoglycemia", "insulin", (), False),
    Case("FALSE_POSITIVE", "pizza delivery", None, (), False),
]

def evaluate_mode(retriever: HybridEvidenceRetriever, mode: RetrievalMode, label: str):
    print(f"\n{'='*20} EVALUATING {label} {'='*20}")
    
    total = len(CASES)
    recall_hits = 0
    recall_total = 0
    precision_hits = 0
    precision_total = 0
    mrr_sum = 0.0
    
    wrong_drug_count = 0
    unsupported_fp_count = 0
    sufficiency_correct = 0

    for case in CASES:
        # Simulate retrieval as done in retrieve_for_* methods
        evidence = retriever.search(
            query=case.query,
            drug_filter=case.expected_entity,
            top_k=3,
            mode=mode
        )
        
        # Entity verification
        entity_verified = bool(evidence) and all(c.entity_verified for c in evidence)
        
        # Sufficiency logic identical to production
        has_sufficient = False
        if entity_verified and len(evidence) > 0:
            first = evidence[0]
            if (first.lexical_score >= SUFFICIENCY_MIN_COVERAGE and
                first.tfidf_cosine_score >= SUFFICIENCY_MIN_COSINE and
                first.non_entity_lexical_score >= NON_ENTITY_MIN_COVERAGE and
                first.non_entity_tfidf_cosine_score >= NON_ENTITY_MIN_COSINE):
                has_sufficient = True
        
        # Metrics
        if case.should_have_evidence == has_sufficient:
            sufficiency_correct += 1
            
        if case.cls == "FALSE_POSITIVE" and has_sufficient:
            unsupported_fp_count += 1
            
        # Wrong drug boundary check: did we return chunks belonging to a different drug?
        if evidence:
            for c in evidence:
                # If we asked for a specific entity but got a different one (should be structurally impossible)
                if case.expected_entity and canonical_entity(case.expected_entity) != canonical_entity(c.drug_name):
                    wrong_drug_count += 1
                    
        # Relevance Metrics (only for cases that *should* have evidence)
        if case.expected_chunks:
            recall_total += 1
            retrieved_ids = [c.chunk_id for c in evidence]
            
            # Recall@k (did we find ANY of the expected chunks?)
            if any(exp in retrieved_ids for exp in case.expected_chunks):
                recall_hits += 1
                
            # Precision@k (how many retrieved chunks were expected?)
            if retrieved_ids:
                precision_total += len(retrieved_ids)
                precision_hits += sum(1 for rid in retrieved_ids if rid in case.expected_chunks)
                
            # MRR@k
            mrr = 0.0
            for rank, rid in enumerate(retrieved_ids, 1):
                if rid in case.expected_chunks:
                    mrr = 1.0 / rank
                    break
            mrr_sum += mrr

    recall = (recall_hits / recall_total) if recall_total > 0 else 0.0
    precision = (precision_hits / precision_total) if precision_total > 0 else 0.0
    mrr = (mrr_sum / recall_total) if recall_total > 0 else 0.0
    suff_acc = sufficiency_correct / total
    
    print(f"Recall@k:             {recall:.3f} ({recall_hits}/{recall_total})")
    print(f"Precision@k:          {precision:.3f}")
    print(f"MRR@k:                {mrr:.3f}")
    print(f"Wrong-drug count:     {wrong_drug_count}")
    print(f"Unsupported FP count: {unsupported_fp_count} / {sum(1 for c in CASES if c.cls == 'FALSE_POSITIVE')}")
    print(f"Sufficiency accuracy: {suff_acc:.3f} ({sufficiency_correct}/{total})")

def main():
    print("Loading embedder for evaluation...")
    embedder = OllamaEmbedder()
    retriever = HybridEvidenceRetriever(embedder=embedder)
    
    evaluate_mode(retriever, RetrievalMode.LEXICAL, "LEXICAL (BASELINE)")
    evaluate_mode(retriever, RetrievalMode.SEMANTIC, "SEMANTIC")
    evaluate_mode(retriever, RetrievalMode.HYBRID, "HYBRID")

if __name__ == "__main__":
    main()
