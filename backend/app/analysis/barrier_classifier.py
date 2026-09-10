"""
Adherence Barrier Classifier

Classifies potential adherence barriers from observed adherence patterns.

Design contract:
- NEVER speculate. Observed numeric discrepancies alone are NOT sufficient evidence.
- A patient-*selected* SkipReasonCode is the strongest evidence available: OBSERVED,
  HIGH confidence. It is a closed vocabulary, so it is trusted and unambiguous.
- Keyword-matching free text is a *guess* and is now labelled as one: INFERRED, LOW
  confidence. It is only consulted when no structured code was recorded.
- All unconfirmed patterns resolve to UNKNOWN / LOW confidence.
- Patient free text is carried in ``BarrierItem.patient_reported_text``, never
  interpolated into ``observed_pattern``. The two have different trust levels and
  merging them makes the boundary unrecoverable downstream.
- This preserves epistemic honesty: the system does not pretend to know
  what it has not been told.

On the demotion of keyword matching: the old code returned OBSERVED / MEDIUM for a
substring hit, so "my stomach was fine, I just forgot" was reported to a clinician as
observed evidence of side effects. Presenting a keyword guess as an observation is an
error a clinician cannot detect from the output.
"""

from typing import List, Optional

from app.analysis.schemas import BarrierCategory, BarrierItem, ConfidenceLevel, EvidenceStatus
from app.models.medication_event import SkipReasonCode
from app.services.adherence_service import (
    AdherenceMetrics,
    rate_at_least,
    rate_at_most,
    rate_below,
)

# Patient-selected code -> barrier category. Trusted: the patient chose from a list.
_SKIP_CODE_CATEGORY_MAP = {
    SkipReasonCode.CLINICIAN_INSTRUCTED: BarrierCategory.CLINICIAN_DIRECTED,
    SkipReasonCode.SIDE_EFFECTS: BarrierCategory.SIDE_EFFECTS,
    SkipReasonCode.UNAVAILABLE: BarrierCategory.ACCESS_AVAILABILITY,
    SkipReasonCode.COST: BarrierCategory.COST,
    SkipReasonCode.SCHEDULE_CONFLICT: BarrierCategory.SCHEDULE_CONFLICT,
    SkipReasonCode.OTHER: BarrierCategory.UNKNOWN,
}

# Keywords in free-text skip_reason that *suggest* each category. Untrusted, and a
# heuristic: consulted only for events with no structured code.
_SKIP_REASON_CATEGORY_MAP = {
    BarrierCategory.SCHEDULE_CONFLICT: [
        "work", "schedule", "shift", "commute", "travel", "busy", "forgot evening",
        "forgot morning", "routine", "meeting", "late", "out of town",
    ],
    BarrierCategory.SIDE_EFFECTS: [
        "side effect", "nausea", "dizzy", "headache", "stomach", "vomiting",
        "rash", "allergic", "felt sick", "unwell",
    ],
    BarrierCategory.COST: [
        "expensive", "cost", "afford", "money", "price", "pharmacy",
    ],
    BarrierCategory.ACCESS_AVAILABILITY: [
        "refill", "out of stock", "pharmacy closed", "no prescription", "ran out",
        "couldn't get", "unavailable",
    ],
    BarrierCategory.MEDICATION_MISUNDERSTANDING: [
        "confused", "didn't know", "wrong time", "instructions", "misunderstood",
        "wasn't sure", "not sure when",
    ],
    BarrierCategory.INTENTIONAL_NON_ADHERENCE: [
        "stopped on purpose", "decided to stop", "don't want", "refused",
        "intentionally", "chose not",
    ],
    BarrierCategory.FORGETFULNESS: [
        "forgot", "forgot to take", "slept through", "distracted",
    ],
}

_SCHEDULE_CONFLICT_KEYWORDS = _SKIP_REASON_CATEGORY_MAP[BarrierCategory.SCHEDULE_CONFLICT]


def _classify_from_skip_reason(reason: str) -> Optional[BarrierCategory]:
    """Guess a BarrierCategory from patient free text, or None. Heuristic."""
    reason_lower = reason.lower()
    for category, keywords in _SKIP_REASON_CATEGORY_MAP.items():
        if any(kw in reason_lower for kw in keywords):
            return category
    return None


