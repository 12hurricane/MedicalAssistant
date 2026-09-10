"""
Drug Identity Normalization Module

Deterministic canonical normalization of brand names, synonyms, and free-text medication strings
into structured canonical drug representations with therapeutic classifications.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CanonicalDrug:
    """Canonical representation of a medication."""
    canonical_id: str          # e.g. 'warfarin', 'metformin', 'amoxicillin'
    generic_name: str          # Standard international non-proprietary name (INN)
    drug_class: str            # Pharmacological / therapeutic class
    brand_names: List[str] = field(default_factory=list)
    dosage_form: str = "tablet"
    route: str = "oral"
    is_critical: bool = False  # Vital or narrow therapeutic index medication


# Structured clinical drug catalog
CANONICAL_DRUG_CATALOG: Dict[str, CanonicalDrug] = {
    "warfarin": CanonicalDrug(
        canonical_id="warfarin",
        generic_name="warfarin",
        drug_class="anticoagulant",
        brand_names=["coumadin", "jantoven", "marevan"],
        is_critical=True,
    ),
    "aspirin": CanonicalDrug(
        canonical_id="aspirin",
        generic_name="aspirin",
        drug_class="antiplatelet_nsaid",
        brand_names=["bayer", "ecotrin", "disprin", "asaphen"],
        is_critical=True,
    ),
    "clopidogrel": CanonicalDrug(
        canonical_id="clopidogrel",
        generic_name="clopidogrel",
        drug_class="antiplatelet",
        brand_names=["plavix", "clopilet", "ceruvin"],
        is_critical=True,
    ),
    "metformin": CanonicalDrug(
        canonical_id="metformin",
        generic_name="metformin",
        drug_class="biguanide",
        brand_names=["glucophage", "glycomet", "fortamet", "glumetza"],
        is_critical=True,
    ),
    "amoxicillin": CanonicalDrug(
        canonical_id="amoxicillin",
        generic_name="amoxicillin",
        drug_class="penicillin_antibiotic",
        brand_names=["amoxil", "moxatag", "novamoxin"],
        is_critical=False,
    ),
    "amoxicillin_clavulanate": CanonicalDrug(
        canonical_id="amoxicillin_clavulanate",
        generic_name="amoxicillin and clavulanate potassium",
        drug_class="penicillin_antibiotic",
        brand_names=["augmentin", "clavulin", "moxikind-cv"],
        is_critical=False,
    ),
    "ibuprofen": CanonicalDrug(
        canonical_id="ibuprofen",
        generic_name="ibuprofen",
        drug_class="nsaid",
        brand_names=["advil", "motrin", "brufen", "nurofen"],
        is_critical=False,
    ),
    "naproxen": CanonicalDrug(
        canonical_id="naproxen",
        generic_name="naproxen",
        drug_class="nsaid",
        brand_names=["aleve", "naprosyn", "anaprox"],
        is_critical=False,
    ),
    "paracetamol": CanonicalDrug(
        canonical_id="paracetamol",
        generic_name="paracetamol",
        drug_class="analgesic_antipyretic",
        brand_names=["tylenol", "panadol", "calpol", "crocin", "dolo", "acetaminophen"],
        is_critical=False,
    ),
    "lisinopril": CanonicalDrug(
        canonical_id="lisinopril",
        generic_name="lisinopril",
        drug_class="ace_inhibitor",
        brand_names=["zestril", "prinivil", "lipril"],
        is_critical=True,
    ),
    "ramipril": CanonicalDrug(
        canonical_id="ramipril",
        generic_name="ramipril",
        drug_class="ace_inhibitor",
        brand_names=["altace", "cardace", "tritace"],
        is_critical=True,
    ),
    "spironolactone": CanonicalDrug(
        canonical_id="spironolactone",
        generic_name="spironolactone",
        drug_class="potassium_sparing_diuretic",
        brand_names=["aldactone", "carospir"],
        is_critical=True,
    ),
    "propranolol": CanonicalDrug(
        canonical_id="propranolol",
        generic_name="propranolol",
        drug_class="non_selective_beta_blocker",
        brand_names=["inderal", "inno-pran", "ciplar"],
        is_critical=True,
    ),
    "atenolol": CanonicalDrug(
        canonical_id="atenolol",
        generic_name="atenolol",
        drug_class="cardioselective_beta_blocker",
        brand_names=["tenormin", "aten"],
        is_critical=True,
    ),
    "sildenafil": CanonicalDrug(
        canonical_id="sildenafil",
        generic_name="sildenafil",
        drug_class="pde5_inhibitor",
        brand_names=["viagra", "revatio", "manforce", "caverta"],
        is_critical=False,
    ),
    "nitroglycerin": CanonicalDrug(
        canonical_id="nitroglycerin",
        generic_name="nitroglycerin",
        drug_class="nitrate",
        brand_names=["nitrostat", "nitro-dur", "angispan", "nitrolingual"],
        is_critical=True,
    ),
    "methotrexate": CanonicalDrug(
        canonical_id="methotrexate",
        generic_name="methotrexate",
        drug_class="antimetabolite_immunosuppressive",
        brand_names=["trexall", "otrexup", "rasuvo", "folitrax"],
        is_critical=True,
    ),
    "omeprazole": CanonicalDrug(
        canonical_id="omeprazole",
        generic_name="omeprazole",
        drug_class="ppi",
        brand_names=["prilosec", "omez", "losec"],
        is_critical=False,
    ),
    "sertraline": CanonicalDrug(
        canonical_id="sertraline",
        generic_name="sertraline",
        drug_class="ssri",
        brand_names=["zoloft", "serlift", "daxid"],
        is_critical=True,
    ),
    "tramadol": CanonicalDrug(
        canonical_id="tramadol",
        generic_name="tramadol",
        drug_class="opioid_analgesic",
        brand_names=["ultram", "tramal", "ultracet"],
        is_critical=True,
    ),
    "pseudoephedrine": CanonicalDrug(
        canonical_id="pseudoephedrine",
        generic_name="pseudoephedrine",
        drug_class="sympathomimetic_decongestant",
        brand_names=["sudafed", "actifed", "sinutab"],
        is_critical=False,
    ),
}

# Build fast reverse lookup index: normalized_alias -> canonical_id
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for cid, drug in CANONICAL_DRUG_CATALOG.items():
    ALIAS_TO_CANONICAL[cid] = cid
    ALIAS_TO_CANONICAL[drug.generic_name.lower()] = cid
    for brand in drug.brand_names:
        ALIAS_TO_CANONICAL[brand.lower()] = cid


def _clean_string(text: str) -> str:
    """Strip dosage numbers, formulations, and punctuation."""
    t = text.lower().strip()
    # Replace common dosage patterns: 500mg, 10 mg, 5ml, 1 tab, etc.
    t = re.sub(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|tab|tablet|cap|capsule|pill|puff|drops?)\b", "", t)
    # Remove punctuation
    t = re.sub(r"[^\w\s-]", " ", t)
    # Collapse extra whitespace
    return " ".join(t.split())


def normalize_drug(name_or_text: str) -> CanonicalDrug:
    """
    Normalize a free-text medication name or brand string to a CanonicalDrug.
    
    If the drug is not in the recognized catalog, returns a fallback CanonicalDrug
    with canonical_id derived from the cleaned name.
    """
    if not name_or_text:
        return CanonicalDrug(
            canonical_id="unknown",
            generic_name="unknown",
            drug_class="unknown",
        )

    cleaned = _clean_string(name_or_text)

    # 1. Exact alias match
    if cleaned in ALIAS_TO_CANONICAL:
        return CANONICAL_DRUG_CATALOG[ALIAS_TO_CANONICAL[cleaned]]

    # 2. Token / substring matching against known catalog
    for alias, cid in ALIAS_TO_CANONICAL.items():
        # Match as whole word substring
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, cleaned):
            return CANONICAL_DRUG_CATALOG[cid]

    # 3. Fallback generic representation for unknown or unlisted drugs
    sanitized_id = re.sub(r"\s+", "_", cleaned)
    return CanonicalDrug(
        canonical_id=sanitized_id,
        generic_name=cleaned,
        drug_class="unclassified",
    )
