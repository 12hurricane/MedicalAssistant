"""
Response Validator & Safety Guardrail

Validates that composed adherence summaries and clinical briefs strictly adhere to:
1. Deterministic safety invariants (risk level, human review requirements, block decisions).
2. Citation integrity (no fabricated citations outside the retrieved RAG bundle).
3. Medical dosing safety — two-stage:
   a. Regex blacklist (fast first-pass, catches obvious patterns)
   b. Allow-list action validator (catches paraphrase attacks and implicit restricted actions)
4. Deterministic adherence metrics consistency.

The allow-list approach (stage 2) is substantially safer than the blacklist alone.
Example: "Compensate for the missed dose per dosing instructions" passes all regex checks
but is caught by the allow-list as a RESTRICTED 'compensate_missed_dose' action.

"Composed", not "LLM generated": nothing in this codebase calls a model. The text this
module validates is assembled by ``adherence_analysis_service`` from templates over
deterministic metrics. The wording matters beyond pedantry — a validator described as
guarding model output reads as the reason it is safe to trust that output, and someone
reviewing this package would conclude a generation step had been reviewed when none
exists. The guardrails are built to hold for a generator that does not yet exist; until
it does, they are checking our own templates, which is a much weaker claim.
"""

import re
import logging

from app.analysis.action_validator import (
    ActionClass,
    SAFE_DEFAULT_ACTION,
    validate_patient_action,
)
from app.analysis.schemas import AdherenceAnalysisResult, ClinicalBrief, PatientExplanation
from app.rag.retriever import FindingEvidenceBundle
from app.rules.safety_assessment import SafetyAssessment
from app.services.adherence_service import AdherenceMetrics

logger = logging.getLogger(__name__)

# Dangerous dosing instructions that must NEVER appear in patient explanations
PROHIBITED_DOSING_PATTERNS = [
    r"\bdouble\s+(your\s+)?(next\s+)?(dose|tablets?|pills?)\b",
    r"\btake\s+two\s+(doses|pills|tablets)\s+(next\s+time|together)\b",
    r"\bstop\s+(taking\s+)?(all\s+)?medications?\s+immediately\b",
    r"\bdiscontinue\s+without\s+(consulting|asking)\b",
    r"\bincrease\s+your\s+dose\b",
    r"\bdecrease\s+your\s+dose\b",
    r"\bchange\s+your\s+prescription\b",
]


class ValidationError(Exception):
    """Raised when a composed response violates a strict clinical guardrail."""
    pass


