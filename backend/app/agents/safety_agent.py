"""Safety Verification Agent for prescription ingestion.

Performs deterministic clinical safety verification on newly parsed prescription
medications before database ingestion:
- Drug normalization (catalogue mapping)
- Known drug allergy contraindications
- Chronic medical condition contraindications
- Drug-drug interactions (within new Rx and against active patient meds)
- Duplicate therapy detection
- Polypharmacy risk flag (> 5 active medications)
"""

import logging
from typing import Any, Dict, List, Optional

from app.rules.contraindication_engine import (
    ContraindicationAlert,
    ContraindicationSeverity,
    DuplicateTherapyAlert,
    check_allergy_contraindications,
    check_condition_contraindications,
    check_duplicate_therapies,
)
from app.rules.drug_normalizer import CanonicalDrug, normalize_drug
from app.rules.interaction_engine import (
    InteractionSeverity,
    MedicationInteractionAlert,
    check_drug_interactions,
)

logger = logging.getLogger(__name__)


def verify_prescription_safety(
    new_medications: List[Dict[str, Any]],
    patient_allergies: Optional[List[str]] = None,
    patient_conditions: Optional[List[str]] = None,
    existing_medications: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Verify safety of proposed prescription medications.

    Args:
        new_medications: List of medication dicts containing 'medicine_name'.
        patient_allergies: List of known patient allergy strings.
        patient_conditions: List of known patient chronic condition strings.
        existing_medications: List of active medication names currently prescribed.

    Returns:
        Dict with 'is_safe', 'risk_level', and 'safety_findings'.
    """
    allergies = patient_allergies or []
    conditions = patient_conditions or []
    existing = existing_medications or []

    findings: List[str] = []
    has_critical = False
    has_moderate = False

    # 1. Normalize new drugs
    normalized_new: List[CanonicalDrug] = []
    for med in new_medications:
        name = med.get("medicine_name", "")
        if name:
            canonical = normalize_drug(name)
            normalized_new.append(canonical)

    # 2. Normalize existing drugs
    normalized_existing: List[CanonicalDrug] = []
    for name in existing:
        if name:
            normalized_existing.append(normalize_drug(name))

    all_normalized = normalized_new + normalized_existing

    # 3. Check Allergy Contraindications
    allergy_alerts = check_allergy_contraindications(
        drugs=normalized_new,
        allergies=allergies,
    )
    for alert in allergy_alerts:
        msg = (
            f"CONTRAINDICATION (ALLERGY): "
            f"{alert.medication} triggered by '{alert.trigger}'. {alert.clinical_risk}"
        )
        findings.append(msg)
        if alert.severity == ContraindicationSeverity.CONTRAINDICATED:
            has_critical = True
        else:
            has_moderate = True

    # 4. Check Condition Contraindications
    condition_alerts = check_condition_contraindications(
        drugs=normalized_new,
        conditions=conditions,
    )
    for alert in condition_alerts:
        msg = (
            f"CONTRAINDICATION (CHRONIC_CONDITION): "
            f"{alert.medication} triggered by '{alert.trigger}'. {alert.clinical_risk}"
        )
        findings.append(msg)
        if alert.severity == ContraindicationSeverity.CONTRAINDICATED:
            has_critical = True
        else:
            has_moderate = True

    # 5. Check Drug-Drug Interactions
    interaction_alerts = check_drug_interactions(drugs=all_normalized)
    for alert in interaction_alerts:
        msg = (
            f"DRUG INTERACTION ({alert.severity.value}): "
            f"{alert.drug_a} + {alert.drug_b} - {alert.clinical_effect} ({alert.recommendation})"
        )
        findings.append(msg)
        if alert.severity == InteractionSeverity.CONTRAINDICATED:
            has_critical = True
        elif alert.severity in (InteractionSeverity.MAJOR, InteractionSeverity.MODERATE):
            has_moderate = True

    # 6. Duplicate Therapies
    duplicate_alerts = check_duplicate_therapies(drugs=all_normalized)
    for alert in duplicate_alerts:
        msg = (
            f"DUPLICATE THERAPY ({alert.drug_class}): "
            f"Concurrent medications {alert.medications} share the same therapeutic class."
        )
        findings.append(msg)
        has_moderate = True

    # 7. Polypharmacy Check
    if len(all_normalized) > 5:
        findings.append(
            f"POLYPHARMACY WARNING: Patient has {len(all_normalized)} concurrent medications. "
            "Increased risk of adverse drug reactions."
        )
        has_moderate = True

    if has_critical:
        risk_level = "CRITICAL"
        is_safe = False
    elif has_moderate:
        risk_level = "MODERATE"
        is_safe = True
    else:
        risk_level = "LOW"
        is_safe = True

    return {
        "is_safe": is_safe,
        "risk_level": risk_level,
        "safety_findings": findings,
    }
