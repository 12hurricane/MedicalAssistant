"""
Clinical Evidence Corpus

Authoritative, curated repository of official drug labeling (FDA package inserts),
established clinical practice guidelines (AHA/ACC, KDIGO, EAACI), and regulatory drug safety communications.
Every document has strict versioning, source tracking, and structured sectioning.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Document:
    """Master document in the clinical evidence repository."""
    document_id: str
    title: str
    source: str
    source_type: str  # "FDA_LABEL", "CLINICAL_GUIDELINE", "DRUG_SAFETY_COMMUNICATION"
    publication_date: str
    version: str
    content: str


@dataclass(frozen=True)
class Chunk:
    """Indexed chunk of a clinical document with fine-grained metadata."""
    chunk_id: str
    document_id: str
    drug_name: str
    drug_class: str
    topic: str  # "interactions", "contraindications", "warnings", "adherence_guidelines"
    source: str
    section: str
    text: str
    version: str
    publication_date: str

    #: Canonical ids of every *other* drug this chunk is explicitly about.
    #:
    #: Necessary because ``drug_name`` names the document's subject, not the chunk's
    #: subject matter, and an interaction chunk is by definition about two drugs.
    #: ``CHK-WAR-001`` is filed under warfarin but its text is precisely the
    #: ibuprofen/naproxen/aspirin bleeding interaction — so an ibuprofen query that
    #: consulted ``drug_name`` alone would find nothing, and the corpus does in fact
    #: hold the answer.
    #:
    #: Declared here rather than extracted from ``text`` at index time. A regex over
    #: the prose would also match a drug named only to be ruled out — the warfarin
    #: label recommends acetaminophen *instead of* NSAIDs, and "evidence about
    #: paracetamol" is not what that sentence is. Association is a clinical judgement,
    #: so it is written down and reviewable, and ``test_rag_retrieval_safety.py``
    #: asserts every id here resolves against ``CANONICAL_DRUG_CATALOG``.
    related_drugs: Tuple[str, ...] = ()


# Authoritative Medical Document Store
CLINICAL_DOCUMENTS: List[Document] = [
    Document(
        document_id="DOC-FDA-SIL-01",
        title="Viagra (sildenafil citrate) FDA Prescribing Information",
        source="US Food and Drug Administration / DailyMed",
        source_type="FDA_LABEL",
        publication_date="2023-04-15",
        version="Rev 04/2023",
        content="""
Section 4: Contraindications
Administration of VIAGRA to patients who are using organic nitrates, such as nitroglycerin, isosorbide dinitrate, or isosorbide mononitrate, in any form either regularly and/or intermittently is contraindicated. Consistent with its known effects on the nitric oxide/cGMP pathway, VIAGRA was shown to potentiate the hypotensive effects of nitrates.

Section 7: Drug Interactions
Nitrates: Concomitant use of VIAGRA and organic nitrates or nitric oxide donors in any form is contraindicated. A potentiation of the hypotensive response by sildenafil has been observed in patients with coronary artery disease. Fatal episodes of profound refractory hypotension, myocardial infarction, and cardiovascular collapse have been documented.
""",
    ),
    Document(
        document_id="DOC-FDA-WAR-01",
        title="Coumadin (warfarin sodium) FDA Prescribing Information",
        source="US Food and Drug Administration / DailyMed",
        source_type="FDA_LABEL",
        publication_date="2022-08-01",
        version="Rev 08/2022",
        content="""
Section 4: Warnings and Precautions - Hemorrhage
Warfarin sodium can cause major or fatal bleeding. Bleeding is more likely to occur during the starting period and with a higher dose (resulting in a higher INR). Risk factors for bleeding include high intensity of anticoagulation, age 65 or older, history of highly variable INRs, history of gastrointestinal bleeding, and concomitant use of antiplatelet drugs.

