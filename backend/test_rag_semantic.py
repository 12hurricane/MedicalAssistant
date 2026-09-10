"""
Semantic (dense) retrieval arm — boundary containment, ranking, and degradation.

The claim this file exists to defend is structural, not statistical: **the entity
boundary gates the dense arm the same way it gates the lexical arms**, by deciding what
is in the candidate set before any scoring happens, rather than by filtering results
afterwards. Filtering afterwards would be enough to keep a wrong-drug chunk out of a
response, and would still be wrong — the comparison would have happened, and the next
code path to read the raw scores (a widened top_k, a recall-expansion experiment, a
debug endpoint) would inherit an unfiltered ranking that looks calibrated.

So the tests assert absence of work, not just absence of output. An unresolvable drug
filter must produce zero embedding calls, not zero surviving results.

Why unfiltered dense retrieval is the dangerous case, measured over this corpus:

    "metformin gastrointestinal bleeding interaction"  -> CHK-WAR-001 (warfarin) 0.715
    "amoxicillin severe renal impairment lactic acidosis" -> CHK-MET-001 (metformin) 0.713

Both score higher than any legitimate paraphrase scores against the right drug (max
0.701). Lexically the same queries score ~0.000 on those chunks. The dense arm does not
merely fail to find the answer without a boundary; it returns another drug's chunk with a
number that reads as confidence.

Most tests here use ``StaticEmbedder`` — deterministic, no daemon, similarity a function
of the document alone. One test at the end runs the real ``nomic-embed-text`` and skips
when it is not serving, because a double that reproduces the numbers proves the
arithmetic and cannot prove the model still means what it meant when it was measured.
"""

import pytest

from app.rag.embeddings import (
    DOCUMENT_PREFIX,
    OllamaEmbedder,
    StaticEmbedder,
)
from app.rag.indexer import ClinicalCorpusIndex, canonical_entity
from app.rag.retriever import (
    MIN_COSINE_THRESHOLD,
    SEMANTIC_RESCALE_CEILING,
    SEMANTIC_RESCALE_FLOOR,
    SUFFICIENCY_MIN_COSINE,
    HybridEvidenceRetriever,
    rank_score,
)
from app.rules.interaction_engine import InteractionSeverity, MedicationInteractionAlert

# ---- measured constants -------------------------------------------------------------
# The production interaction query, built exactly as ``retrieve_for_interaction`` builds
# it: f"{drug_a} {drug_b} interaction {mechanism} {clinical_effect}".
RAG8_QUERY = (
    "Warfarin Ibuprofen interaction Displaced protein binding Major bleeding risk"
)

# Live ``nomic-embed-text`` similarities for that query against the two warfarin chunks,
# measured 2026-08-27. CHK-WAR-001 is the correct answer — it is the chunk whose text is
# the ibuprofen/NSAID bleeding interaction — and the lexical arms rank it *second*, which
# is defect RAG-8. Semantic ranks it first.
WAR1_SEMANTIC = 0.772
WAR2_SEMANTIC = 0.713

# Lexical scores for the same query, measured from the index (not asserted approximately:
# these are what ``compute_lexical_coverage`` / ``compute_tfidf_cosine`` return today, and
# a corpus edit that moves them should fail this file rather than silently re-tune it).
WAR1_COVERAGE, WAR1_COSINE = 0.3771, 0.1952
WAR2_COVERAGE, WAR2_COSINE = 0.3882, 0.2538


@pytest.fixture(scope="module")
def index() -> ClinicalCorpusIndex:
    return ClinicalCorpusIndex()


@pytest.fixture
def warfarin_ids(index) -> list:
    """Chunk ids inside the warfarin entity boundary, from the index itself.

    Read out of ``by_entity`` rather than written down, so a corpus that grows a third
    warfarin chunk widens the expectation instead of failing on an unrelated addition.
    """
    return [c.chunk_id for c in index.by_entity[canonical_entity("warfarin")]]


