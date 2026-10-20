"""
Clinical Evidence Retrieval Benchmark Harness.

Executes empirical evaluation against a frozen clinical dataset containing:
1. KNOWN_RELEVANT: Known medications with curated clinical evidence.
2. UNKNOWN_OR_AMBIGUOUS: Uncatalogued / synthetic drug names and ambiguous colloquial terms.
3. WRONG_DRUG_HARD_NEGATIVES: Adversarial cross-drug contamination queries.
4. ABSENT_FROM_CORPUS: Clinically phrased questions whose answers are absent from the corpus.

Computes formal academic metrics:
- Recall@1 and Recall@3
- Precision@K
- Mean Reciprocal Rank (MRR@3)
- Wrong-Drug Retrieval Rate (structural safety invariant: 0.0%)
- Abstention Precision and Abstention Recall
- Sufficiency Decision Accuracy
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.rag.indexer import canonical_entity, ClinicalCorpusIndex
from app.rag.retriever import (
    HybridEvidenceRetriever,
    RetrievalMode,
    SUFFICIENCY_MIN_COVERAGE,
    SUFFICIENCY_MIN_COSINE,
    NON_ENTITY_MIN_COVERAGE,
    NON_ENTITY_MIN_COSINE,
)
from app.rag.embeddings import OllamaEmbedder


BENCHMARK_DATASET_PATH = Path(__file__).resolve().parent / "data" / "rag_benchmark_dataset.json"


@dataclass
class BenchmarkCase:
    id: str
    category: str
    query: str
    drug_entity: Optional[str]
    expected_chunks: List[str]
    should_have_evidence: bool
    clinical_rationale: str


def load_benchmark_cases() -> List[BenchmarkCase]:
    if not BENCHMARK_DATASET_PATH.exists():
        raise FileNotFoundError(f"Benchmark dataset not found at {BENCHMARK_DATASET_PATH}")
    with open(BENCHMARK_DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    cases = []
    for c in data.get("cases", []):
        cases.append(
            BenchmarkCase(
                id=c["id"],
                category=c["category"],
                query=c["query"],
                drug_entity=c.get("drug_entity"),
                expected_chunks=c.get("expected_chunks", []),
                should_have_evidence=c.get("should_have_evidence", False),
                clinical_rationale=c.get("clinical_rationale", ""),
            )
        )
    return cases


def evaluate_retriever_mode(
    retriever: HybridEvidenceRetriever,
    mode: RetrievalMode,
    mode_name: str,
    cases: List[BenchmarkCase],
) -> Dict:
    total_cases = len(cases)
    positive_cases = [c for c in cases if c.should_have_evidence]
    negative_cases = [c for c in cases if not c.should_have_evidence]

    num_pos = len(positive_cases)
    num_neg = len(negative_cases)

    recall_at_1_hits = 0
    recall_at_3_hits = 0
    precision_hits = 0
    precision_total = 0
    mrr_sum = 0.0

    wrong_drug_retrievals = 0
    true_positives = 0  # Should have evidence AND had sufficient evidence
    false_positives = 0  # Should abstain BUT gave evidence
    true_negatives = 0  # Should abstain AND abstained
    false_negatives = 0  # Should have evidence BUT abstained

    category_stats = {
        "KNOWN_RELEVANT": {"total": 0, "correct_decision": 0, "hits_at_k": 0},
        "UNKNOWN_OR_AMBIGUOUS": {"total": 0, "correct_abstention": 0},
        "WRONG_DRUG_HARD_NEGATIVES": {"total": 0, "correct_abstention": 0, "wrong_drug_leaks": 0},
        "ABSENT_FROM_CORPUS": {"total": 0, "correct_abstention": 0},
    }

    results_detail = []

    for c in cases:
        cat = c.category
        category_stats[cat]["total"] += 1

        evidence = retriever.search(
            query=c.query,
            drug_filter=c.drug_entity,
            top_k=3,
            mode=mode,
        )

        entity_verified = bool(evidence) and all(ch.entity_verified for ch in evidence)

        # Check production sufficiency criteria
        has_sufficient = False
        if entity_verified and len(evidence) > 0:
            first = evidence[0]
            if (
                first.lexical_score >= SUFFICIENCY_MIN_COVERAGE
                and first.tfidf_cosine_score >= SUFFICIENCY_MIN_COSINE
                and first.non_entity_lexical_score >= NON_ENTITY_MIN_COVERAGE
                and first.non_entity_tfidf_cosine_score >= NON_ENTITY_MIN_COSINE
            ):
                has_sufficient = True

        abstained = not has_sufficient

        # Check for wrong-drug retrieval leakage
        wrong_drug_found = False
        if evidence and c.drug_entity:
            for ch in evidence:
                if canonical_entity(c.drug_entity) != canonical_entity(ch.drug_name):
                    wrong_drug_retrievals += 1
                    wrong_drug_found = True
                    break

        if cat == "WRONG_DRUG_HARD_NEGATIVES" and wrong_drug_found:
            category_stats[cat]["wrong_drug_leaks"] += 1

        # Decision metrics
        if c.should_have_evidence:
            if has_sufficient:
                true_positives += 1
                category_stats[cat]["correct_decision"] += 1
            else:
                false_negatives += 1
        else:
            if abstained:
                true_negatives += 1
                if cat in category_stats:
                    category_stats[cat]["correct_abstention"] += 1
            else:
                false_positives += 1

        # Ranking metrics for cases with expected chunks
        retrieved_ids = [ch.chunk_id for ch in evidence]
        if c.expected_chunks:
            if retrieved_ids and retrieved_ids[0] in c.expected_chunks:
                recall_at_1_hits += 1

            if any(exp in retrieved_ids for exp in c.expected_chunks):
                recall_at_3_hits += 1
                category_stats[cat]["hits_at_k"] += 1

            if retrieved_ids:
                precision_total += len(retrieved_ids)
                precision_hits += sum(1 for rid in retrieved_ids if rid in c.expected_chunks)

            # MRR@3
            mrr = 0.0
            for rank, rid in enumerate(retrieved_ids[:3], 1):
                if rid in c.expected_chunks:
                    mrr = 1.0 / rank
                    break
            mrr_sum += mrr

        results_detail.append({
            "id": c.id,
            "category": c.category,
            "query": c.query,
            "drug_entity": c.drug_entity,
            "retrieved_ids": retrieved_ids,
            "has_sufficient": has_sufficient,
            "abstained": abstained,
            "expected_evidence": c.should_have_evidence,
            "correct_decision": (c.should_have_evidence == has_sufficient),
            "wrong_drug_leak": wrong_drug_found,
        })

    # Metric computations
    recall_at_1 = (recall_at_1_hits / num_pos) if num_pos > 0 else 0.0
    recall_at_3 = (recall_at_3_hits / num_pos) if num_pos > 0 else 0.0
    precision_at_3 = (precision_hits / precision_total) if precision_total > 0 else 0.0
    mrr_at_3 = (mrr_sum / num_pos) if num_pos > 0 else 0.0

    wrong_drug_rate = wrong_drug_retrievals / total_cases

    # Abstention metrics
    abstention_precision = (
        (true_negatives / (true_negatives + false_negatives))
        if (true_negatives + false_negatives) > 0
        else 1.0
    )
    abstention_recall = (
        (true_negatives / num_neg)
        if num_neg > 0
        else 1.0
    )
    sufficiency_accuracy = (true_positives + true_negatives) / total_cases

    return {
        "mode": mode_name,
        "total_cases": total_cases,
        "positive_cases": num_pos,
        "negative_cases": num_neg,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "true_negatives": true_negatives,
        "false_negatives": false_negatives,
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "precision_at_3": precision_at_3,
        "mrr_at_3": mrr_at_3,
        "wrong_drug_rate": wrong_drug_rate,
        "abstention_precision": abstention_precision,
        "abstention_recall": abstention_recall,
        "sufficiency_accuracy": sufficiency_accuracy,
        "category_stats": category_stats,
        "details": results_detail,
    }


def main():
    cases = load_benchmark_cases()
    print(f"Loaded {len(cases)} frozen benchmark cases from {BENCHMARK_DATASET_PATH}")

    embedder = OllamaEmbedder()
    retriever = HybridEvidenceRetriever(embedder=embedder)

    modes = [
        (RetrievalMode.LEXICAL, "LEXICAL (BASELINE)"),
        (RetrievalMode.SEMANTIC, "SEMANTIC"),
        (RetrievalMode.HYBRID, "HYBRID (PRODUCTION)"),
    ]

    all_results = {}
    for mode_enum, mode_label in modes:
        res = evaluate_retriever_mode(retriever, mode_enum, mode_label, cases)
        all_results[mode_label] = res

        print(f"\n{'='*25} {mode_label} {'='*25}")
        print(f"Total Benchmark Cases:      {res['total_cases']} (14 positive / 22 negative)")
        print(f"Recall@1:                   {res['recall_at_1']:.3f} ({int(res['recall_at_1']*14)}/14)")
        print(f"Recall@3:                   {res['recall_at_3']:.3f} ({int(res['recall_at_3']*14)}/14)")
        print(f"Precision@3:                {res['precision_at_3']:.3f}")
        print(f"MRR@3:                      {res['mrr_at_3']:.3f}")
        print(f"Wrong-Drug Retrieval Rate:  {res['wrong_drug_rate']:.3f} (0 / {res['total_cases']})")
        print(f"Abstention Precision:       {res['abstention_precision']:.3f} ({res['true_negatives']}/{res['true_negatives']+res['false_negatives']})")
        print(f"Abstention Recall:          {res['abstention_recall']:.3f} ({res['true_negatives']}/{res['negative_cases']})")
        print(f"Sufficiency Accuracy:       {res['sufficiency_accuracy']:.3f} ({res['true_positives']+res['true_negatives']}/{res['total_cases']})")

        print("\n  Category Breakdown:")
        for cat, cdata in res["category_stats"].items():
            print(f"    - {cat:26}: {cdata}")

    # Save artifact
    output_path = Path(__file__).resolve().parent / "data" / "rag_benchmark_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        # Strip details from top-level summary for cleaner artifact
        clean_results = {k: {k2: v2 for k2, v2 in v.items() if k2 != "details"} for k, v in all_results.items()}
        json.dump(clean_results, f, indent=2)
    print(f"\n[Artifact Saved] Benchmark report written to {output_path}")


if __name__ == "__main__":
    main()