Section 7: Drug Interactions - NSAIDs and Aspirin
Concomitant use of nonsteroidal anti-inflammatory drugs (NSAIDs) such as ibuprofen, naproxen, or aspirin with warfarin significantly increases the risk of severe gastrointestinal bleeding and ulceration. NSAIDs inhibit platelet aggregation and cause gastric mucosal erosions, while warfarin impairs clotting factor synthesis. Acetaminophen is preferred for analgesia with INR monitoring.
""",
    ),
    Document(
        document_id="DOC-FDA-IND-01",
        title="Inderal (propranolol hydrochloride) FDA Prescribing Information",
        source="US Food and Drug Administration / DailyMed",
        source_type="FDA_LABEL",
        publication_date="2020-03-12",
        version="Rev 03/2020",
        content="""
Section 4: Contraindications - Bronchial Asthma
Propranolol is contraindicated in patients with bronchial asthma, chronic obstructive pulmonary disease (COPD) with a bronchospastic component, sinus bradycardia, second- or third-degree atrioventricular block, and cardiogenic shock.

Section 5: Warnings - Bronchospasm
Non-selective beta-adrenergic receptor blockade by propranolol inhibits beta-2 receptor mediated bronchodilation. In patients with asthma or reactive airway disease, administration of propranolol can precipitate acute, severe, potentially life-threatening bronchospasm and refractory status asthmaticus.
""",
    ),
    Document(
        document_id="DOC-FDA-AMX-01",
        title="Amoxil (amoxicillin) FDA Prescribing Information",
        source="US Food and Drug Administration / DailyMed",
        source_type="FDA_LABEL",
        publication_date="2021-06-15",
        version="Rev 06/2021",
        content="""
Section 4: Contraindications - Hypersensitivity
Amoxicillin is contraindicated in patients who have experienced a serious hypersensitivity reaction (e.g., anaphylaxis or Stevens-Johnson syndrome) to amoxicillin or to other beta-lactam antibacterial drugs (e.g., penicillins and cephalosporins).

Section 5: Warnings - Anaphylaxis
Serious and occasionally fatal hypersensitivity (anaphylactic) reactions have been reported in patients on penicillin therapy. Although anaphylaxis is more frequent following parenteral therapy, it has occurred in patients on oral penicillins. Prior to initiating therapy, careful inquiry should be made concerning previous hypersensitivity reactions to penicillins.
""",
    ),
    Document(
        document_id="DOC-GL-AHA-HF01",
        title="AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        source="American Heart Association / American College of Cardiology",
        source_type="CLINICAL_GUIDELINE",
        publication_date="2022-04-01",
        version="Vol 145, Issue 18",
        content="""
Section 7.3: RAAS Blockade and Aldosterone Antagonist Combination
The combination of an ACE inhibitor (e.g., lisinopril, ramipril) and a mineralocorticoid receptor antagonist (spironolactone or eplerenone) provides significant morbidity and mortality benefits in heart failure with reduced ejection fraction. However, this dual therapy confers a substantial risk of severe, life-threatening hyperkalemia (potassium > 5.5 mEq/L) and renal failure.

Clinical Recommendation:
Serum potassium and renal function (eGFR/creatinine) must be evaluated prior to initiation, at 1 week, at 4 weeks, and every 3 to 6 months thereafter. Potassium supplementation should be discontinued upon starting spironolactone unless hypokalemia is documented.
""",
    ),
    Document(
        document_id="DOC-FDA-MET-01",
        title="Glucophage (metformin hydrochloride) FDA Prescribing Information",
        source="US Food and Drug Administration / DailyMed",
        source_type="FDA_LABEL",
        publication_date="2021-09-20",
        version="Rev 09/2021",
        content="""
Boxed Warning: Lactic Acidosis
Postmarketing cases of metformin-associated lactic acidosis have resulted in death, hypothermia, hypotension, and resistant bradyarrhythmias. Lactic acidosis is a medical emergency with high mortality. The risk is heightened in patients with renal impairment (eGFR < 45 mL/min/1.73m2).

