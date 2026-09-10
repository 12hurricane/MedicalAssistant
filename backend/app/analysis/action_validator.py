"""
Patient Action Allow-List Validator

Validates that the patient-facing `what_to_do_next` field resolves to an
explicitly permitted action category.

Design rationale:
A regex blacklist (blacklist-based approach) is insufficient because:
  - Language is ambiguous ("compensate for the missed dose" passes all blacklists)
  - The space of dangerous phrasings is unbounded

An allow-list (whitelist-based approach) is safer:
  - We define exactly what a safe patient instruction looks like
  - Anything outside that list is rejected and replaced with the safe default
  - The safe default is always acceptable regardless of clinical context
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ActionClass(str, Enum):
    ALLOWED = "ALLOWED"
    RESTRICTED = "RESTRICTED"
    UNCLASSIFIED = "UNCLASSIFIED"


@dataclass
class ActionValidationResult:
    action_class: ActionClass
    matched_category: Optional[str]
    original_text: str
    is_safe: bool
    replacement_used: bool
    replacement_text: Optional[str] = None
    reason: Optional[str] = None


# -----------------------------------------------------------------------
# Safe default. Always clinically acceptable.
# -----------------------------------------------------------------------
SAFE_DEFAULT_ACTION = (
    "Take your next dose at its regular scheduled time. "
    "Do not take extra or double doses. "
    "Contact your doctor or pharmacist if you have any questions."
)

# -----------------------------------------------------------------------
# ALLOWED action patterns (intent-level matching)
# Each tuple: (category_label, list_of_keyword_phrases)
# A match means the text is an ALLOWED action.
# -----------------------------------------------------------------------
_ALLOWED_PATTERNS: List[tuple] = [
    ("take_next_dose_scheduled", [
        "next dose at", "scheduled time", "take it at the regular",
        "take your medication as", "take as directed", "at the usual time",
    ]),
    ("contact_care_team", [
        "contact your doctor", "reach out to your doctor", "call your doctor",
        "contact your care", "speak with your care", "inform your doctor",
        "let your care team know", "talk to your doctor", "consult your doctor",
        "notify your care", "contact your pharmacist",
    ]),
    ("ask_pharmacist_clinician", [
        "ask your pharmacist", "ask your doctor", "ask your clinician",
        "speak with your pharmacist", "consult your pharmacist",
        "discuss with your pharmacist", "check with your pharmacist",
    ]),
    ("review_medication_instructions", [
        "review your medication", "read your medication", "check your medication instructions",
        "follow the instructions", "refer to your prescription",
    ]),
    ("discuss_barriers", [
        "discuss any difficulties", "talk about challenges", "discuss barriers",
        "share your concerns", "tell your care team about", "mention to your doctor",
    ]),
    ("safe_skip_guidance", [
        "do not take extra", "do not double", "skip the missed dose",
        "if you miss a dose, take it as soon as", "do not make up for",
    ]),
]

# -----------------------------------------------------------------------
# RESTRICTED action patterns (intent-level matching)
# A match means the text contains a RESTRICTED action — must be rejected.
# -----------------------------------------------------------------------
_RESTRICTED_PATTERNS: List[tuple] = [
    ("change_dose_amount", [
        "increase your dose", "decrease your dose",
        "take a higher dose", "take a lower dose", "adjust your dose",
        "change the amount", "modify the dose",
        "take more mg", "take less mg",
    ]),
    ("change_frequency_timing", [
        "take it more often", "take it less often", "change the frequency",
        "change how often", "change the timing", "adjust the schedule",
        "switch the time", "move the dose to",
    ]),
    ("stop_medication", [
        # Must be direct imperative, NOT negated forms like "do not stop"
        "stop taking your medication", "stop your medication",
        "discontinue your medication", "cease taking your medication",
        "halt your medication", "quit taking your medication",
        "stop all your medication", "stop all medication",
    ]),
    ("restart_medication", [
        "restart your medication", "resume your medication", "start taking again",
        "begin taking again", "go back to taking",
    ]),
    ("compensate_missed_dose", [
        # Must describe compensating action, NOT safety warnings against it
        "compensate for the missed", "compensate by taking",
        "make up for the missed dose by", "take two doses at once",
        "take a double dose", "double your dose",
        "take an extra dose to compensate", "take two pills to catch",
        "catch up by taking extra",
    ]),
    ("recommend_alternative_medication", [
        "switch to a different medication", "switch your medication to",
        "try a different medication instead", "use a different medication",
        "replace with another medication", "substitute with another medication",
        "recommend another medication",
    ]),
]



def _match_patterns(text: str, patterns: List[tuple]) -> Optional[str]:
    """
    Returns the category label of the first matching pattern group, or None.
    """
    text_lower = text.lower()
    for category, phrases in patterns:
        for phrase in phrases:
            if phrase in text_lower:
                return category
    return None


def validate_patient_action(text: str) -> ActionValidationResult:
    """
    Classify a patient-facing action instruction.

        Pipeline:
            1. Check against RESTRICTED patterns → if matched, reject immediately
            2. Check against ALLOWED patterns → if matched, approve
            3. If unclassified → reject and replace with the safe default

    Returns ActionValidationResult with is_safe flag and optional replacement.
    """
    # Stage 1: Check for restricted intent first (conservative — fail fast)
    restricted_match = _match_patterns(text, _RESTRICTED_PATTERNS)
    if restricted_match:
        return ActionValidationResult(
            action_class=ActionClass.RESTRICTED,
            matched_category=restricted_match,
            original_text=text,
            is_safe=False,
            replacement_used=True,
            replacement_text=SAFE_DEFAULT_ACTION,
            reason=f"Matched restricted action category: '{restricted_match}'",
        )

    # Stage 2: Check for explicitly allowed intent
    allowed_match = _match_patterns(text, _ALLOWED_PATTERNS)
    if allowed_match:
        return ActionValidationResult(
            action_class=ActionClass.ALLOWED,
            matched_category=allowed_match,
            original_text=text,
            is_safe=True,
            replacement_used=False,
        )

    # Stage 3: Unclassified text is outside the allow-list and is therefore unsafe.
    return ActionValidationResult(
        action_class=ActionClass.UNCLASSIFIED,
        matched_category=None,
        original_text=text,
        is_safe=False,
        replacement_used=True,
        replacement_text=SAFE_DEFAULT_ACTION,
        reason="Text did not match the patient action allow-list.",
    )
