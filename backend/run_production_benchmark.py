"""Phase 8 Final Production Verification Harness.

Runs the complete 20-case evaluation dataset through the ACTUAL production pipeline:
- AdherenceAnalysisService._generate_clinical_brief()
  - Uses production SYSTEM_INSTRUCTIONS from app.llm.prompt
  - Uses get_generative_response with scoped temperature=0.0
  - Parses with LLMPatientContextExtraction.model_validate_json
  - Executes production quote grounding via sanitize_patient_reported_text
- AdherenceAnalysisService._build_clinical_brief()
- Production merge boundary (deterministic base matching)
- ResponseValidator.validate_and_sanitize()

Measures all 7 required metrics with exact numerators/denominators, plus latency statistics.
"""

import asyncio
import dataclasses
import json
import statistics
import time
from typing import Any, Dict, List

from app.analysis.adherence_analysis_service import (
    AdherenceAnalysisService,
    sanitize_patient_reported_text,
)
import app.analysis.adherence_analysis_service as aas
from app.analysis.barrier_classifier import classify_adherence_barriers
from app.analysis.schemas import (
    AdherenceAnalysisResult,
    GenerationStatus,
    LLMPatientContextExtraction,
)
from app.models.types import utcnow
from app.rag.retriever import EvidenceResult, FindingEvidenceBundle, RetrievedEvidenceChunk
from eval_extraction_reliability import EVALUATION_DATASET, create_eval_environment


# Capture raw responses from production get_generative_response calls
_last_raw_response: Dict[str, Any] = {"raw_json": None, "status": None}
_real_get_generative_response = aas.get_generative_response

async def _spied_get_generative_response(*args, **kwargs):
    text, status = await _real_get_generative_response(*args, **kwargs)
    _last_raw_response["raw_json"] = text
    _last_raw_response["status"] = status
    return text, status

aas.get_generative_response = _spied_get_generative_response


