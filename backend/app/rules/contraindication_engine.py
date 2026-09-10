"""
Contraindication & Duplicate Therapy Engine

Evaluates medication safety against patient-specific clinical profiles:
- Known drug allergies
- Chronic medical conditions & comorbidities
- Duplicate / redundant pharmacological therapies
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Set, Tuple

from app.rules.drug_normalizer import CanonicalDrug


class ContraindicationSeverity(str, Enum):
    CONTRAINDICATED = "CONTRAINDICATED"
    MAJOR = "MAJOR"
    MODERATE = "MODERATE"


@dataclass
class ContraindicationAlert:
    """Alert for allergy or medical condition contraindication."""
    medication: str
    contraindication_type: str  # "ALLERGY" or "CHRONIC_CONDITION"
    trigger: str               # The matching allergy or condition
    severity: ContraindicationSeverity
    clinical_risk: str
    recommendation: str


@dataclass
class DuplicateTherapyAlert:
    """Alert for duplicate pharmacological therapy."""
    medications: List[str]
    drug_class: str
    severity: ContraindicationSeverity
    clinical_risk: str
    recommendation: str


# Allergy matching rules: normalized allergy string -> affected canonical_ids / drug_classes
ALLERGY_CROSS_REACTIVITY: Dict[str, Dict[str, str]] = {
    "penicillin": {
        "drug_classes": ["penicillin_antibiotic"],
        "canonical_ids": ["amoxicillin", "amoxicillin_clavulanate", "ampicillin"],
        "risk": "Risk of severe Type I IgE-mediated hypersensitivity reaction (anaphylaxis, angioedema, urticaria).",
        "recommendation": "Avoid all penicillin-class antibiotics. Use non-beta-lactam alternative (e.g. Macrolide, Fluoroquinolone).",
        "severity": ContraindicationSeverity.CONTRAINDICATED,
    },
    "sulfa": {
        "drug_classes": ["sulfonamide_antibiotic", "sulfonamide"],
        "canonical_ids": ["sulfamethoxazole", "trimethoprim_sulfamethoxazole", "sulfasalazine"],
        "risk": "Risk of severe cutaneous adverse reactions (Stevens-Johnson syndrome / TEN) or anaphylaxis.",
        "recommendation": "Do not administer sulfonamide-containing medications.",
        "severity": ContraindicationSeverity.CONTRAINDICATED,
    },
    "aspirin": {
        "drug_classes": ["antiplatelet_nsaid", "nsaid"],
        "canonical_ids": ["aspirin", "ibuprofen", "naproxen"],
        "risk": "Aspirin-exacerbated respiratory disease (AERD) / severe bronchospasm or angioedema.",
        "recommendation": "Avoid aspirin and all non-steroidal anti-inflammatory drugs.",
        "severity": ContraindicationSeverity.CONTRAINDICATED,
    },
    "nsaid": {
        "drug_classes": ["nsaid", "antiplatelet_nsaid"],
        "canonical_ids": ["ibuprofen", "naproxen", "aspirin"],
        "risk": "Severe hypersensitivity, bronchospasm, or cutaneous reactions.",
        "recommendation": "Avoid NSAIDs. Consider acetaminophen/paracetamol.",
        "severity": ContraindicationSeverity.CONTRAINDICATED,
    },
}

# Condition contraindication rules: normalized condition name -> affected drug classes / IDs
CONDITION_CONTRAINDICATIONS: Dict[str, List[Dict]] = {
    "asthma": [
        {
            "match_classes": ["non_selective_beta_blocker"],
            "match_ids": ["propranolol", "timolol", "nadolol", "carvedilol"],
            "severity": ContraindicationSeverity.CONTRAINDICATED,
            "risk": "Beta-2 receptor blockade causes potent bronchoconstriction and life-threatening asthma exacerbation.",
            "recommendation": "Contraindicated in active asthma. Use cardioselective beta-blocker with extreme caution or alternative class.",
        },
        {
            "match_classes": ["nsaid"],
            "match_ids": ["ibuprofen", "naproxen", "aspirin"],
            "severity": ContraindicationSeverity.MODERATE,
            "risk": "Potential to trigger acute bronchospasm in patients with aspirin-sensitive asthma triad.",
            "recommendation": "Use with caution; discontinue immediately if respiratory symptoms worsen.",
        },
    ],
    "chronic_kidney_disease": [
        {
            "match_classes": ["nsaid"],
            "match_ids": ["ibuprofen", "naproxen"],
            "severity": ContraindicationSeverity.MAJOR,
            "risk": "Inhibition of renal prostaglandins reduces renal blood flow and accelerates acute-on-chronic renal failure.",
            "recommendation": "Avoid systemic NSAIDs in moderate-to-severe CKD. Use paracetamol or topical alternatives.",
        },
        {
            "match_classes": ["biguanide"],
            "match_ids": ["metformin"],
            "severity": ContraindicationSeverity.MODERATE,
            "risk": "Metformin accumulation in severe renal impairment (eGFR < 30 mL/min) increases risk of lactic acidosis.",
            "recommendation": "Verify eGFR. Dose reduction required if eGFR 30-45; discontinue if eGFR < 30.",
        },
    ],
    "peptic_ulcer": [
        {
            "match_classes": ["nsaid", "antiplatelet_nsaid"],
            "match_ids": ["ibuprofen", "naproxen", "aspirin"],
            "severity": ContraindicationSeverity.MAJOR,
            "risk": "COX-1 inhibition compromises gastroprotective prostaglandins, causing mucosal ulceration and active bleeding.",
            "recommendation": "Avoid NSAIDs. If essential, co-prescribe a proton pump inhibitor (PPI) gastroprotectant.",
        },
        {
            "match_classes": ["anticoagulant"],
            "match_ids": ["warfarin"],
            "severity": ContraindicationSeverity.MAJOR,
            "risk": "Severe exacerbation of gastrointestinal hemorrhage in presence of mucosal lesions.",
            "recommendation": "Endoscopic evaluation and mucosal healing required prior to anticoagulation.",
        },
    ],
    "hypertension": [
        {
            "match_classes": ["sympathomimetic_decongestant"],
            "match_ids": ["pseudoephedrine", "phenylephrine"],
            "severity": ContraindicationSeverity.MODERATE,
            "risk": "Alpha-1 adrenergic vasoconstriction causes elevation in systemic blood pressure.",
            "recommendation": "Avoid oral decongestants in uncontrolled hypertension; use intranasal saline or topical sprays briefly.",
        }
    ],
    "liver_disease": [
        {
            "match_classes": ["antimetabolite_immunosuppressive"],
            "match_ids": ["methotrexate"],
            "severity": ContraindicationSeverity.MAJOR,
            "risk": "Significant risk of accelerated hepatic fibrosis and cirrhosis in pre-existing liver disease.",
            "recommendation": "Contraindicated in severe hepatic impairment. Baseline and periodic LFT monitoring required.",
        }
    ],
}


def _normalize_tag(tag: str) -> str:
    return tag.lower().strip().replace(" ", "_").replace("-", "_")


def check_allergy_contraindications(
    drugs: List[CanonicalDrug],
    allergies: List[str],
) -> List[ContraindicationAlert]:
    """Check if any prescribed medication conflicts with known patient drug allergies."""
    alerts: List[ContraindicationAlert] = []
    if not allergies:
        return alerts

    normalized_allergies = [_normalize_tag(a) for a in allergies if a]

    for drug in drugs:
        for patient_allergy in normalized_allergies:
            # Check against allergy definitions
            for allergy_key, rule in ALLERGY_CROSS_REACTIVITY.items():
                if allergy_key in patient_allergy or patient_allergy in allergy_key:
                    # Check drug class or canonical ID match
                    class_match = drug.drug_class in rule.get("drug_classes", [])
                    id_match = drug.canonical_id in rule.get("canonical_ids", [])

                    if class_match or id_match:
                        alerts.append(
                            ContraindicationAlert(
                                medication=drug.generic_name.title(),
                                contraindication_type="ALLERGY",
                                trigger=patient_allergy.replace("_", " ").title(),
                                severity=rule["severity"],
                                clinical_risk=rule["risk"],
                                recommendation=rule["recommendation"],
                            )
                        )
    return alerts


def check_condition_contraindications(
    drugs: List[CanonicalDrug],
    conditions: List[str],
) -> List[ContraindicationAlert]:
    """Check if any prescribed medication conflicts with patient chronic conditions."""
    alerts: List[ContraindicationAlert] = []
    if not conditions:
        return alerts

    normalized_conditions = [_normalize_tag(c) for c in conditions if c]

    for drug in drugs:
        for patient_cond in normalized_conditions:
            for cond_key, rules in CONDITION_CONTRAINDICATIONS.items():
                if cond_key in patient_cond or patient_cond in cond_key:
                    for rule in rules:
                        class_match = drug.drug_class in rule.get("match_classes", [])
                        id_match = drug.canonical_id in rule.get("match_ids", [])

                        if class_match or id_match:
                            alerts.append(
                                ContraindicationAlert(
                                    medication=drug.generic_name.title(),
                                    contraindication_type="CHRONIC_CONDITION",
                                    trigger=patient_cond.replace("_", " ").title(),
                                    severity=rule["severity"],
                                    clinical_risk=rule["risk"],
                                    recommendation=rule["recommendation"],
                                )
                            )
    return alerts


def check_duplicate_therapies(drugs: List[CanonicalDrug]) -> List[DuplicateTherapyAlert]:
    """
    Check for duplicate / redundant medications in the same drug class or identical active ingredient.
    """
    alerts: List[DuplicateTherapyAlert] = []
    
    # Group by drug class
    class_groups: Dict[str, List[CanonicalDrug]] = {}
    for d in drugs:
        if d.drug_class and d.drug_class not in ("unclassified", "unknown"):
            class_groups.setdefault(d.drug_class, []).append(d)

    # Classes where duplicate therapy is clinically hazardous
    HIGH_RISK_DUPLICATE_CLASSES = {
        "nsaid": "Concurrent use of multiple NSAIDs increases GI bleeding, ulceration, and renal toxicity with no added therapeutic benefit.",
        "ace_inhibitor": "Dual renin-angiotensin-system inhibition causes increased hypotension, hyperkalemia, and acute kidney injury.",
        "anticoagulant": "Multiple anticoagulants without bridging protocol markedly multiplies life-threatening bleeding risk.",
        "non_selective_beta_blocker": "Excessive beta-adrenergic blockade causes profound bradycardia and heart failure decompensation.",
        "ssri": "Duplicate serotonergic agents trigger severe serotonin syndrome risk.",
    }

    for dclass, group in class_groups.items():
        if len(group) > 1:
            med_names = [d.generic_name.title() for d in group]
            risk_desc = HIGH_RISK_DUPLICATE_CLASSES.get(
                dclass,
                f"Multiple medications prescribed from the same therapeutic class ({dclass.replace('_', ' ').title()})."
            )
            severity = ContraindicationSeverity.MAJOR if dclass in HIGH_RISK_DUPLICATE_CLASSES else ContraindicationSeverity.MODERATE
            alerts.append(
                DuplicateTherapyAlert(
                    medications=med_names,
                    drug_class=dclass.replace("_", " ").title(),
                    severity=severity,
                    clinical_risk=risk_desc,
                    recommendation="Review regimen to eliminate duplicate therapy or adjust to single optimal agent.",
                )
            )

    return alerts
