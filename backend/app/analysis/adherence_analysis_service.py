"""
Adherence Analysis Service — the Constrained Adherence Intelligence Layer.

NOT an LLM. There is no model call anywhere in this package. Every field of every
response below is composed deterministically from three trusted inputs:

    SafetyAssessment (deterministic rules)
    + AdherenceMetrics (arithmetic over medication_events)
    + FindingEvidenceBundle (retrieval over a fixed corpus)
            |
            v
    template composition  ->  barrier classification  ->  response validator
            |
            v
    structured output

Given identical inputs this returns identical output; it cannot hallucinate because
it cannot generate. The generative phase is a *later* box in the build order and is
not present yet. Until it is, do not describe this layer as AI, an agent, or an LLM
in code, docstrings, endpoint descriptions or the README — the name is a claim, and
that claim would be false.

What the ResponseValidator guards today is therefore composition and invariants, not
model output. It stays because it is the seam the model will eventually be inserted
behind: see ``app/llm/prompt.py`` for the trust-separated prompt contract that
generation must use when it arrives.
"""

from datetime import datetime, timezone
import ast
from typing import List, Optional

import anyio.to_thread
import dataclasses
import json
import logging
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.analysis.barrier_classifier import classify_adherence_barriers
from app.analysis.response_validator import ResponseValidator
from app.analysis.schemas import (
    AdherenceAnalysisResult,
    ClinicalBrief,
    PatientExplanation,
    GenerativeClinicalInsights,
    GenerationStatus,
    LLMPatientContextExtraction,
)
from app.llm.client import get_generative_response, LLMUnavailable
from app.llm.prompt import build_clinician_brief_prompt
from app.rag.retriever import FindingEvidenceBundle, get_default_retriever
from app.rules.safety_assessment import SafetyAssessment, evaluate_patient_safety
from app.services import adherence_service
from app.services.adherence_service import AdherenceMetrics, rate_below