def _interaction_alert(drug_a="Warfarin", drug_b="Ibuprofen") -> MedicationInteractionAlert:
    """The alert whose retrieval query is ``RAG8_QUERY``."""
    return MedicationInteractionAlert(
        rule_id="INT-DDI-WAR-IBU",
        drug_a=drug_a,
        drug_b=drug_b,
        severity=InteractionSeverity.MAJOR,
        mechanism="Displaced protein binding",
        clinical_effect="Major bleeding risk",
        recommendation="Avoid NSAIDs; prefer acetaminophen with INR monitoring.",
        source="Coumadin FDA Prescribing Information",
        source_id="FDA-LABEL-WAR-01",
        source_title="Coumadin FDA Prescribing Information",
        source_version="Rev 08/2022",
        source_date="2022-08-01",
    )


# ---- 1. the boundary gates the dense arm structurally --------------------------------


def test_unresolvable_drug_filter_never_embeds_anything(index):
    """A drug outside the corpus costs zero embedding calls, not just zero results.

    This is the assertion the whole design turns on. ``search`` returns ``[]`` at the
    entity-resolution step, which is *above* the embedding call, so there is no query
    vector, no document vector, and nothing to compare. A retriever that embedded first
    and filtered second would pass a results-only assertion identically while having
    already ranked the query against all ten chunks.
    """
    spy = StaticEmbedder({"warfarin": 0.99}, default=0.9)
    retriever = HybridEvidenceRetriever(index=index, embedder=spy)

    assert retriever.search(query="bleeding risk", drug_filter="NotARealDrug") == []

    assert spy.query_calls == 0, "a query was embedded for a drug not in the corpus"
    assert spy.document_calls == 0, "the corpus was embedded for a drug not in it"


def test_unknown_topic_filter_never_embeds_anything(index):
    """Same structural claim for the other early return above the embedding call."""
    spy = StaticEmbedder(default=0.9)
    retriever = HybridEvidenceRetriever(index=index, embedder=spy)

    assert retriever.search(
        query="warfarin bleeding risk",
        drug_filter="warfarin",
        topic_filter="no_such_topic",
    ) == []

    assert spy.query_calls == 0
    assert spy.document_calls == 0


def test_empty_query_never_embeds_anything(index):
    """A query with no scorable tokens returns before the boundary is even consulted."""
    spy = StaticEmbedder(default=0.9)
    retriever = HybridEvidenceRetriever(index=index, embedder=spy)

    assert retriever.search(query="   the a of   ", drug_filter="warfarin") == []
    assert spy.query_calls == 0
    assert spy.document_calls == 0


def test_semantic_comparison_covers_exactly_the_entity_candidates(index, warfarin_ids):
    """The dot products are taken over the boundary's chunks and no others.

    Asserted on the score map rather than on the returned chunks, because the returned
    chunks have also passed the inclusion gate — a chunk could be absent from the results
    for a scoring reason while still having been compared. The score map is the
    comparison itself.
    """
    embedder = StaticEmbedder({"ibuprofen": WAR1_SEMANTIC}, default=0.5)
    retriever = HybridEvidenceRetriever(index=index, embedder=embedder)

    candidates = index.by_entity[canonical_entity("warfarin")]
    scores = retriever._semantic_scores(RAG8_QUERY, candidates)

    assert set(scores) == set(warfarin_ids)
    assert len(warfarin_ids) < len(index.chunks), (
        "the boundary admits the whole corpus, so this test proves nothing"
    )
    # And nothing from outside it, named explicitly: the cross-drug leak measured in the
    # module docstring is a metformin/warfarin confusion in both directions.
    assert not any(cid.startswith("CHK-MET") for cid in scores)


def test_adversarial_similarity_cannot_cross_the_boundary(index):
    """A wrong-drug chunk scored 1.0 does not surface, and is not even compared.

    The embedder here is built to fail the boundary if the boundary is a post-filter: it
    gives the metformin chunk perfect similarity and every warfarin chunk a low one, so a
    retriever that ranked first and filtered second would have metformin at rank 1 and
    would have to notice. Nothing has to notice, because metformin is not a candidate.
    """
    embedder = StaticEmbedder({"metformin": 1.0}, default=0.05)
    retriever = HybridEvidenceRetriever(index=index, embedder=embedder)

    # Guard against the test passing vacuously: confirm the double really would rank the
    # metformin chunk top if it were ever handed it.
    metformin_chunk = next(c for c in index.chunks if c.chunk_id.startswith("CHK-MET"))
    metformin_text = index._indexed_text(metformin_chunk)
    assert embedder.similarity_for(metformin_text) == 1.0

    results = retriever.search(query=RAG8_QUERY, drug_filter="warfarin", top_k=10)

    assert results, "expected the warfarin chunks to be retrievable at all"
    assert all(r.drug_name == "warfarin" for r in results)
    assert not any(r.chunk_id.startswith("CHK-MET") for r in results)
    assert all(r.entity_verified for r in results)


