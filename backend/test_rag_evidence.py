"""
Clinical evidence retrieval failure modes.

Converted from a standalone script whose eight checks lived in one
``run_rag_failure_mode_tests()`` function. pytest imported the module and ran
nothing, because the function was not named ``test_*``. As one function the checks
were also all-or-nothing: the first failure hid the seven behind it, and a
retrieval regression would have reported as a single opaque failure rather than
naming which guarantee broke.

Nothing here touches the database — the corpus and index are in-memory — so these
tests use no session fixture.

What is being protected: this layer attaches citations to safety findings that a
clinician is expected to act on. The failure that matters is not "retrieval was
imprecise", it is evidence that looks authoritative and is not — a chunk about the
wrong drug, a confident answer to a query the corpus cannot support, or a claim
with no traceable source. Each test below pins one of those.
"""

from datetime import datetime

import pytest

from app.rag.corpus import build_corpus_chunks
from app.rules.contraindication_engine import (
    ContraindicationAlert,
    ContraindicationSeverity,
)
from app.rag.retriever import HybridEvidenceRetriever
from app.rules.interaction_engine import (
    InteractionSeverity,
    MedicationInteractionAlert,
)
from app.rules.safety_assessment import SafetyAssessment


@pytest.fixture(scope="module")
def retriever():
    """Built once: the index is immutable and every test below only reads it."""
    return HybridEvidenceRetriever()


@pytest.fixture(scope="module")
def sildenafil_nitrate_alert():
    """A CONTRAINDICATED pair the corpus is known to document."""
    return MedicationInteractionAlert(
        rule_id="INT-DDI-001",
        drug_a="Sildenafil",
        drug_b="Nitroglycerin",
        severity=InteractionSeverity.CONTRAINDICATED,
        mechanism=(
            "Synergistic relaxation of vascular smooth muscle via cGMP pathway "
            "potentiation."
        ),
        clinical_effect=(
            "Severe, life-threatening refractory hypotension and cardiovascular "
            "collapse."
        ),
        recommendation="Co-administration is strictly contraindicated.",
        source="Viagra FDA Prescribing Information",
        source_id="FDA-LABEL-SIL-01",
        source_title="Viagra FDA Prescribing Information",
        source_version="Rev 04/2023",
        source_date="2023-04-15",
    )


@pytest.fixture(scope="module")
def critical_bundle(retriever, sildenafil_nitrate_alert):
    """
    An evidence bundle built from a CRITICAL assessment.

    Shared by the two tests that inspect a fully assembled bundle, so it is built
    once rather than twice.
    """
    assessment = SafetyAssessment(
        patient_id=42,
        evaluated_at=datetime.now(),
        risk_level="CRITICAL",
        requires_human_review=True,
        recommended_action="BLOCK / URGENT REVIEW",
        medication_interactions=[sildenafil_nitrate_alert],
        contraindications=[
            ContraindicationAlert(
                medication="Propranolol",
                contraindication_type="CHRONIC_CONDITION",
                trigger="Asthma",
                severity=ContraindicationSeverity.CONTRAINDICATED,
                clinical_risk="Life-threatening bronchospasm",
                recommendation="Contraindicated in active asthma.",
            )
        ],
    )
    return retriever.retrieve_evidence_bundle(assessment)


def test_query_retrieves_the_drug_it_asked_about(retriever):
    """The top hit for a warfarin query is warfarin, not a neighbouring drug."""
    results = retriever.search(query="warfarin anticoagulant bleeding risk", top_k=2)

    assert results, "no evidence retrieved for a drug the corpus documents"
    assert results[0].drug_name == "warfarin", (
        f"top hit was {results[0].drug_name!r}, not warfarin: "
        f"{[(r.chunk_id, r.drug_name) for r in results]}"
    )


def test_interaction_finding_is_supported_by_matching_evidence(
    retriever, sildenafil_nitrate_alert
):
    """
    A documented interaction comes back with evidence that is actually about it.

    ``has_sufficient_evidence`` alone is not enough — it would be satisfied by any
    chunk at all. The text check is what distinguishes real support from a
    confident-looking citation about something else.
    """
    result = retriever.retrieve_for_interaction(sildenafil_nitrate_alert)

    assert result.has_sufficient_evidence is True, (
        "sildenafil + nitrates is documented in the corpus but was reported as "
        f"unsupported (confidence {result.confidence})"
    )
    assert any(
        "nitrates" in c.text.lower() or "hypotension" in c.text.lower()
        for c in result.evidence
    ), (
        "evidence was returned but none of it mentions nitrates or hypotension: "
        f"{[c.chunk_id for c in result.evidence]}"
    )


def test_drug_filter_excludes_every_other_drug(retriever):
    """
    A drug filter is a hard constraint, not a ranking preference.

    "bleeding risk" matches several drugs, so an off-target chunk leaking through
    here would attach another drug's label text to a warfarin finding.
    """
    results = retriever.search(query="bleeding risk", drug_filter="warfarin", top_k=5)

    assert results, "the filter excluded everything, including the target drug"
    offenders = [(r.chunk_id, r.drug_name) for r in results if r.drug_name != "warfarin"]
    assert not offenders, f"non-warfarin chunks survived a warfarin filter: {offenders}"