def sanitize_patient_reported_text(raw_text: Optional[str]) -> Optional[str]:
    """Clean model-generated patient_reported_text.

    If the model stringified a list (e.g. "['Too busy today', 'Too busy today']"),
    parse it, deduplicate while preserving order, and join distinct reasons with '; '.
    Trims whitespace and converts empty strings to None.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()
    if not cleaned:
        return None

    # Check if the text looks like a stringified list e.g. "['...']" or '["..."]'
    if cleaned.startswith("[") and cleaned.endswith("]"):
        items = None
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                items = parsed
        except Exception:
            try:
                parsed = ast.literal_eval(cleaned)
                if isinstance(parsed, (list, tuple)):
                    items = list(parsed)
            except Exception:
                items = None

        if items is not None:
            # Extract non-empty string elements and deduplicate in order
            unique_reasons: List[str] = []
            for item in items:
                if item and isinstance(item, str) and item.strip():
                    val = item.strip()
                    if val not in unique_reasons:
                        unique_reasons.append(val)
            if not unique_reasons:
                return None
            return "; ".join(unique_reasons)

    return cleaned


class AdherenceAnalysisService:
    """Deterministic composition of patient explanations and clinician briefs."""

    def __init__(self):
        self.retriever = get_default_retriever()
        self.validator = ResponseValidator()

    async def evaluate_and_generate(
        self,
        db: AsyncSession,
        patient_id: int,
        days: int = 7,
    ) -> AdherenceAnalysisResult:
        """
        Run the analysis pipeline:
        1. Deterministic Metrics
        2. Deterministic Safety Assessment
        3. Evidence Retrieval
        4. Barrier Classification
        5. Structured Patient & Clinician Composition
        6. Guardrail Invariant Validation
        """
        now = datetime.now(timezone.utc)

        # 1. Deterministic Adherence Calculation
        metrics: AdherenceMetrics = await adherence_service.calculate_adherence_score(
            session=db,
            patient_id=patient_id,
            days=days,
        )

        # 2. Deterministic Safety Assessment
        safety: SafetyAssessment = await evaluate_patient_safety(
            db=db,
            patient_id=patient_id,
        )

        # 3. Evidence Retrieval
        # Offloaded to a worker thread. The retriever is sync from top to bottom, and as
        # of the dense arm it makes a blocking HTTP call to the embeddings daemon on the
        # first search of the process. Called directly from this coroutine that call would
        # block the event loop — every other request on this worker stalled behind one
        # corpus embedding — so the sync boundary is crossed explicitly here rather than
        # by making the retriever async and infecting every caller and test with it.
        evidence_bundle: FindingEvidenceBundle = await anyio.to_thread.run_sync(
            self.retriever.retrieve_evidence_bundle, safety
        )

        # 4. Barrier Classification
        barriers = classify_adherence_barriers(metrics)

        # 5. Compose Patient-Facing Explanation (jargon-free, safety-first)
        patient_explanation = self._build_patient_explanation(metrics, safety, barriers, evidence_bundle)

        # 6. Compose Clinical Brief (deterministic base, evidence-backed)
        clinical_brief = self._build_clinical_brief(metrics, safety, barriers, evidence_bundle)

        generation_status = GenerationStatus.FALLBACK

        try:
            insights, status = await self._generate_clinical_brief(metrics, safety, evidence_bundle)
            
            # Merge LLM barrier context into the deterministic barriers
            for llm_barrier in insights.barrier_context:
                # Find matching deterministic barrier by category
                match = next((b for b in clinical_brief.insights.possible_barriers if b.category == llm_barrier.barrier_category), None)
                if match:
                    match.patient_reported_text = llm_barrier.patient_quote
                    match.follow_up_question = llm_barrier.follow_up_question
            
            if status == "GENERATED_OLLAMA":
                generation_status = GenerationStatus.GENERATED_OLLAMA
            elif status == "GENERATED_GEMINI":
                generation_status = GenerationStatus.GENERATED_GEMINI
        except (LLMUnavailable, ValidationError, ValueError) as exc:
            logger.warning("Generative insights failed, falling back to deterministic base: %s", exc)

        clinical_brief.generation_status = generation_status

        # 7. Assemble Candidate Result
        candidate = AdherenceAnalysisResult(
            patient_id=patient_id,
            evaluated_at=now,
            safety_risk_level=safety.risk_level,
            requires_human_review=safety.requires_human_review,
            recommended_action=safety.recommended_action,
            patient_explanation=patient_explanation,
            clinical_brief=clinical_brief,
            validation_passed=True,
            generation_status=generation_status,
        )

        # 8. Run Rigorous Response Validator Guardrails
        validated_result = self.validator.validate_and_sanitize(
            result=candidate,
            safety_assessment=safety,
            metrics=metrics,
            evidence_bundle=evidence_bundle,
        )

        return validated_result

    def _build_patient_explanation(
        self,
        metrics: AdherenceMetrics,
        safety: SafetyAssessment,
        barriers: List,
        evidence_bundle: FindingEvidenceBundle,
    ) -> PatientExplanation:
        """Build empathetic, jargon-free explanation for the patient."""
        # Summary
        #
        # The no-data case is stated first and separately. Every branch below divides
        # the patient into a band by rate, and with no rate there is no band: the old
        # code compared None with >= and, before rates could be null, told a patient
        # with no logged doses "Great work! Your medication adherence is at 100%".
        if metrics.adherence_rate is None:
            summary = (
                f"There are no recorded doses to review for the past {metrics.period}, "
                "so your adherence cannot be measured yet."
            )
        elif metrics.adherence_rate >= 85.0:
            summary = f"Great work! Your medication adherence is at {metrics.adherence_rate}% over the past {metrics.period}."
        elif metrics.adherence_rate >= 70.0:
            summary = f"Your medication adherence is at {metrics.adherence_rate}% over the past {metrics.period}. A few doses were missed."
        else:
            summary = f"Your overall medication adherence is {metrics.adherence_rate}% over the past {metrics.period}. Multiple doses were missed."

        # What the system found
        pattern_texts = []
        morn = metrics.time_slot_breakdown.get("morning")
        eve = metrics.time_slot_breakdown.get("evening")
        # Both rates are read out before comparing. ``total_expected >= 2`` does imply a
        # non-null rate today, so the null check below is redundant — but it is the kind
        # of redundancy worth keeping: it makes the comparison safe on its own terms
        # instead of safe because of a threshold two lines away that someone could
        # reasonably lower to 0 later.
        morn_rate = morn.adherence_rate if morn else None
        eve_rate = eve.adherence_rate if eve else None
        if (
            morn and eve
            and morn.total_expected >= 2 and eve.total_expected >= 2
            and morn_rate is not None and eve_rate is not None
        ):
            if morn_rate > eve_rate + 20:
                pattern_texts.append(f"Morning doses are taken regularly ({morn_rate}%), but evening doses were frequently missed ({eve_rate}%).")
            elif eve_rate > morn_rate + 20:
                pattern_texts.append(f"Evening doses are taken regularly ({eve_rate}%), but morning doses were frequently missed ({morn_rate}%).")

        if metrics.total_missed > 0:
            pattern_texts.append(f"A total of {metrics.total_missed} missed dose(s) occurred.")

        if pattern_texts:
            what_found = " ".join(pattern_texts)
        elif metrics.expected_doses == 0:
            what_found = (
                "No doses were expected in this period, so there is nothing to report yet."
            )
        else:
            what_found = f"{metrics.total_taken} out of {metrics.expected_doses} doses were logged."

        # Why it matters
        if safety.risk_level in ("CRITICAL", "HIGH"):
            why_matters = (
                "Taking your medications consistently is vital to keep your condition stable "
                "and prevent serious health complications."
            )
        else:
            why_matters = "Taking each dose on time helps your treatment work as intended and maintains steady medication levels in your body."

        # What to do next (strictly no double-dosing)
        what_to_do_next = (
            "Take your next dose at its regular scheduled time. "
            "Do not take extra or double doses to make up for missed pills."
        )

        # When to contact care team
        if safety.requires_human_review:
            contact_msg = "Please contact your doctor or care coordinator to review your medication routine and discuss any challenges."
        else:
            contact_msg = "If you experience uncomfortable side effects or have trouble taking doses on time, reach out to your doctor or pharmacist."

        # Citations
        citations: List[str] = []
        for res in evidence_bundle.results:
            for chunk in res.citable_evidence:
                citations.append(f"[{chunk.document_id} | {chunk.version}] {chunk.source} - {chunk.section}")

        return PatientExplanation(
            summary=summary,
            what_the_system_found=what_found,
            why_it_matters=why_matters,
            what_to_do_next=what_to_do_next,
            when_to_contact_care_team=contact_msg,
            citations=citations,
        )

    async def _generate_clinical_brief(
        self,
        metrics: AdherenceMetrics,
        safety: SafetyAssessment,
        evidence_bundle: FindingEvidenceBundle,
    ) -> tuple[LLMPatientContextExtraction, str]:
        """Call the generative model to synthesize clinical insights."""
        patient_texts = [
            e.skip_reason for e in metrics.reasoned_events if e.skip_reason
        ]
        skip_codes = [
            e.skip_reason_code for e in metrics.reasoned_events if e.skip_reason_code
        ]

        prompt = build_clinician_brief_prompt(
            safety_assessment_json=json.dumps(dataclasses.asdict(safety), default=str),
            evidence_json=json.dumps(evidence_bundle.to_llm_projection(), default=str),
            patient_texts=patient_texts,
            structured_skip_reasons=skip_codes,
        )

        response_json, status = await get_generative_response(
            prompt, timeout=600.0, format="json", temperature=0.0
        )
        insights = LLMPatientContextExtraction.model_validate_json(response_json)
        
        # Grounding check: verify patient quotes are actually from the patient texts.
        for barrier in insights.barrier_context:
            raw_quote = barrier.patient_quote
            sanitized = sanitize_patient_reported_text(raw_quote)
            if sanitized:
                # A simple grounding check: the string must appear in one of the patient texts.
                found = False
                for pt in patient_texts:
                    if sanitized.lower() in pt.lower():
                        found = True
                        break
                if not found:
                    sanitized = None
            barrier.patient_quote = sanitized

        return insights, status

    def _build_clinical_brief(
        self,
        metrics: AdherenceMetrics,
        safety: SafetyAssessment,
        barriers: List,
        evidence_bundle: FindingEvidenceBundle,
    ) -> ClinicalBrief:
        """Build structured clinical brief with evidence citations for healthcare providers."""
        concerning = list(metrics.detected_patterns) + list(metrics.escalation_reasons)
        if not concerning and rate_below(metrics.adherence_rate, 80.0):
            concerning.append(f"Suboptimal overall adherence: {metrics.adherence_rate}%")
        elif not concerning and metrics.adherence_rate is None:
            # Stated as a gap in the record, not as a clinical concern about the
            # patient. A clinician reading a brief with an empty findings list would
            # otherwise reasonably read it as "reviewed, nothing found".
            concerning.append(
                "No doses expected in this period — adherence not measurable. "
                "Absence of data, not evidence of adherence."
            )

        # Questions from barriers
        questions = [b.follow_up_question for b in barriers if b.follow_up_question]

        # Citations from evidence bundle. ``citable_evidence`` excludes chunks retrieved
        # without an entity boundary — those may document a different drug, and a
        # citation in a clinical brief asserts that they do not.
        citations: List[str] = []
        for res in evidence_bundle.results:
            for chunk in res.citable_evidence:
                citations.append(f"[{chunk.document_id} | {chunk.version}] {chunk.source} - {chunk.section}")

        insights = GenerativeClinicalInsights(
            trend=metrics.trend,
            concerning_patterns=concerning,
            possible_barriers=barriers,
        )

        return ClinicalBrief(
            patient_id=metrics.patient_id,
            period=metrics.period,
            adherence_rate=metrics.adherence_rate,
            safety_risk_level=safety.risk_level,
            requires_human_review=safety.requires_human_review,
            citations=citations,
            insights=insights,
        )