def _classify_from_skip_code(code: Optional[str]) -> Optional[BarrierCategory]:
    """Map a patient-selected SkipReasonCode to a BarrierCategory. Exact, not a guess."""
    if not code:
        return None
    try:
        return _SKIP_CODE_CATEGORY_MAP.get(SkipReasonCode(code))
    except ValueError:
        # An unrecognised code is a bug or a stale row, not a barrier. Staying silent
        # is correct: inventing a category here would be the guessing this exists to
        # remove.
        return None


def classify_adherence_barriers(metrics: AdherenceMetrics) -> List[BarrierItem]:
    """
    Generate structured barrier hypotheses from deterministic adherence metrics.

    Rules:
    1a. Patient-selected skip code → specific category (OBSERVED, HIGH).
    1b. No code, but free text keyword hit → category (INFERRED, LOW). A guess,
        reported as a guess.
    2. Consecutive misses without any reason → UNKNOWN, LOW.
    3. Time-of-day discrepancy WITHOUT reason support → UNKNOWN, LOW.
       (We observe the pattern, but do NOT infer a cause without evidence.)
    4. Low adherence, no other signal → UNKNOWN, LOW fallback.
    5a. No expected doses → UNKNOWN, LOW "not measurable" note.
    5b. Good adherence → positive OBSERVED, HIGH note.
    """
    barriers: List[BarrierItem] = []

    # ----------------------------------------------------------------
    # 1. Patient-supplied reasons (highest evidence quality)
    #
    # Structured codes are preferred absolutely. Free text is only consulted for
    # events that carry no code, and produces a weaker, explicitly INFERRED item.
    # ----------------------------------------------------------------
    # Read ``reasoned_events``, not ``missed_events``: a skip reason is recorded on a
    # SKIPPED event, which the MISSED-only list excludes by definition. Falls back to
    # missed_events for any caller still constructing metrics without the newer field.
    reasoned = list(
        getattr(metrics, "reasoned_events", None)
        or getattr(metrics, "missed_events", [])
        or []
    )
    has_any_patient_reason = False
    seen_categories: set = set()

    for ev in reasoned:
        code = getattr(ev, "skip_reason_code", None)
        free_text = getattr(ev, "skip_reason", None)
        if not code and not free_text:
            continue
        has_any_patient_reason = True

        cat = _classify_from_skip_code(code)
        if cat is not None:
            status, confidence = EvidenceStatus.OBSERVED, ConfidenceLevel.HIGH
            rationale = (
                f"Patient selected \"{SkipReasonCode(code).value}\" from the fixed "
                "skip-reason list. Directly reported, not inferred."
            )
        else:
            cat = _classify_from_skip_reason(free_text) if free_text else None
            if cat is None:
                continue
            status, confidence = EvidenceStatus.INFERRED, ConfidenceLevel.LOW
            rationale = (
                "Inferred by keyword match against the patient's free-text note. "
                "No structured skip reason was recorded, so this is a hypothesis "
                "and requires confirmation before being acted on."
            )

        if cat in seen_categories:
            continue
        seen_categories.add(cat)

        if cat is BarrierCategory.CLINICIAN_DIRECTED:
            observed = (
                "Patient recorded that a clinician instructed them to hold this dose. "
                "This is a clinical decision, not a barrier to adherence -- confirm "
                "it against the care plan before treating it as non-adherence."
            )
        else:
            observed = f"Patient-reported reason recorded for a missed dose ({cat.value})."

        barriers.append(
            BarrierItem(
                category=cat,
                status=status,
                confidence=confidence,
                observed_pattern=observed,
                hypothesis_rationale=rationale,
                follow_up_question=_follow_up_for_category(cat),
                # UNTRUSTED. Quoted for the clinician, isolated from trusted prose.
                patient_reported_text=free_text or None,
            )
        )

    # Downstream rules below suppress themselves when the patient has already told us
    # something, on the same principle as before: do not speculate over evidence.
    confirmed_reasons = has_any_patient_reason

    # ----------------------------------------------------------------
    # 2. Time-of-day discrepancy observed — but without patient evidence,
    #    we acknowledge the PATTERN, not the CAUSE.
    # ----------------------------------------------------------------
    morn = metrics.time_slot_breakdown.get("morning")
    eve = metrics.time_slot_breakdown.get("evening")

    if (
        morn and eve
        and morn.total_expected >= 2
        and eve.total_expected >= 2
        and not confirmed_reasons  # Only emit if no confirmed reason already covers it
    ):
        if rate_at_least(morn.adherence_rate, 80.0) and rate_at_most(eve.adherence_rate, 50.0):
            barriers.append(
                BarrierItem(
                    category=BarrierCategory.UNKNOWN,
                    status=EvidenceStatus.UNKNOWN,
                    confidence=ConfidenceLevel.LOW,
                    observed_pattern=(
                        f"Morning adherence is {morn.adherence_rate}%, "
                        f"but evening adherence is {eve.adherence_rate}% "
                        f"({eve.total_missed} missed). "
                        "No patient-confirmed reason is available."
                    ),
                    hypothesis_rationale=(
                        "Time-of-day pattern is observed, but the cause is unconfirmed. "
                        "Possible factors include schedule conflict, fatigue, or forgetfulness — "
                        "but this requires patient confirmation before classification."
                    ),
                    follow_up_question=(
                        "Is there something about your evening routine that makes it "
                        "harder to remember your dose — such as work schedule, fatigue, "
                        "or social activities?"
                    ),
                )
            )
        elif rate_at_least(eve.adherence_rate, 80.0) and rate_at_most(morn.adherence_rate, 50.0):
            barriers.append(
                BarrierItem(
                    category=BarrierCategory.UNKNOWN,
                    status=EvidenceStatus.UNKNOWN,
                    confidence=ConfidenceLevel.LOW,
                    observed_pattern=(
                        f"Evening adherence is {eve.adherence_rate}%, "
                        f"but morning adherence is {morn.adherence_rate}% "
                        f"({morn.total_missed} missed). "
                        "No patient-confirmed reason is available."
                    ),
                    hypothesis_rationale=(
                        "Morning dose pattern observed, but cause is unconfirmed. "
                        "Possible factors include waking schedule variability or morning routine pressure — "
                        "but this requires patient confirmation."
                    ),
                    follow_up_question=(
                        "Do you find it difficult to take your morning dose — "
                        "for example because of an early commute, rushed mornings, "
                        "or waking at inconsistent times?"
                    ),
                )
            )

    # ----------------------------------------------------------------
    # 3. Consecutive misses / acute discontinuation — UNKNOWN, LOW
    # ----------------------------------------------------------------
    has_consecutive = any("consecutive" in r.lower() for r in metrics.escalation_reasons)
    has_multiple_misses = metrics.current_streak == 0 and metrics.total_missed >= 3

    if (has_consecutive or has_multiple_misses) and not confirmed_reasons:
        barriers.append(
            BarrierItem(
                category=BarrierCategory.UNKNOWN,
                status=EvidenceStatus.UNKNOWN,
                confidence=ConfidenceLevel.LOW,
                observed_pattern=(
                    f"Multiple consecutive doses missed ({metrics.total_missed} total in period). "
                    "No patient-confirmed reason recorded."
                ),
                hypothesis_rationale=(
                    "Consecutive non-adherence without explanation could indicate "
                    "side effects, refill exhaustion, illness, or intentional stoppage. "
                    "The cause is unknown without patient input."
                ),
                follow_up_question=(
                    "Have you experienced side effects, had trouble getting a refill, "
                    "been unwell, or had any other reason that led to missing multiple doses?"
                ),
            )
        )

    # ----------------------------------------------------------------
    # 4. General low adherence, no specific signal → UNKNOWN, LOW
    # ----------------------------------------------------------------
    if rate_below(metrics.adherence_rate, 70.0) and not barriers:
        barriers.append(
            BarrierItem(
                category=BarrierCategory.UNKNOWN,
                status=EvidenceStatus.UNKNOWN,
                confidence=ConfidenceLevel.LOW,
                observed_pattern=(
                    f"Overall adherence rate is {metrics.adherence_rate}% "
                    f"({metrics.total_missed} missed of {metrics.expected_doses} expected). "
                    "No specific pattern or confirmed reason identified."
                ),
                hypothesis_rationale=(
                    "Low adherence without a discernible time-slot pattern or patient-confirmed cause. "
                    "Barrier type is INSUFFICIENT_INFORMATION."
                ),
                follow_up_question=(
                    "Would you be able to tell us more about what makes it "
                    "difficult to take your medications consistently?"
                ),
            )
        )

    # ----------------------------------------------------------------
    # 5a. No measurable adherence at all — say so, do not congratulate
    #
    # Split out from the good-adherence fallback below, which it used to fall into.
    # A patient with no logged doses reached that branch and was told "Adherence is on
    # track (None% over the evaluated period)" — wrong twice over: the number is a
    # rendered null, and "on track" is a clinical statement made from no evidence, at
    # HIGH confidence, about the patient a clinician knows least about.
    # ----------------------------------------------------------------
    if not barriers and metrics.adherence_rate is None:
        barriers.append(
            BarrierItem(
                category=BarrierCategory.UNKNOWN,
                status=EvidenceStatus.UNKNOWN,
                confidence=ConfidenceLevel.LOW,
                observed_pattern=(
                    "No doses were expected in the evaluated period, so adherence "
                    "cannot be measured. This is an absence of data, not a good result."
                ),
                hypothesis_rationale=(
                    "Nothing can be concluded about barriers without at least one "
                    "expected dose. Barrier type is INSUFFICIENT_INFORMATION."
                ),
                follow_up_question=(
                    "Has your medication schedule started yet, and are your doses "
                    "being recorded when you take them?"
                ),
            )
        )

    # ----------------------------------------------------------------
    # 5b. Fallback for good adherence
    # ----------------------------------------------------------------
    if not barriers:
        barriers.append(
            BarrierItem(
                category=BarrierCategory.UNKNOWN,
                status=EvidenceStatus.OBSERVED,
                confidence=ConfidenceLevel.HIGH,
                observed_pattern=f"Adherence is on track ({metrics.adherence_rate}% over the evaluated period).",
                hypothesis_rationale="No significant non-adherence barriers detected.",
                follow_up_question=(
                    "Are there any upcoming changes to your routine — travel, shift changes, "
                    "or new commitments — that might affect your medication schedule?"
                ),
            )
        )

    return barriers