def test_irrelevant_query_returns_nothing(retriever):
    """
    Below the relevance threshold the honest answer is no answer.

    A retriever that always returns its best match will answer a question the
    corpus cannot support, which is precisely how a fabricated citation gets
    attached to a clinical claim.
    """
    # At any threshold, an irrelevant query must not retrieve evidence
    results = retriever.search(
        query="what is the weather like today in london",
        min_coverage=0.01,
        min_cosine=0.01,
    )

    assert results == [], (
        "a non-clinical query returned evidence: "
        f"{[(r.chunk_id, r.relevance_score) for r in results]}"
    )


def test_every_corpus_chunk_carries_version_and_date_provenance():
    """
    Provenance is checked at the corpus level, so an unversioned chunk cannot be
    added without a test failing.

    Drug labelling changes. A citation without a version and date cannot be audited
    later, and cannot be recognised as stale.
    """
    chunks = build_corpus_chunks()
    assert chunks, "the clinical corpus is empty"

    missing_version = [c.chunk_id for c in chunks if not c.version]
    assert not missing_version, f"chunks with no version tag: {missing_version}"

    bad_date = [
        c.chunk_id
        for c in chunks
        if not c.publication_date or len(c.publication_date) != 10
    ]
    assert not bad_date, f"chunks without a YYYY-MM-DD publication date: {bad_date}"


def test_uncatalogued_drug_is_reported_as_unsupported(retriever):
    """
    A drug the corpus has never heard of yields an explicit no-evidence result.

    The dangerous alternative is silence that reads as agreement: a finding shown
    with no citation looks the same in a UI as a finding whose citation was never
    sought. Confidence 0.0 and the false flag are what let the caller say
    "unverified" instead.
    """
    alert = ContraindicationAlert(
        medication="XylotroxinFakeDrug",
        contraindication_type="ALLERGY",
        trigger="UnicornDander",
        severity=ContraindicationSeverity.CONTRAINDICATED,
        clinical_risk="Unknown hypothetical reaction",
        recommendation="Do not use",
    )

    result = retriever.retrieve_for_contraindication(alert)

    assert result.has_sufficient_evidence is False, (
        "an invented drug was reported as having sufficient supporting evidence: "
        f"{[c.chunk_id for c in result.evidence]}"
    )
    assert result.confidence == 0.0, result.confidence


def test_evidence_retrieval_cannot_downgrade_a_critical_assessment(critical_bundle):
    """
    The deterministic risk level survives the evidence layer untouched.

    This is the layering invariant: rules decide, retrieval annotates. If evidence
    retrieval could alter ``risk_level``, a thin corpus would quietly soften a
    CRITICAL finding into something a clinician is not paged about — the rules
    engine's verdict would depend on how well the library happened to be stocked.
    """
    assert critical_bundle.assessment_risk_level == "CRITICAL", (
        "risk level was changed by evidence retrieval: "
        f"{critical_bundle.assessment_risk_level}"
    )
    assert len(critical_bundle.results) == 2, (
        f"expected one result per finding (2), got {len(critical_bundle.results)}"
    )
    assert critical_bundle.all_findings_supported is True, (
        "both findings are documented in the corpus but were not all supported"
    )


def test_every_citation_is_traceable(critical_bundle):
    """
    Each attached chunk names its source, section, version and document.

    Those four fields are the difference between a citation a clinician can look up
    and a plausible-sounding sentence. Any one of them missing makes the claim
    unverifiable in exactly the situation where verification matters.
    """
    incomplete = [
        (chunk.chunk_id, field)
        for result in critical_bundle.results
        for chunk in result.evidence
        for field, value in (
            ("source", chunk.source),
            ("section", chunk.section),
            ("version", chunk.version),
            ("document_id", chunk.document_id),
        )
        if not value
    ]

    assert not incomplete, f"citations missing required provenance fields: {incomplete}"
    assert critical_bundle.total_evidence_chunks > 0, "bundle attached no citations"


def test_within_entity_false_positive_is_rejected(retriever):
    """
    An adversarial/mismatched query that correctly resolves to the entity but contains
    no clinical topic overlap must NOT be marked sufficient, even if the drug name IDF
    is high enough to mathematically clear the baseline threshold.
    """
    alert = MedicationInteractionAlert(
        rule_id="INT-ADV",
        drug_a="Metformin",
        drug_b="FakeDrug",
        severity=InteractionSeverity.MODERATE,
        mechanism="gastrointestinal bleeding",
        clinical_effect="interaction",
        recommendation="Monitor",
        source="Test",
        source_id="T1",
        source_title="T1",
        source_version="v1",
        source_date="2024",
    )
    # Target chunk (CHK-MET-001) is about lactic acidosis, not GI bleeding.
    result = retriever.retrieve_for_interaction(alert)
    assert result.has_sufficient_evidence is False, (
        "Chunk satisfied sufficiency purely on drug-name overlap."
    )


def test_within_entity_true_positive_is_accepted(retriever):
    """
    A short, specific clinical query must NOT be inadvertently rejected by the
    non-entity threshold. It must be recognized as sufficient.
    """
    alert = ContraindicationAlert(
        medication="Metformin",
        contraindication_type="CONDITION",
        trigger="Lactic Acidosis",
        severity=ContraindicationSeverity.CONTRAINDICATED,
        clinical_risk="",
        recommendation="Do not use",
    )
    result = retriever.retrieve_for_contraindication(alert)
    assert result.has_sufficient_evidence is True, (
        "Legitimate short query was rejected; non-entity threshold may be too tight."
    )