# ---- 2. degradation is exact, and touches no gate -----------------------------------


@pytest.mark.parametrize(
    "query,drug_filter",
    [
        (RAG8_QUERY, "Warfarin"),
        ("metformin severe renal impairment lactic acidosis", "metformin"),
        ("propranolol bronchial asthma bronchospasm contraindication", "propranolol"),
        ("warfarin", "warfarin"),
        ("clot prevention drug", "warfarin"),
    ],
)
def test_unavailable_embedder_is_byte_identical_to_lexical_only(index, query, drug_filter):
    """An outage costs ordering quality and changes nothing else.

    Compared as whole dataclasses, not field by field: every score, every flag, and the
    order. If the dense arm ever leaked into a gate, some query in this list would come
    back with a different ``entity_verified``, a different membership, or a different
    length under one configuration and not the other.
    """
    lexical = HybridEvidenceRetriever(index=index)
    degraded = HybridEvidenceRetriever(
        index=index, embedder=StaticEmbedder({"ibuprofen": 0.99}, unavailable=True)
    )

    assert degraded.search(query=query, drug_filter=drug_filter) == lexical.search(
        query=query, drug_filter=drug_filter
    )


def test_unavailable_embedder_does_not_change_sufficiency(index):
    """Sufficiency is a lexical decision, so it must survive the daemon going away.

    The failure this forbids is the safe-but-useless one: if semantic similarity were a
    sufficiency conjunct, an Ollama hiccup would turn every finding into "no sufficient
    evidence" and an outage would be indistinguishable from an empty corpus.
    """
    alert = _interaction_alert()
    lexical = HybridEvidenceRetriever(index=index)
    degraded = HybridEvidenceRetriever(
        index=index, embedder=StaticEmbedder({"ibuprofen": 0.99}, unavailable=True)
    )

    a = lexical.retrieve_for_interaction(alert)
    b = degraded.retrieve_for_interaction(alert)

    assert b.has_sufficient_evidence == a.has_sufficient_evidence
    assert b.confidence == a.confidence
    assert [c.chunk_id for c in b.evidence] == [c.chunk_id for c in a.evidence]


def test_unavailable_embedder_records_none_not_zero(index):
    """``semantic_score`` is ``None`` on an outage, never 0.0.

    0.0 is a real measurement meaning "unrelated". A chunk recorded as unrelated because
    the daemon was down is a different fact, and the two must not be written the same way
    — the field is what a later reader would use to explain a ranking.
    """
    retriever = HybridEvidenceRetriever(
        index=index, embedder=StaticEmbedder({"ibuprofen": 0.99}, unavailable=True)
    )
    results = retriever.search(query=RAG8_QUERY, drug_filter="Warfarin")

    assert results
    assert all(r.semantic_score is None for r in results)


def test_lexical_only_retriever_has_no_semantic_arm(index):
    """``embedder=None`` is the degraded configuration, not a separate code path.

    Asserted because the rest of the suite constructs ``HybridEvidenceRetriever()`` with
    no embedder, and that is only sound as coverage of the outage path if the two are the
    same thing.
    """
    retriever = HybridEvidenceRetriever(index=index)
    assert retriever.semantic is None
    assert retriever._semantic_scores(RAG8_QUERY, index.chunks) == {}


# ---- 3. ranking arithmetic ----------------------------------------------------------


def test_rank_score_without_semantic_is_the_lexical_blend():
    """The pre-embeddings formula, preserved exactly, for the outage path."""
    assert rank_score(0.4, 0.2) == round(0.7 * 0.4 + 0.3 * 0.2, 3)
    assert rank_score(WAR2_COVERAGE, WAR2_COSINE) == round(0.7 * WAR2_COVERAGE + 0.3 * WAR2_COSINE, 3)
    assert rank_score(WAR1_COVERAGE, WAR1_COSINE) == round(0.7 * WAR1_COVERAGE + 0.3 * WAR1_COSINE, 3)


