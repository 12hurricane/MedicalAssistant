"""
Safety Rules Engine

Deterministic service — NOT an AI agent.
Uses clinician-approved protocols for safety triage.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Severity(str, Enum):
    """Safety severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SafetyAction(str, Enum):
    """Actions to take based on severity."""
    PROVIDE_INFORMATION = "PROVIDE_INFORMATION"
    CONTACT_CLINICIAN = "CONTACT_CLINICIAN"
    URGENT_ACTION = "URGENT_ACTION"


@dataclass
class SafetyAssessment:
    """Result of a safety evaluation."""
    severity: Severity
    action: SafetyAction
    reason: str
    requires_human_review: bool
    recommended_message: str


# Symptom keywords mapped to severity
# These should be reviewed and approved by a clinician
URGENT_SYMPTOMS = {
    "chest pain", "difficulty breathing", "shortness of breath",
    "severe bleeding", "loss of consciousness", "fainting",
    "seizure", "convulsion", "severe allergic reaction",
    "anaphylaxis", "swelling of face", "swelling of throat",
    "suicidal thoughts", "self harm", "overdose",
    "severe dizziness", "sudden vision loss", "stroke symptoms",
    "heart attack", "severe abdominal pain",
}

CONCERNING_SYMPTOMS = {
    "rash", "hives", "itching", "nausea", "vomiting",
    "persistent headache", "diarrhea", "constipation",
    "dizziness", "drowsiness", "insomnia", "fatigue",
    "swelling", "bruising", "bleeding", "fever",
    "mood changes", "anxiety", "depression",
    "muscle pain", "joint pain", "stomach upset",
}

# Requests that are outside system scope
OUT_OF_SCOPE_PATTERNS = {
    "stop taking", "change dose", "replace medicine",
    "prescribe", "diagnose", "should i take",
    "is it safe to stop", "can i take more",
    "switch to", "alternative medicine",
}


def assess_patient_report(report_text: str) -> SafetyAssessment:
    """
    Evaluate a patient's reported symptom or concern.

    This uses deterministic keyword matching with validated rules.

    Args:
        report_text: Patient's description of their concern

    Returns:
        SafetyAssessment with severity, action, and guidance
    """
    report_lower = report_text.lower().strip()

    # Check for urgent symptoms first
    for symptom in URGENT_SYMPTOMS:
        if symptom in report_lower:
            return SafetyAssessment(
                severity=Severity.HIGH,
                action=SafetyAction.URGENT_ACTION,
                reason=f"Patient reported urgent symptom: '{symptom}'",
                requires_human_review=True,
                recommended_message=(
                    "This sounds like it could be serious. "
                    "Please contact your doctor or go to the nearest "
                    "emergency room immediately. If you are in danger, "
                    "call emergency services."
                ),
            )

    # Check for concerning symptoms
    for symptom in CONCERNING_SYMPTOMS:
        if symptom in report_lower:
            return SafetyAssessment(
                severity=Severity.MEDIUM,
                action=SafetyAction.CONTACT_CLINICIAN,
                reason=f"Patient reported concerning symptom: '{symptom}'",
                requires_human_review=True,
                recommended_message=(
                    "This symptom should be discussed with your doctor. "
                    "Please contact your healthcare provider to discuss "
                    "what you are experiencing. Do not stop or change your "
                    "medication without medical guidance."
                ),
            )

    # Check for out-of-scope requests
    for pattern in OUT_OF_SCOPE_PATTERNS:
        if pattern in report_lower:
            return SafetyAssessment(
                severity=Severity.MEDIUM,
                action=SafetyAction.CONTACT_CLINICIAN,
                reason=f"Patient made a request outside system scope: '{pattern}'",
                requires_human_review=False,
                recommended_message=(
                    "I cannot make changes to your medication or provide "
                    "personalized medical advice. Please discuss this with "
                    "your doctor or healthcare provider."
                ),
            )

    # Default: low severity, provide information
    return SafetyAssessment(
        severity=Severity.LOW,
        action=SafetyAction.PROVIDE_INFORMATION,
        reason="No urgent or concerning patterns detected",
        requires_human_review=False,
        recommended_message=(
            "I can provide general information about your medication. "
            "If you have specific concerns, please consult your "
            "healthcare provider."
        ),
    )


def assess_adherence_risk(
    adherence_score: float,
    consecutive_missed: int,
    days_no_response: int,
) -> SafetyAssessment:
    """
    Evaluate adherence-related safety risk.

    Deterministic rules for escalation based on adherence patterns.

    Args:
        adherence_score: 0-100 adherence percentage
        consecutive_missed: Number of consecutive missed doses
        days_no_response: Days since last patient response
    """
    # No response for 3+ days — urgent
    if days_no_response >= 3:
        return SafetyAssessment(
            severity=Severity.HIGH,
            action=SafetyAction.URGENT_ACTION,
            reason=f"Patient has not responded for {days_no_response} days",
            requires_human_review=True,
            recommended_message=(
                "We have not heard from the patient in multiple days. "
                "A welfare check may be needed."
            ),
        )

    # 5+ consecutive missed doses — high concern
    if consecutive_missed >= 5:
        return SafetyAssessment(
            severity=Severity.HIGH,
            action=SafetyAction.CONTACT_CLINICIAN,
            reason=f"Patient has missed {consecutive_missed} consecutive doses",
            requires_human_review=True,
            recommended_message=(
                "Multiple consecutive doses have been missed. "
                "The healthcare team should be notified."
            ),
        )

    # Score below 50% or 3+ missed — medium concern
    if adherence_score < 50.0 or consecutive_missed >= 3:
        return SafetyAssessment(
            severity=Severity.MEDIUM,
            action=SafetyAction.CONTACT_CLINICIAN,
            reason=f"Adherence score: {adherence_score}%, missed: {consecutive_missed}",
            requires_human_review=True,
            recommended_message=(
                "Your medication adherence has been lower than expected. "
                "We recommend discussing this with your healthcare provider."
            ),
        )

    # Default: low risk
    return SafetyAssessment(
        severity=Severity.LOW,
        action=SafetyAction.PROVIDE_INFORMATION,
        reason="Adherence within acceptable range",
        requires_human_review=False,
        recommended_message="Your medication adherence is on track. Keep it up!",
    )