Section 4: Contraindications - Renal Disease
Metformin is contraindicated in patients with severe renal impairment (eGFR < 30 mL/min/1.73m2). Initiation is not recommended in patients with eGFR between 30 and 45 mL/min/1.73m2. Obtain eGFR at least annually in all patients taking metformin.
""",
    ),
    Document(
        document_id="DOC-FDA-CLOP-01",
        title="Plavix (clopidogrel) Drug Safety Communication",
        source="US Food and Drug Administration Safety Alert",
        source_type="DRUG_SAFETY_COMMUNICATION",
        publication_date="2016-11-01",
        version="FDA Safety Communication",
        content="""
Section: CYP2C19 Inhibition and Omeprazole Interaction
Clopidogrel is a prodrug requiring biotransformation to its active metabolite by CYP2C19. Proton pump inhibitors (PPIs), particularly omeprazole and esomeprazole, significantly inhibit CYP2C19 activity. Concomitant use decreases the antiplatelet effect of clopidogrel by approximately 45%, increasing the incidence of adverse cardiovascular events including stent thrombosis and myocardial infarction.

Recommendation:
Avoid concomitant use of omeprazole or esomeprazole with clopidogrel. Consider alternatives such as pantoprazole (a weaker CYP2C19 inhibitor) or H2-receptor antagonists (ranitidine, famotidine).
""",
    ),
    Document(
        document_id="DOC-FDA-ZOL-01",
        title="Zoloft (sertraline hydrochloride) FDA Prescribing Information",
        source="US Food and Drug Administration / DailyMed",
        source_type="FDA_LABEL",
        publication_date="2021-12-05",
        version="Rev 12/2021",
        content="""
Section 7: Drug Interactions - Serotonergic Drugs
The co-administration of ZOLOFT with other drugs that enhance serotonergic neurotransmission (e.g., tramadol, triptans, fentanyl, lithium, linezolid) increases the risk of Serotonin Syndrome. Symptoms include mental status changes (agitation, hallucinations, coma), autonomic instability (tachycardia, labile blood pressure, hyperthermia), and neuromuscular aberrations (hyperreflexia, incoordination).