def test_rank_score_stays_in_unit_interval():
    """``confidence`` is this number rounded, so it has to remain readable as one.

    Includes similarities outside the rescale window in both directions, since the window
    is measured over one corpus and a future query can fall outside it.
    """
    for semantic in (-1.0, 0.0, SEMANTIC_RESCALE_FLOOR, 0.6, SEMANTIC_RESCALE_CEILING, 1.0, None):
        for coverage, cosine in ((0.0, 0.0), (0.5, 0.5), (1.0, 1.0)):
            assert 0.0 <= rank_score(coverage, cosine, semantic) <= 1.0


def test_rank_score_is_monotonic_in_semantic_similarity():
    """Higher similarity never ranks a chunk lower — the ordering claim, isolated."""
    scores = [rank_score(0.4, 0.2, s) for s in (0.40, 0.55, 0.70, 0.85)]
    assert scores == sorted(scores)
    assert scores[0] < scores[-1], "semantic similarity does not move the blend at all"


# ---- 4. RAG-8: the defect this arm was added to fix ---------------------------------


def test_lexical_ranking_alone_puts_the_wrong_chunk_first(index):
    """RAG-8, reproduced. Without this the flip below would prove nothing.

    CHK-WAR-001 *is* the ibuprofen interaction chunk. CHK-WAR-002 is the general
    hemorrhage warning. On the ibuprofen interaction query the lexical arms prefer the
    hemorrhage warning, because "bleeding" appears twice in it and the query's own word
    "bleeding" outweighs the one term that identifies the right chunk.
    """
    retriever = HybridEvidenceRetriever(index=index)
    results = retriever.search(query=RAG8_QUERY, drug_filter="Warfarin", top_k=2)

    assert [r.chunk_id for r in results] == ["CHK-WAR-002", "CHK-WAR-001"]


def test_semantic_ranking_puts_the_ibuprofen_chunk_first(index):
    """RAG-8, fixed by re-ranking inside the boundary.

    The similarities are the measured live values, so this asserts the arithmetic of the
    blend against the real ordering rather than against a chosen pair that happens to
    work. The margin is 0.017, which is thin — recorded here so that a future weighting
    change that erases it fails loudly instead of quietly reverting RAG-8.
    """
    embedder = StaticEmbedder(
        # Markers unique to one chunk each within the indexed corpus text:
        # "ibuprofen" appears only in CHK-WAR-001's text, "Hemorrhage" only in
        # CHK-WAR-002's section heading.
        {"ibuprofen": WAR1_SEMANTIC, "Hemorrhage": WAR2_SEMANTIC},
        # Every other chunk is outside the warfarin boundary and so is never compared.
        default=0.0,
    )
    retriever = HybridEvidenceRetriever(index=index, embedder=embedder)
    results = retriever.search(query=RAG8_QUERY, drug_filter="Warfarin", top_k=2)

    assert [r.chunk_id for r in results] == ["CHK-WAR-001", "CHK-WAR-002"]

    war1, war2 = results
    assert war1.semantic_score == WAR1_SEMANTIC
    assert war2.semantic_score == WAR2_SEMANTIC
    assert war1.relevance_score == rank_score(WAR1_COVERAGE, WAR1_COSINE, WAR1_SEMANTIC)
    assert war2.relevance_score == rank_score(WAR2_COVERAGE, WAR2_COSINE, WAR2_SEMANTIC)
    assert war1.relevance_score == 0.442
    assert war2.relevance_score == 0.425

    # The lexical scores are unchanged by re-ranking: the dense arm reorders, it does not
    # rewrite what the lexical arms measured, and the gates read the lexical fields.
    assert war1.lexical_score == round(WAR1_COVERAGE, 3)
    assert war1.tfidf_cosine_score == round(WAR1_COSINE, 3)


def test_the_correct_chunk_survives_the_recalibrated_cosine_floor(index):
    """The floor sits below the promoted chunk's cosine, and above nothing accidental.

    Re-ranking made CHK-WAR-001 rank 1, and its TF-IDF cosine is 0.195 — below the 0.20
    floor that was calibrated when CHK-WAR-002 (cosine 0.254) ranked first. So for one
    step the retrieval was right and the verdict was wrong. Step 2 re-derived the floor
    against the union of both rank-1 distributions, giving 0.16.

    Asserted as a relation rather than as a literal, so the invariant that matters — the
    floor admits the corpus's own best answer, with headroom — is what fails if either
    number moves. The upper bound keeps it from silently drifting up to where 0.195 was
    excluded again.
    """
    assert SUFFICIENCY_MIN_COSINE < WAR1_COSINE < WAR2_COSINE
    assert SUFFICIENCY_MIN_COSINE > MIN_COSINE_THRESHOLD, (
        "the sufficiency cosine conjunct has sunk to the inclusion gate, so it now "
        "filters nothing while still reading as an active check"
    )


