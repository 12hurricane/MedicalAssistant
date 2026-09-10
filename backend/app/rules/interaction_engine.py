"""
Drug Interaction Engine

Deterministic clinical drug-drug interaction evaluation.
Evaluates pairs of canonical medications against verified clinical interaction rules with full
auditable provenance (source ID, publication version, and regulatory reference).
Does NOT use LLM hallucination for interaction checking.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.rules.drug_normalizer import CanonicalDrug


class InteractionSeverity(str, Enum):
    CONTRAINDICATED = "CONTRAINDICATED"
    MAJOR = "MAJOR"
    MODERATE = "MODERATE"
    MINOR = "MINOR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class InteractionRule:
    """Clinical drug-drug interaction rule definition with auditable provenance."""
    rule_id: str
    pair: Tuple[str, str]  # Sorted tuple of canonical_ids
    severity: InteractionSeverity
    mechanism: str
    clinical_effect: str
    recommendation: str
    source_id: str
    source_title: str
    source_version: str
    source_date: str
    regulatory_body: str = "FDA"


# Clinical interaction knowledge base with explicit regulatory provenance
_INTERACTION_RULES: List[InteractionRule] = [
    # 1. Sildenafil + Nitroglycerin (Absolute Contraindication)
    InteractionRule(
        rule_id="INT-DDI-001",
        pair=("nitroglycerin", "sildenafil"),
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism="Synergistic relaxation of vascular smooth muscle via cGMP pathway potentiation.",
        clinical_effect="Severe, life-threatening refractory hypotension and cardiovascular collapse.",
        recommendation="Co-administration is strictly contraindicated. Do not prescribe together.",
        source_id="FDA-LABEL-SIL-01",
        source_title="Viagra (sildenafil citrate) FDA Prescribing Information, Section 4 (Contraindications) & Section 7 (Drug Interactions)",
        source_version="Rev 04/2023",
        source_date="2023-04-15",
        regulatory_body="US FDA",
    ),
    # 2. Warfarin + Aspirin / NSAIDs (Major Bleeding Risk)
    InteractionRule(
        rule_id="INT-DDI-002",
        pair=("aspirin", "warfarin"),
        severity=InteractionSeverity.MAJOR,
        mechanism="Concurrent inhibition of platelet aggregation (aspirin) and vitamin K clotting factors (warfarin).",
        clinical_effect="Significantly increased risk of major gastrointestinal and intracranial hemorrhage.",
        recommendation="Avoid combination unless specifically indicated (e.g. mechanical heart valve) with close INR monitoring.",
        source_id="FDA-LABEL-WAR-01",
        source_title="Coumadin (warfarin sodium) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 08/2022",
        source_date="2022-08-01",
        regulatory_body="US FDA",
    ),
    InteractionRule(
        rule_id="INT-DDI-003",
        pair=("ibuprofen", "warfarin"),
        severity=InteractionSeverity.MAJOR,
        mechanism="NSAID-induced GI mucosal damage and platelet dysfunction combined with systemic anticoagulation.",
        clinical_effect="High risk of severe gastrointestinal bleeding and ulceration.",
        recommendation="Avoid concurrent use. Use acetaminophen/paracetamol for pain/fever if appropriate.",
        source_id="FDA-LABEL-WAR-01",
        source_title="Coumadin (warfarin sodium) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 08/2022",
        source_date="2022-08-01",
        regulatory_body="US FDA",
    ),
    InteractionRule(
        rule_id="INT-DDI-004",
        pair=("naproxen", "warfarin"),
        severity=InteractionSeverity.MAJOR,
        mechanism="NSAID-induced platelet dysfunction and gastric mucosal injury combined with anticoagulation.",
        clinical_effect="High risk of major gastrointestinal bleeding.",
        recommendation="Avoid concurrent use. Alternative analgesic recommended.",
        source_id="FDA-LABEL-WAR-01",
        source_title="Coumadin (warfarin sodium) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 08/2022",
        source_date="2022-08-01",
        regulatory_body="US FDA",
    ),
    # 3. Lisinopril + Spironolactone (Major Hyperkalemia Risk)
    InteractionRule(
        rule_id="INT-DDI-005",
        pair=("lisinopril", "spironolactone"),
        severity=InteractionSeverity.MAJOR,
        mechanism="Dual blockade of the renin-angiotensin-aldosterone system leading to potassium retention.",
        clinical_effect="Dangerous hyperkalemia leading to cardiac arrhythmias and conduction blocks.",
        recommendation="Monitor serum potassium and renal function within 1 week of initiation and periodically thereafter.",
        source_id="AHA-ACC-HF-2022",
        source_title="AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        source_version="Vol 145, Issue 18",
        source_date="2022-04-01",
        regulatory_body="AHA/ACC",
    ),
    InteractionRule(
        rule_id="INT-DDI-006",
        pair=("ramipril", "spironolactone"),
        severity=InteractionSeverity.MAJOR,
        mechanism="Dual aldosterone suppression causing additive potassium retention.",
        clinical_effect="Severe hyperkalemia risk and renal impairment.",
        recommendation="Monitor electrolytes closely. Avoid potassium supplements.",
        source_id="AHA-ACC-HF-2022",
        source_title="AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        source_version="Vol 145, Issue 18",
        source_date="2022-04-01",
        regulatory_body="AHA/ACC",
    ),
    # 4. Amoxicillin + Methotrexate (Major Toxicity Risk)
    InteractionRule(
        rule_id="INT-DDI-007",
        pair=("amoxicillin", "methotrexate"),
        severity=InteractionSeverity.MAJOR,
        mechanism="Penicillins inhibit renal tubular secretion of methotrexate via organic anion transporters.",
        clinical_effect="Elevated methotrexate serum levels and increased risk of bone marrow suppression and hepatotoxicity.",
        recommendation="Monitor for methotrexate toxicity (pancytopenia, stomatitis, elevated LFTs) or select alternative antibiotic.",
        source_id="FDA-LABEL-MTX-01",
        source_title="Trexall (methotrexate) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 10/2021",
        source_date="2021-10-10",
        regulatory_body="US FDA",
    ),
    # 5. Clopidogrel + Omeprazole (Moderate Antiplatelet Reduction)
    InteractionRule(
        rule_id="INT-DDI-008",
        pair=("clopidogrel", "omeprazole"),
        severity=InteractionSeverity.MODERATE,
        mechanism="Omeprazole inhibits CYP2C19, blocking metabolic bioactivation of clopidogrel prodrug.",
        clinical_effect="Reduced antiplatelet efficacy and increased risk of adverse cardiovascular/thrombotic events.",
        recommendation="Consider switching to a non-CYP2C19 inhibiting PPI (e.g., pantoprazole) or H2 blocker.",
        source_id="FDA-DSC-CLOP-01",
        source_title="FDA Drug Safety Communication: Reduced effectiveness of Plavix (clopidogrel) in patients also taking Prilosec (omeprazole)",
        source_version="FDA Safety Alert",
        source_date="2016-11-01",
        regulatory_body="US FDA",
    ),
    # 6. Sertraline + Tramadol (Major Serotonin Syndrome Risk)
    InteractionRule(
        rule_id="INT-DDI-009",
        pair=("sertraline", "tramadol"),
        severity=InteractionSeverity.MAJOR,
        mechanism="Additive serotonergic effects via SSRI reuptake inhibition and tramadol serotonin release.",
        clinical_effect="Serotonin syndrome (hyperreflexia, clonus, hyperthermia, autonomic instability) and lowered seizure threshold.",
        recommendation="Avoid combination where possible. Educate patient on early serotonin syndrome symptoms.",
        source_id="FDA-LABEL-ZOL-01",
        source_title="Zoloft (sertraline hydrochloride) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 12/2021",
        source_date="2021-12-05",
        regulatory_body="US FDA",
    ),
    # 7. Propranolol + Pseudoephedrine (Moderate Hypertension Risk)
    InteractionRule(
        rule_id="INT-DDI-010",
        pair=("propranolol", "pseudoephedrine"),
        severity=InteractionSeverity.MODERATE,
        mechanism="Unopposed alpha-adrenergic vasoconstriction due to non-selective beta blockade.",
        clinical_effect="Marked hypertension and reflex bradycardia.",
        recommendation="Avoid oral pseudoephedrine; consider saline nasal sprays or topical decongestants for brief durations.",
        source_id="FDA-LABEL-IND-01",
        source_title="Inderal (propranolol hydrochloride) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 03/2020",
        source_date="2020-03-12",
        regulatory_body="US FDA",
    ),
    # 8. Ibuprofen + Lisinopril (Moderate Renal & BP Effect)
    InteractionRule(
        rule_id="INT-DDI-011",
        pair=("ibuprofen", "lisinopril"),
        severity=InteractionSeverity.MODERATE,
        mechanism="NSAIDs inhibit renal vasodilatory prostaglandins, opposing ACE inhibitor antihypertensive action.",
        clinical_effect="Decreased blood pressure control and increased risk of acute kidney injury.",
        recommendation="Limit NSAID duration; monitor blood pressure and renal function.",
        source_id="FDA-LABEL-ZEST-01",
        source_title="Zestril (lisinopril) FDA Prescribing Information, Section 7 (Drug Interactions)",
        source_version="Rev 09/2022",
        source_date="2022-09-18",
        regulatory_body="US FDA",
    ),
]

# Map for O(1) pairwise lookup: (sorted_drug_a, sorted_drug_b) -> InteractionRule
INTERACTION_MAP: Dict[Tuple[str, str], InteractionRule] = {
    tuple(sorted(r.pair)): r for r in _INTERACTION_RULES
}


@dataclass
class MedicationInteractionAlert:
    """Structured alert output for a detected drug interaction with provenance."""
    rule_id: str
    drug_a: str
    drug_b: str
    severity: InteractionSeverity
    mechanism: str
    clinical_effect: str
    recommendation: str
    source: str
    source_id: str
    source_title: str
    source_version: str
    source_date: str


def check_drug_interactions(drugs: List[CanonicalDrug]) -> List[MedicationInteractionAlert]:
    """
    Check all pairwise combinations of medications for clinical drug-drug interactions.
    """
    alerts: List[MedicationInteractionAlert] = []
    seen_pairs = set()

    for i in range(len(drugs)):
        for j in range(i + 1, len(drugs)):
            drug1 = drugs[i]
            drug2 = drugs[j]

            if drug1.canonical_id == drug2.canonical_id:
                continue

            pair_key = tuple(sorted([drug1.canonical_id, drug2.canonical_id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            if pair_key in INTERACTION_MAP:
                rule = INTERACTION_MAP[pair_key]
                alerts.append(
                    MedicationInteractionAlert(
                        rule_id=rule.rule_id,
                        drug_a=drug1.generic_name.title(),
                        drug_b=drug2.generic_name.title(),
                        severity=rule.severity,
                        mechanism=rule.mechanism,
                        clinical_effect=rule.clinical_effect,
                        recommendation=rule.recommendation,
                        source=rule.source_title,
                        source_id=rule.source_id,
                        source_title=rule.source_title,
                        source_version=rule.source_version,
                        source_date=rule.source_date,
                    )
                )

    return alerts