Recommendation:
If concomitant use of sertraline and tramadol is clinically warranted, careful observation of the patient is advised, particularly during treatment initiation and dose increases.
""",
    ),
]


def build_corpus_chunks() -> List[Chunk]:
    """Generate structured, metadata-rich chunks from the authoritative document repository."""
    chunks: List[Chunk] = []

    # 1. Sildenafil - Nitrates Contraindication & Interaction
    chunks.append(
        Chunk(
            chunk_id="CHK-SIL-001",
            document_id="DOC-FDA-SIL-01",
            drug_name="sildenafil",
            drug_class="pde5_inhibitor",
            topic="contraindications",
            source="US Food and Drug Administration / DailyMed",
            section="Section 4: Contraindications",
            text="Administration of VIAGRA (sildenafil) to patients who are using organic nitrates (nitroglycerin, isosorbide dinitrate, or isosorbide mononitrate) in any form is contraindicated. Sildenafil potentiates the hypotensive effects of nitrates via the cGMP pathway.",
            # Isosorbide dinitrate/mononitrate are named in the text but absent from the
            # catalog, so they cannot be declared here. A nitrate the catalog does not know
            # is a gap in CANONICAL_DRUG_CATALOG, not something to paper over in the corpus.
            related_drugs=("nitroglycerin",),
            version="Rev 04/2023",
            publication_date="2023-04-15",
        )
    )
    chunks.append(
        Chunk(
            chunk_id="CHK-SIL-002",
            document_id="DOC-FDA-SIL-01",
            drug_name="sildenafil",
            drug_class="pde5_inhibitor",
            topic="interactions",
            source="US Food and Drug Administration / DailyMed",
            section="Section 7: Drug Interactions",
            text="Nitrates + Sildenafil: Concomitant use is strictly contraindicated due to synergistic nitric oxide/cGMP vasodilation. Fatal episodes of profound refractory hypotension, myocardial infarction, and cardiovascular collapse have been documented.",
            related_drugs=("nitroglycerin",),
            version="Rev 04/2023",
            publication_date="2023-04-15",
        )
    )

    # 2. Warfarin - NSAIDs/Aspirin Interaction & Bleeding
    chunks.append(
        Chunk(
            chunk_id="CHK-WAR-001",
            document_id="DOC-FDA-WAR-01",
            drug_name="warfarin",
            drug_class="anticoagulant",
            topic="interactions",
            source="US Food and Drug Administration / DailyMed",
            section="Section 7: Drug Interactions - NSAIDs and Aspirin",
            text="Concomitant use of nonsteroidal anti-inflammatory drugs (NSAIDs, ibuprofen, naproxen) or aspirin with warfarin significantly increases the risk of severe gastrointestinal bleeding and ulceration. NSAIDs inhibit platelet aggregation and cause gastric mucosal erosions.",
            # The reason related_drugs has to exist. This chunk is filed under warfarin but
            # is the authoritative evidence for an *ibuprofen* interaction, so a filter that
            # consulted drug_name alone would answer "no evidence" to the one question this
            # chunk answers.
            related_drugs=("ibuprofen", "naproxen", "aspirin"),
            version="Rev 08/2022",
            publication_date="2022-08-01",
        )
    )
    chunks.append(
        Chunk(
            chunk_id="CHK-WAR-002",
            document_id="DOC-FDA-WAR-01",
            drug_name="warfarin",
            drug_class="anticoagulant",
            topic="warnings",
            source="US Food and Drug Administration / DailyMed",
            section="Section 4: Warnings and Precautions - Hemorrhage",
            text="Warfarin sodium can cause major or fatal bleeding. Bleeding is more likely to occur with higher doses (elevated INR), older age, and concomitant use of antiplatelet drugs (aspirin, clopidogrel).",
            related_drugs=("aspirin", "clopidogrel"),
            version="Rev 08/2022",
            publication_date="2022-08-01",
        )
    )

    # 3. Propranolol - Asthma Contraindication
    chunks.append(
        Chunk(
            chunk_id="CHK-IND-001",
            document_id="DOC-FDA-IND-01",
            drug_name="propranolol",
            drug_class="non_selective_beta_blocker",
            topic="contraindications",
            source="US Food and Drug Administration / DailyMed",
            section="Section 4: Contraindications & Section 5: Warnings",
            text="Propranolol is contraindicated in patients with bronchial asthma or reactive airway disease. Non-selective beta-2 receptor blockade inhibits bronchodilation, precipitating acute, life-threatening bronchospasm and refractory status asthmaticus.",
            # Single-drug contraindication against a *condition*, not another drug. Declared
            # empty rather than omitted so that "reviewed, no associations" is distinguishable
            # from "nobody has looked at this chunk yet".
            related_drugs=(),
            version="Rev 03/2020",
            publication_date="2020-03-12",
        )
    )

    # 4. Amoxicillin - Penicillin Hypersensitivity
    chunks.append(
        Chunk(
            chunk_id="CHK-AMX-001",
            document_id="DOC-FDA-AMX-01",
            drug_name="amoxicillin",
            drug_class="penicillin_antibiotic",
            topic="contraindications",
            source="US Food and Drug Administration / DailyMed",
            section="Section 4: Contraindications & Section 5: Warnings",
            text="Amoxicillin is contraindicated in patients with prior serious hypersensitivity reactions (anaphylaxis, angioedema, Stevens-Johnson syndrome) to penicillins or beta-lactam antibacterials. Severe and fatal IgE-mediated anaphylaxis can occur.",
            # co-amoxiclav *is* amoxicillin plus a beta-lactamase inhibitor, so a penicillin
            # hypersensitivity contraindication applies to it unchanged. A clinical judgement,
            # not a string match — "amoxicillin_clavulanate" appears nowhere in the text.
            related_drugs=("amoxicillin_clavulanate",),
            version="Rev 06/2021",
            publication_date="2021-06-15",
        )
    )

    # 5. Lisinopril + Spironolactone - Hyperkalemia Guidelines
    chunks.append(
        Chunk(
            chunk_id="CHK-LSP-001",
            document_id="DOC-GL-AHA-HF01",
            drug_name="lisinopril",
            drug_class="ace_inhibitor",
            topic="interactions",
            source="American Heart Association / American College of Cardiology",
            section="Section 7.3: RAAS Blockade and Aldosterone Antagonist Combination",
            text="Combination of ACE inhibitors (lisinopril, ramipril) with aldosterone antagonists (spironolactone) confers a high risk of life-threatening hyperkalemia (K+ > 5.5 mEq/L) and renal failure. Serum potassium and renal function must be checked at baseline, 1 week, and periodically.",
            related_drugs=("ramipril", "spironolactone"),
            version="Vol 145, Issue 18",
            publication_date="2022-04-01",
        )
    )

    # 6. Metformin - Renal Impairment & Lactic Acidosis
    chunks.append(
        Chunk(
            chunk_id="CHK-MET-001",
            document_id="DOC-FDA-MET-01",
            drug_name="metformin",
            drug_class="biguanide",
            topic="contraindications",
            source="US Food and Drug Administration / DailyMed",
            section="Boxed Warning: Lactic Acidosis & Section 4: Contraindications",
            text="Metformin is contraindicated in severe renal impairment (eGFR < 30 mL/min/1.73m2). Impaired renal elimination leads to metformin accumulation and elevated risk of life-threatening lactic acidosis.",
            related_drugs=(),
            version="Rev 09/2021",
            publication_date="2021-09-20",
        )
    )

    # 7. Clopidogrel + Omeprazole - CYP2C19 Interaction
    chunks.append(
        Chunk(
            chunk_id="CHK-CLP-001",
            document_id="DOC-FDA-CLOP-01",
            drug_name="clopidogrel",
            drug_class="antiplatelet",
            topic="interactions",
            source="US Food and Drug Administration Safety Alert",
            section="CYP2C19 Inhibition and Omeprazole Interaction",
            text="Omeprazole significantly inhibits CYP2C19-mediated activation of clopidogrel prodrug, reducing antiplatelet efficacy by ~45% and multiplying the risk of stent thrombosis and myocardial infarction. Avoid concomitant omeprazole; consider pantoprazole.",
            # pantoprazole is named as the safer *alternative*, not as an interacting drug, and
            # is absent from the catalog in any case. Declaring it would make this chunk
            # answer "is pantoprazole a problem with clopidogrel?" with evidence saying the
            # opposite — the precise failure mode that rules out extracting names from prose.
            related_drugs=("omeprazole",),
            version="FDA Safety Communication",
            publication_date="2016-11-01",
        )
    )

    # 8. Sertraline + Tramadol - Serotonin Syndrome
    chunks.append(
        Chunk(
            chunk_id="CHK-SRT-001",
            document_id="DOC-FDA-ZOL-01",
            drug_name="sertraline",
            drug_class="ssri",
            topic="interactions",
            source="US Food and Drug Administration / DailyMed",
            section="Section 7: Drug Interactions - Serotonergic Drugs",
            text="Co-administration of sertraline with tramadol increases the risk of Serotonin Syndrome (hyperreflexia, clonus, autonomic instability, hyperthermia) and lowered seizure threshold via dual serotonergic mechanisms.",
            related_drugs=("tramadol",),
            version="Rev 12/2021",
            publication_date="2021-12-05",
        )
    )

    return chunks