def test_semantic_rank_one_is_sufficient_evidence(index):
    """The finding CHK-WAR-001 supports must survive the sufficiency gate.

    A warfarin/ibuprofen bleeding interaction with the FDA label's own interaction
    section retrieved and entity-verified is exactly the case the corpus answers. If that
    reports "no sufficient evidence", the floors are wrong, not the retrieval.

    This is RAG-8 closed end to end: not just that the right chunk ranks first, but that
    the verdict built on it says so.
    """
    embedder = StaticEmbedder(
        {"ibuprofen": WAR1_SEMANTIC, "Hemorrhage": WAR2_SEMANTIC}, default=0.0
    )
    retriever = HybridEvidenceRetriever(index=index, embedder=embedder)
    result = retriever.retrieve_for_interaction(_interaction_alert())

    assert result.evidence[0].chunk_id == "CHK-WAR-001"
    assert result.has_sufficient_evidence is True
    assert result.evidence[0].entity_verified is True
    assert result.citable_evidence, "sufficient evidence that cannot be cited"


# ---- 5. the real model --------------------------------------------------------------


def _live_embedder() -> OllamaEmbedder:
    """A real embedder, or a skip.

    Probed lazily inside the test rather than at import, so the other tests in the suite
    do not pay a connect attempt during collection. Short timeout: this is a liveness
    check, and a wedged daemon should skip quickly rather than stall the run.
    """
    embedder = OllamaEmbedder(timeout=15.0)
    if embedder.embed_query("probe") is None:
        pytest.skip(
            f"no embeddings daemon at {embedder.base_url} serving "
            f"{embedder.model_name!r}"
        )
    return embedder


def test_live_model_reproduces_the_measured_ordering(index):
    """``nomic-embed-text`` itself prefers the ibuprofen chunk on the ibuprofen query.

    The ``StaticEmbedder`` tests prove the blend arithmetic; only this proves the model
    still means what it meant when the constants above were measured. Skipped when the
    daemon is not serving, so it is a check that runs where the model runs rather than a
    dependency of the suite.

    The ordering is asserted exactly and the magnitudes loosely. Ordering is what the
    design relies on; magnitude is what the measurement found unusable, and pinning it
    tightly would make a model update fail here for a reason the design does not care
    about.
    """
    retriever = HybridEvidenceRetriever(index=index, embedder=_live_embedder())
    results = retriever.search(query=RAG8_QUERY, drug_filter="Warfarin", top_k=2)

    assert [r.chunk_id for r in results] == ["CHK-WAR-001", "CHK-WAR-002"]

    war1, war2 = results
    assert war1.semantic_score is not None and war2.semantic_score is not None
    assert war1.semantic_score > war2.semantic_score
    assert 0.70 <= war1.semantic_score <= 0.85, (
        f"live similarity {war1.semantic_score} is far from the measured "
        f"{WAR1_SEMANTIC}; the rescale window in retriever.py was derived from that "
        f"measurement and needs re-deriving"
    )


def test_live_model_returns_normalised_vectors_of_one_dimension():
    """Unit length and a single dimension, since ``similarities`` is a bare dot product.

    Also the only place the document prefix is exercised against the real model. If the
    daemon ever returned vectors of mixed length, ``SemanticIndex`` would refuse the
    batch and semantic ranking would silently switch off; better to see it here.
    """
    embedder = _live_embedder()
    vectors = embedder.embed_documents(["warfarin bleeding", "metformin lactic acidosis"])

    assert vectors is not None
    assert len({len(v) for v in vectors}) == 1
    for vector in vectors:
        assert abs(sum(x * x for x in vector) - 1.0) < 1e-6

    assert DOCUMENT_PREFIX.endswith(" "), (
        "the task prefix must be separated from the text it prefixes"
    )