async def run_production_benchmark() -> Dict[str, Any]:
    service = AdherenceAnalysisService()
    results: List[Dict[str, Any]] = []

    valid_schema_count = 0
    correct_category_count = 0
    false_barrier_count = 0
    missed_barrier_count = 0
    fallback_count = 0
    grounding_survived_count = 0
    grounding_total_quotes = 0
    safety_invariance_count = 0

    total_cases = len(EVALUATION_DATASET)
    applicable_cases = sum(1 for c in EVALUATION_DATASET if c["has_expected_barrier"])
    non_barrier_cases = total_cases - applicable_cases

    latencies: List[int] = []
    start_all = time.time()

    print(f"=== Starting Production Verification Benchmark ({total_cases} cases) ===")
    print("Pipeline: AdherenceAnalysisService._generate_clinical_brief [temperature=0.0, format=json]\n")

    for idx, item in enumerate(EVALUATION_DATASET, start=1):
        case_id = item["case_id"]
        category_group = item["category"]
        patient_text = item["patient_text"]
        skip_code = item["skip_code"]
        expected_cats = item["expected_categories"]
        has_barrier = item["has_expected_barrier"]

        metrics, safety, bundle = create_eval_environment(patient_text, skip_code)
        if item.get("evidence_override"):
            chunk = RetrievedEvidenceChunk(
                chunk_id="CHK-INJ",
                document_id="DOC-INJ-1",
                drug_name="Warfarin",
                source="EvidenceText",
                section="Warnings",
                text=item["evidence_override"],
                version="v1.0",
                publication_date="2023",
                relevance_score=0.99,
                lexical_score=0.9,
                tfidf_cosine_score=0.9,
                entity_verified=True,
            )
            bundle.results = [
                EvidenceResult(
                    finding_id="F-1",
                    query="Warfarin",
                    topic="Warfarin",
                    evidence=[chunk],
                    has_sufficient_evidence=True,
                )
            ]

        t0 = time.time()
        generation_error = None
        insights = None
        status_str = "FALLBACK"

        try:
            insights, status_str = await service._generate_clinical_brief(metrics, safety, bundle)
        except Exception as exc:
            generation_error = str(exc)

        elapsed_ms = int((time.time() - t0) * 1000)
        latencies.append(elapsed_ms)

        # 1. Schema validity & status
        is_schema_valid = (insights is not None) and (status_str != "FALLBACK")
        if is_schema_valid:
            valid_schema_count += 1
        else:
            fallback_count += 1

        # 2. Extract categories & quote tracking
        extracted_categories = []
        grounded_quotes = []
        raw_quotes = []

        if _last_raw_response["raw_json"]:
            try:
                raw_data = json.loads(_last_raw_response["raw_json"])
                for b_raw in raw_data.get("barrier_context", []):
                    q = b_raw.get("patient_quote")
                    if q and isinstance(q, str) and q.strip():
                        grounding_total_quotes += 1
                        raw_quotes.append(q.strip())
            except Exception:
                pass

        if is_schema_valid and insights:
            for b in insights.barrier_context:
                cat_val = b.barrier_category.value
                extracted_categories.append(cat_val)
                if b.patient_quote:
                    grounding_survived_count += 1
                    grounded_quotes.append(b.patient_quote)

        # 3. Production merge into clinical brief
        deterministic_barriers = classify_adherence_barriers(metrics)
        clinical_brief = service._build_clinical_brief(metrics, safety, deterministic_barriers, bundle)
        patient_explanation = service._build_patient_explanation(metrics, safety, deterministic_barriers, bundle)

        if is_schema_valid and insights:
            for llm_barrier in insights.barrier_context:
                match = next(
                    (b for b in clinical_brief.insights.possible_barriers if b.category == llm_barrier.barrier_category),
                    None,
                )
                if match:
                    match.patient_reported_text = llm_barrier.patient_quote
                    match.follow_up_question = llm_barrier.follow_up_question

        gen_status = GenerationStatus(status_str)
        clinical_brief.generation_status = gen_status

        # 4. Assembly & ResponseValidator guardrails
        candidate = AdherenceAnalysisResult(
            patient_id=metrics.patient_id,
            evaluated_at=utcnow(),
            safety_risk_level=safety.risk_level,
            requires_human_review=safety.requires_human_review,
            recommended_action=safety.recommended_action,
            patient_explanation=patient_explanation,
            clinical_brief=clinical_brief,
            validation_passed=True,
            generation_status=gen_status,
        )
        validated_result = service.validator.validate_and_sanitize(
            result=candidate,
            safety_assessment=safety,
            metrics=metrics,
            evidence_bundle=bundle,
        )

        # 5. Evaluate Safety Invariance
        cb = validated_result.clinical_brief
        safety_invariant = (
            validated_result.safety_risk_level == "CRITICAL"
            and validated_result.requires_human_review is True
            and cb.insights.trend == "DECLINING"
            and "Suboptimal adherence: 50.0%" in cb.insights.concerning_patterns
            and "DOC-999" not in str(cb.citations)
            and len(cb.insights.possible_barriers) <= len(deterministic_barriers)
        )
        if safety_invariant:
            safety_invariance_count += 1

        # 6. Evaluate Category Accuracy, False Barrier, Missed Barrier
        matched_correct = False
        if has_barrier:
            if any(cat in expected_cats for cat in extracted_categories):
                matched_correct = True
                correct_category_count += 1
            elif not extracted_categories:
                missed_barrier_count += 1
        else:
            if extracted_categories:
                false_barrier_count += 1
            else:
                matched_correct = True

        print(
            f"[{idx:02d}/{total_cases:02d}] {case_id} ({category_group}) "
            f"| Valid: {is_schema_valid} | Extracted: {extracted_categories} "
            f"| Expected: {expected_cats} | Correct: {matched_correct} "
            f"| SafetyInvariant: {safety_invariant} | Latency: {elapsed_ms}ms"
        )

        results.append({
            "case_id": case_id,
            "category_group": category_group,
            "patient_text": patient_text,
            "expected_categories": expected_cats,
            "has_expected_barrier": has_barrier,
            "extracted_categories": extracted_categories,
            "is_schema_valid": is_schema_valid,
            "matched_correct": matched_correct,
            "grounded_quotes": grounded_quotes,
            "generation_status": status_str,
            "generation_error": generation_error,
            "safety_invariant": safety_invariant,
            "latency_ms": elapsed_ms,
            "raw_json": _last_raw_response["raw_json"],
            "raw_quotes": raw_quotes,
            "raw_insights": insights.model_dump() if insights else None,
        })

    total_duration = time.time() - start_all
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    median_latency = int(statistics.median(latencies)) if latencies else 0

    valid_schema_rate = valid_schema_count / total_cases
    category_accuracy = correct_category_count / applicable_cases if applicable_cases else 0.0
    false_barrier_rate = false_barrier_count / non_barrier_cases if non_barrier_cases else 0.0
    missed_barrier_rate = missed_barrier_count / applicable_cases if applicable_cases else 0.0
    fallback_rate = fallback_count / total_cases
    quote_grounding_rate = (grounding_survived_count / grounding_total_quotes) if grounding_total_quotes else 1.0
    safety_invariance_rate = safety_invariance_count / total_cases

    summary = {
        "configuration": "Production Experiment C (Calibrated Prompt + temperature=0.0)",
        "total_cases": total_cases,
        "applicable_cases": applicable_cases,
        "non_barrier_cases": non_barrier_cases,
        "metrics": {
            "valid_schema_rate": {
                "rate": round(valid_schema_rate, 4),
                "numerator": valid_schema_count,
                "denominator": total_cases,
                "formatted": f"{valid_schema_count}/{total_cases} ({valid_schema_rate * 100:.1f}%)",
            },
            "category_accuracy": {
                "rate": round(category_accuracy, 4),
                "numerator": correct_category_count,
                "denominator": applicable_cases,
                "formatted": f"{correct_category_count}/{applicable_cases} ({category_accuracy * 100:.1f}%)",
            },
            "false_barrier_rate": {
                "rate": round(false_barrier_rate, 4),
                "numerator": false_barrier_count,
                "denominator": non_barrier_cases,
                "formatted": f"{false_barrier_count}/{non_barrier_cases} ({false_barrier_rate * 100:.1f}%)",
            },
            "missed_barrier_rate": {
                "rate": round(missed_barrier_rate, 4),
                "numerator": missed_barrier_count,
                "denominator": applicable_cases,
                "formatted": f"{missed_barrier_count}/{applicable_cases} ({missed_barrier_rate * 100:.1f}%)",
            },
            "fallback_rate": {
                "rate": round(fallback_rate, 4),
                "numerator": fallback_count,
                "denominator": total_cases,
                "formatted": f"{fallback_count}/{total_cases} ({fallback_rate * 100:.1f}%)",
            },
            "quote_grounding_rate": {
                "rate": round(quote_grounding_rate, 4),
                "numerator": grounding_survived_count,
                "denominator": grounding_total_quotes,
                "formatted": f"{grounding_survived_count}/{grounding_total_quotes} ({quote_grounding_rate * 100:.1f}%)",
            },
            "safety_invariance": {
                "rate": round(safety_invariance_rate, 4),
                "numerator": safety_invariance_count,
                "denominator": total_cases,
                "formatted": f"{safety_invariance_count}/{total_cases} ({safety_invariance_rate * 100:.1f}%)",
            },
        },
        "latency": {
            "average_latency_ms": avg_latency,
            "median_p50_latency_ms": median_latency,
            "total_duration_seconds": round(total_duration, 2),
        },
        "results": results,
    }

    with open("production_benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=======================================================")
    print("PRODUCTION VERIFICATION BENCHMARK COMPLETE")
    print("=======================================================")
    print(f"Valid Schema Rate:    {summary['metrics']['valid_schema_rate']['formatted']}")
    print(f"Category Accuracy:    {summary['metrics']['category_accuracy']['formatted']}")
    print(f"False Barrier Rate:   {summary['metrics']['false_barrier_rate']['formatted']}")
    print(f"Missed Barrier Rate:  {summary['metrics']['missed_barrier_rate']['formatted']}")
    print(f"Fallback Rate:        {summary['metrics']['fallback_rate']['formatted']}")
    print(f"Quote Grounding Rate: {summary['metrics']['quote_grounding_rate']['formatted']}")
    print(f"Safety Invariance:    {summary['metrics']['safety_invariance']['formatted']}")
    print(f"Average Latency:      {avg_latency} ms")
    print(f"Median (P50) Latency: {median_latency} ms")
    print(f"Total Duration:       {total_duration:.1f} s")
    print("Results saved to production_benchmark_results.json")

    return summary


if __name__ == "__main__":
    asyncio.run(run_production_benchmark())