def _follow_up_for_category(category: BarrierCategory) -> str:
    """Return a clinically appropriate follow-up question for a confirmed barrier category."""
    _questions = {
        BarrierCategory.SCHEDULE_CONFLICT: (
            "Would adjusting the dose timing to better fit your daily routine help? "
            "Please discuss this with your care team."
        ),
        BarrierCategory.SIDE_EFFECTS: (
            "Please describe the side effects you experienced to your doctor — "
            "they may be able to adjust your treatment plan."
        ),
        BarrierCategory.COST: (
            "Your care team may know of generic alternatives or assistance programs. "
            "Have you discussed the cost burden with your pharmacist or doctor?"
        ),
        BarrierCategory.ACCESS_AVAILABILITY: (
            "Has your care team been informed about the supply issue? "
            "They may be able to arrange an emergency supply or alternative."
        ),
        BarrierCategory.MEDICATION_MISUNDERSTANDING: (
            "Would a brief review of your medication instructions with your pharmacist help? "
            "It's important to take it at the right time and dose."
        ),
        BarrierCategory.INTENTIONAL_NON_ADHERENCE: (
            "Please speak with your doctor before stopping or changing any medication. "
            "They can discuss your concerns and adjust the plan safely."
        ),
        BarrierCategory.FORGETFULNESS: (
            "Would a daily alarm, a pill organizer, or a reminder app help you remember your doses?"
        ),
        BarrierCategory.COMPLEXITY: (
            "Is the number or timing of your medications feeling overwhelming? "
            "A medication review with your pharmacist might simplify your regimen."
        ),
        BarrierCategory.CLINICIAN_DIRECTED: (
            "The patient reports being told to hold this dose. Confirm which "
            "clinician advised it and whether the hold is still in effect, and record "
            "it in the care plan so these doses are not counted as non-adherence."
        ),
    }
    return _questions.get(
        category,
        "Please discuss any difficulties taking your medication with your care team.",
    )