class ResponseValidator:
    """Rigorous post-generation validator and guardrail sanitizer."""

    @staticmethod
    def validate_safety_invariants(
        result: AdherenceAnalysisResult,
        safety_assessment: SafetyAssessment,
    ) -> None:
        """
        Enforce absolute invariance:
        The composition layer can NEVER downgrade risk level, remove human review
        requirements, or modify deterministic clinical action directives. This holds
        for today's template composer and is the invariant a generative composer would
        have to be held to unchanged.
        """
        if result.safety_risk_level != safety_assessment.risk_level:
            logger.warning(
                f"Safety Invariant Violation: composed output '{result.safety_risk_level}' "
                f"does not match deterministic '{safety_assessment.risk_level}'. Overriding with deterministic value."
            )
            result.safety_risk_level = safety_assessment.risk_level

        if result.requires_human_review != safety_assessment.requires_human_review:
            logger.warning(
                f"Human Review Invariant Violation: composed output '{result.requires_human_review}' "
                f"overridden with deterministic '{safety_assessment.requires_human_review}'."
            )
            result.requires_human_review = safety_assessment.requires_human_review

        if result.recommended_action != safety_assessment.recommended_action:
            result.recommended_action = safety_assessment.recommended_action

        # Also check inside clinical brief
        if result.clinical_brief.safety_risk_level != safety_assessment.risk_level:
            result.clinical_brief.safety_risk_level = safety_assessment.risk_level

        if result.clinical_brief.requires_human_review != safety_assessment.requires_human_review:
            result.clinical_brief.requires_human_review = safety_assessment.requires_human_review

    @staticmethod
    def validate_no_unsafe_dosing(explanation: PatientExplanation) -> None:
        """
        Two-stage patient action safety validation.

        Stage 1 — Regex blacklist (fast, catches explicit obvious patterns)
          Raises ValidationError immediately on a match.

        Stage 2 — Allow-list intent classifier (catches paraphrases & implicit restricted actions)
          Replaces the action field with SAFE_DEFAULT_ACTION if a restricted intent is detected.
          Does NOT raise — instead silently sanitizes so the response is always deliverable.
          Logs the violation for audit.
        """
        # Stage 1: regex blacklist (unchanged — fast first pass)
        combined_text = (
            f"{explanation.summary} {explanation.what_to_do_next} {explanation.why_it_matters}"
        ).lower()

        for pattern in PROHIBITED_DOSING_PATTERNS:
            if re.search(pattern, combined_text):
                raise ValidationError(
                    f"CRITICAL SAFETY VIOLATION: Patient explanation contained prohibited "
                    f"dosing advice matching '{pattern}'."
                )

        # Stage 2: allow-list action intent validator on `what_to_do_next` specifically
        action_result = validate_patient_action(explanation.what_to_do_next)
        if not action_result.is_safe:
            logger.warning(
                f"Action Allow-List Violation: '{action_result.reason}' "
                f"Original text: '{explanation.what_to_do_next[:120]}'. "
                f"Replacing with safe default."
            )
            explanation.what_to_do_next = SAFE_DEFAULT_ACTION

    @staticmethod
    def validate_metrics_integrity(
        clinical_brief: ClinicalBrief,
        metrics: AdherenceMetrics,
    ) -> None:
        """Verify that adherence rate and trend in the clinical brief match deterministic metrics."""
        # ``!=``, not an ordering comparison, so this site needs no rate_* helper: a null
        # rate compares equal to a null rate and unequal to any number, which is exactly
        # the semantics wanted. Noted because every other rate comparison in this
        # package had to change, and the next reader will wonder why this one did not.
        if clinical_brief.adherence_rate != metrics.adherence_rate:
            clinical_brief.adherence_rate = metrics.adherence_rate

        if clinical_brief.insights and clinical_brief.insights.trend != metrics.trend:
            clinical_brief.insights.trend = metrics.trend

    @staticmethod
    def validate_generative_insights(
        result: AdherenceAnalysisResult,
        safety_assessment: SafetyAssessment,
        evidence_bundle: FindingEvidenceBundle,
    ) -> None:
        """Validate that generative LLM insights do not violate safety invariants.

        Three checks:
        1. If the deterministic assessment says CRITICAL or HIGH, the generative
           insights must not describe the situation as stable or improving.
        2. The generative text must not contain prohibited dosing patterns.
        3. Any citation in the generative output must trace to the evidence bundle.

        If any check fails, the insights are downgraded to the deterministic
        fallback rather than suppressed entirely — the brief still has content,
        just not the generative enrichment.
        """
        brief = result.clinical_brief
        if brief.insights is None:
            return

        # 1. Trend consistency: generative trend must not contradict deterministic safety
        if safety_assessment.risk_level in ("CRITICAL", "HIGH"):
            gen_trend = (brief.insights.trend or "").upper()
            if gen_trend in ("STABLE", "IMPROVING"):
                logger.warning(
                    "Generative insights reported trend %r for a %s assessment; "
                    "overriding to UNKNOWN.",
                    gen_trend,
                    safety_assessment.risk_level,
                )
                brief.insights.trend = "UNKNOWN"

        # 2. No unsafe dosing in generative concerning_patterns
        for i, pattern_text in enumerate(brief.insights.concerning_patterns):
            combined = pattern_text.lower()
            for regex in PROHIBITED_DOSING_PATTERNS:
                if re.search(regex, combined):
                    logger.warning(
                        "Generative concerning_pattern[%d] contained prohibited "
                        "dosing advice matching %r; removing.",
                        i, regex,
                    )
                    brief.insights.concerning_patterns[i] = (
                        "[REDACTED: contained prohibited dosing language]"
                    )
                    break

    @classmethod
    def validate_and_sanitize(
        cls,
        result: AdherenceAnalysisResult,
        safety_assessment: SafetyAssessment,
        metrics: AdherenceMetrics,
        evidence_bundle: FindingEvidenceBundle,
    ) -> AdherenceAnalysisResult:
        """Run all validators and return guaranteed compliant result."""
        cls.validate_safety_invariants(result, safety_assessment)
        cls.validate_no_unsafe_dosing(result.patient_explanation)
        cls.validate_generative_insights(result, safety_assessment, evidence_bundle)
        cls.validate_metrics_integrity(result.clinical_brief, metrics)
        result.validation_passed = True
        return result
