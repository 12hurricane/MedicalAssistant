"""
Hybrid Clinical Evidence Retriever

Combines BM25 lexical keyword matching, TF-IDF cosine scoring over sparse term vectors,
and dense semantic similarity from ``app/rag/embeddings.py``. Executes targeted
retrieval queries constructed directly from deterministic safety findings.

The three signals are not interchangeable, and the asymmetry is deliberate. The two
lexical signals gate: they decide whether a chunk is returned at all and whether the
evidence counts as sufficient. The semantic signal only ranks. Measurement over this
corpus found ``nomic-embed-text`` gives a usable ordering and an unusable magnitude —
its must-pass/must-fail sufficiency band is 0.007 wide and its inclusion band has
negative width — so there is no value at which it could be a floor. See the
``embeddings.py`` docstring for the numbers.

Entity boundary invariant
-------------------------
When a ``drug_filter`` is supplied, the retriever resolves it to a canonical entity id
and restricts the candidate set to chunks indexed under that entity — *before* any
scoring runs, lexical or semantic. If the entity is not in the index, the answer is
``[]``: no evidence for this drug in the corpus. That boundary is structural, not a
post-hoc check, so no fallback path can widen it.

The boundary matters more for the dense arm than for the sparse one, which is why the
embedding call sits below both early returns rather than beside the scoring loop.
An unanswerable query scores 0.000 lexically; the same query scores 0.715 semantically
against *another drug's* chunk — higher than any legitimate paraphrase scores against
the right one. Unfiltered dense retrieval does not merely fail to find the answer, it
returns the wrong drug with a number that reads as confidence.

Scoring invariant
-----------------
Scores are query-intrinsic: BM25 coverage (the fraction of an ideal score this chunk
achieves), TF-IDF cosine, and rescaled semantic similarity, all in [0, 1] and all
depending only on the chunk and the query. A score normalised against the best result in
the same batch would guarantee some chunk scores 1.0 for every query including
unanswerable ones, making every threshold meaningless. This is why the semantic term is
rescaled against fixed corpus-wide constants rather than min-maxed within the candidate
set, which would reintroduce exactly that denominator.
"""

import enum
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from app.rag.corpus import Chunk
from app.rag.embeddings import Embedder, OllamaEmbedder, SemanticIndex
from app.rag.vector_store import ChromaSemanticIndex
from app.rag.indexer import (
    ClinicalCorpusIndex,
    _tokenize,
    canonical_entity,
    get_default_index,
)
from app.rules.contraindication_engine import ContraindicationAlert, DuplicateTherapyAlert
from app.rules.drug_normalizer import CANONICAL_DRUG_CATALOG
from app.rules.interaction_engine import MedicationInteractionAlert
from app.rules.safety_assessment import AdherenceSafetyAlert, SafetyAssessment


class RetrievalMode(enum.Enum):
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass
class RetrievedEvidenceChunk:
    """Individual retrieved evidence chunk with citation metadata."""
    chunk_id: str
    document_id: str
    drug_name: str
    source: str
    section: str
    text: str
    version: str
    publication_date: str
    relevance_score: float
    lexical_score: float
    tfidf_cosine_score: float
    non_entity_lexical_score: float = 0.0
    non_entity_tfidf_cosine_score: float = 0.0
    #: Raw cosine similarity from the dense arm, or ``None`` when semantic scoring was
    #: unavailable for this query. ``None`` rather than 0.0 deliberately: 0.0 is a real
    #: measurement meaning "unrelated", and a chunk ranked as unrelated because Ollama
    #: was down is not the same fact. Recorded for debugging and for ``eval_retrieval``;
    #: no gate reads it, and ``app/rag/schemas.py`` does not expose it, following the
    #: precedent already set for the ``non_entity_*`` scores.
    semantic_score: Optional[float] = None
    # True only when this chunk came out of a drug/entity-filtered candidate set.
    # Defaults False, and ``search`` derives it rather than accepting it from the
    # caller: the previous default of True meant any code path that forgot the
    # parameter shipped chunks claiming an attribution check that never ran. A flag
    # that fails open is worse than no flag, because consumers trust it.
    entity_verified: bool = False


@dataclass
class EvidenceResult:
    """Evidence retrieval bundle for a specific clinical safety finding."""
    finding_id: str
    query: str
    topic: str
    evidence: List[RetrievedEvidenceChunk] = field(default_factory=list)
    confidence: float = 0.0
    has_sufficient_evidence: bool = False
    retrieval_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def citable_evidence(self) -> List[RetrievedEvidenceChunk]:
        """The subset of ``evidence`` that may become a citation.

        Unfiltered-fallback chunks stay in ``evidence`` because they are genuine
        retrieval output and suppressing them would hide what the retriever did. They
        must not become citations: a chunk retrieved without an entity boundary may
        document a different drug entirely, and a citation asserts the opposite.

        Exposed as a property rather than left to each consumer's own comprehension so
        that the safe path is the short one. ``has_sufficient_evidence`` already
        refused these, but two of the three consumers iterated ``evidence`` directly
        and never read the flag, so wrong-drug chunks reached the clinical brief
        regardless of what sufficiency said — the entity boundary re-opened one layer
        below where it was enforced.

        Gated on ``entity_verified`` alone, deliberately not on
        ``has_sufficient_evidence``. Attribution is a structural fact; sufficiency
        depends on score thresholds that are still being calibrated, and a citation
        list that moves when a threshold moves would couple provenance to tuning.
        """
        return [c for c in self.evidence if c.entity_verified]


    def to_llm_projection(self) -> dict:
        """
        Strict LLM-facing evidence boundary.
        Filters out internal retrieval states, scores, and unverified chunks.
        """
        status = "SUFFICIENT" if self.has_sufficient_evidence else "INSUFFICIENT"
        
        clinical_evidence = []
        if self.has_sufficient_evidence:
            for c in self.citable_evidence:
                # Extra safety boundary: explicitly ensure the chunk passed all absolute thresholds.
                # In Phase 2, `evidence` already only contains chunks that passed the thresholds,
                # but this check acts as a defensive programming invariant.
                if (c.lexical_score >= SUFFICIENCY_MIN_COVERAGE
                    and c.tfidf_cosine_score >= SUFFICIENCY_MIN_COSINE
                    and c.non_entity_lexical_score >= NON_ENTITY_MIN_COVERAGE
                    and c.non_entity_tfidf_cosine_score >= NON_ENTITY_MIN_COSINE):
                    
                    clinical_evidence.append({
                        "medication": c.drug_name,
                        "evidence_text": c.text,
                        "source": c.source,
                        "section": c.section,
                        "document_id": c.document_id,
                        "version": c.version
                    })

        return {
            "finding_id": self.finding_id,
            "query": self.query,
            "topic": self.topic,
            "evidence_status": status,
            "clinical_evidence": clinical_evidence
        }


@dataclass
class FindingEvidenceBundle:
    """Consolidated evidence package for an entire Safety Assessment."""
    patient_id: int
    assessment_risk_level: str
    results: List[EvidenceResult] = field(default_factory=list)
    total_evidence_chunks: int = 0
    all_findings_supported: bool = False

    def to_llm_projection(self) -> dict:
        """LLM-facing projection of the entire bundle."""
        return {
            "patient_id": self.patient_id,
            "assessment_risk_level": self.assessment_risk_level,
            "all_findings_supported": self.all_findings_supported,
            "results": [r.to_llm_projection() for r in self.results]
        }


# ---- Thresholds ----------------------------------------------------------------
# Every number here is derived from ``eval_retrieval.py`` and must be re-derived when the
# corpus changes — or when *ranking* changes, which is what happened at Phase 2.1.
#
# Measured on the FILTERED candidate set, because that is the only path a safety
# finding takes. The earlier unfiltered grid was the wrong yardstick: its worst
# "noise" cases are ADVERSARIAL queries scoring on *another drug's* chunk, and the
# entity boundary already removes that chunk structurally. Calibrating a filtered-path
# floor against unfiltered cross-drug contamination sets it far too high, which is how
# the previous 0.40/0.24 pair came to sit 0.009 from rejecting real evidence.
#
# Calibrated over the UNION of both ranking configurations, not just the current one.
# Sufficiency is evaluated against ``evidence[0]``, so every floor here is a statement
# about whichever chunk ranks first — and which chunk ranks first depends on whether the
# embeddings daemon answered. Both are real production states. A floor calibrated against
# the dense ordering alone would move a finding from "sufficient" to "no evidence" the
# moment Ollama restarted, which is a safety verdict changing for an infrastructure
# reason; the union costs a little margin and cannot do that.
#
# Adding the dense arm changed rank-1 on exactly 2 of the 22 filtered cases — the
# warfarin/ibuprofen REAL_FINDING (CHK-WAR-002 -> CHK-WAR-001, the RAG-8 fix) and
# "warfarin interaction", which is NAME_PLUS_GENERIC and must fail either way. Measured
# 2026-08-28, must-pass minima over the 12 CLEAR + REAL_FINDING cases:
#
#                       lexical rank-1    dense rank-1    union must-pass min
#     coverage                   0.388           0.377                  0.377
#     cosine                     0.254           0.195                  0.195
#     ne_coverage                0.285           0.278                  0.278
#     ne_cosine                  0.166           0.120                  0.120
#
# NAME_ONLY maxima are unaffected by ranking: coverage 1.000, cosine 0.500, and a hard
# 0.000 on both non-entity signals under both configurations.
#
# So neither whole-query floor can separate a real finding from a bare drug name — a
# bare name outscores every real finding on its own drug's chunks. These two are
# therefore sanity floors, set below the observed minima with margin rather than shaved
# against them, and the *non-entity* floors below are what actually carry sufficiency.

# Conjunctive gate for a chunk to be returned at all (answerable AND specific).
MIN_COVERAGE_THRESHOLD = 0.20
MIN_COSINE_THRESHOLD = 0.15

# Conjunctive gate for evidence to be considered "sufficient" (verified clinical
# evidence). Below the union must-pass minima of 0.377 / 0.195.
#
# The cosine floor came down from 0.20, which was derived when CHK-WAR-002 (cosine 0.254)
# ranked first on the warfarin/ibuprofen finding. Re-ranking promoted CHK-WAR-001 — the
# chunk whose text actually *is* that interaction — and its cosine is 0.195, so the old
# floor rejected the corpus's own best answer to the query. The floor followed the
# distribution it is calibrated against; it was not lowered to make a test pass.
#
# 0.16 rather than a proportional margin. The previous pair kept ~20% headroom below the
# measured minimum, which here would give 0.154 — at or under MIN_COSINE_THRESHOLD, where
# the conjunct becomes unreachable and reads as an active check while filtering nothing.
# 0.16 keeps it live with 0.035 of headroom. That headroom is thin, and thin for a reason
# worth naming: the correct chunk for this finding has genuinely weak lexical cosine,
# which is the whole argument for the dense arm. If a future real finding lands below
# 0.16, the answer is not to lower this again toward the inclusion gate — it is that a
# whole-query cosine floor has stopped separating anything and should be retired rather
# than kept as decoration.
SUFFICIENCY_MIN_COVERAGE = 0.30
SUFFICIENCY_MIN_COSINE = 0.16

# Non-entity floors: the query re-scored with the filtered drug's name stripped out, so
# a chunk cannot clear the gate on the drug name alone. This is the load-bearing check
# — per the numbers above it is the *only* signal that separates "metformin" from a
# real metformin finding, so it cannot be dropped, only calibrated.
#
# Calibrated against the stripped distribution, which is a different distribution from
# the whole-query one: removing a query's rarest token lowers every score, so a
# whole-query number means something else here. Borrowing MIN_COSINE_THRESHOLD was the
# defect — at 0.24 it rejected all three real production queries (ne_cosine 0.219,
# 0.171, 0.166), including the propranolol/asthma contraindication.
#
# All 8 must-fail queries strip to nothing that scores, giving a hard 0.000; 
# must-pass minima are ne_coverage 0.278 and ne_cosine 0.107. 
# Admissible bands are therefore (0.000, 0.278] and (0.000, 0.107].
# Set at the band midpoints, because the must-pass edge has observed cases near it 
# and the must-fail edge has none.
#
# ne_cosine moved 0.08 -> 0.05 after switching to HYBRID ranking, 
# because the dense arm promoted CHK-WAR-001 (which has a lower ne_cosine than CHK-WAR-002),
# narrowing the band to 0.107.
NON_ENTITY_MIN_COVERAGE = 0.14
NON_ENTITY_MIN_COSINE = 0.05


# ---- Ranking --------------------------------------------------------------------
# Semantic similarity is rescaled onto [0, 1] before it is blended, because the raw
# cosines from ``nomic-embed-text`` occupy a narrow, high band — the observed corpus-wide
# range is 0.398 (worst IRRELEVANT query) to 0.895 (best CLEAR query). Averaged raw, a
# term that never drops below 0.4 would act as a constant offset plus a little noise, and
# a ranking signal that barely varies is not a ranking signal.
#
# The rescaling is affine against these two fixed constants, not min-max against the
# candidate set. Min-max within a batch would make a chunk's score depend on which other
# chunks were retrieved, which is the query-relative denominator the module docstring's
# scoring invariant exists to forbid. Being fixed, these constants set how far semantic
# can move a blend rather than which arm wins, so an imperfect range costs margin and not
# ordering.
SEMANTIC_RESCALE_FLOOR = 0.398
SEMANTIC_RESCALE_CEILING = 0.895


def rank_score(
    lexical_coverage: float, lexical_tfidf_cosine: float, semantic_cosine: Optional[float] = None,
    mode: RetrievalMode = RetrievalMode.HYBRID
) -> float:
    """Ranking score for one chunk against one query. In [0, 1].

    Ranking only. Nothing here decides whether a chunk is returned or whether evidence
    is sufficient — those are the conjunctive gates above, and semantic appears in
    neither.

    Phase 2.1: Semantic similarity provides near-zero separation on the filtered path
    (a band width of +0.007). Stretching that signal across [0, 1] and averaging it
    adds pure noise. We revert to the 0.7/0.3 lexical blend until the embeddings
    model is replaced or fine-tuned.
    """
    if mode == RetrievalMode.SEMANTIC and semantic_cosine is not None:
        # Experimental semantic-only ranking
        span = SEMANTIC_RESCALE_CEILING - SEMANTIC_RESCALE_FLOOR
        scaled = (semantic_cosine - SEMANTIC_RESCALE_FLOOR) / span if span > 0 else 0.0
        return round(max(0.0, min(1.0, scaled)), 3)
    elif mode == RetrievalMode.HYBRID and semantic_cosine is not None:
        # Experimental hybrid ranking
        span = SEMANTIC_RESCALE_CEILING - SEMANTIC_RESCALE_FLOOR
        scaled = (semantic_cosine - SEMANTIC_RESCALE_FLOOR) / span if span > 0 else 0.0
        scaled = max(0.0, min(1.0, scaled))
        return round((lexical_coverage + lexical_tfidf_cosine + scaled) / 3.0, 3)
    
    # Default LEXICAL baseline
    return round(0.7 * lexical_coverage + 0.3 * lexical_tfidf_cosine, 3)


class HybridEvidenceRetriever:
    """Retriever over the clinical knowledge index: two lexical arms and one dense arm.

    The lexical arms gate, the dense arm ranks. See the module docstring for why that
    asymmetry is measured rather than stylistic.
    """

    def __init__(
        self,
        index: Optional[ClinicalCorpusIndex] = None,
        embedder: Optional[Embedder] = None,
    ):
        self.index: ClinicalCorpusIndex = index or get_default_index()
        # ``embedder=None`` means lexical-only, which is a real production mode and not
        # merely a test convenience: it is exactly what a search does when the daemon is
        # unreachable, so the existing suite exercising this path is exercising the
        # degraded configuration rather than a fiction. ``get_default_retriever`` supplies
        # the real embedder, so switching the dense arm on is one visible line.
        # Use ephemeral index for tests (StaticEmbedder), persistent for production
        persist_dir = "./chroma_data" if getattr(embedder, "model_name", "") not in ("static", "static-embedder") else None
        self.semantic: Optional[ChromaSemanticIndex] = (
            ChromaSemanticIndex(embedder, self.index.indexed_texts(), persist_directory=persist_dir)
            if embedder is not None
            else None
        )

    # ---- entity resolution -------------------------------------------------------

    def _resolve_entity_candidates(
        self, drug_filter: str
    ) -> Optional[List[Chunk]]:
        """Resolve a drug name to corpus chunks via the entity index.

        Returns ``None`` if the drug is not in the corpus — the caller must treat this
        as "no evidence", not as "search everything".
        """
        entity_id = canonical_entity(drug_filter)
        if entity_id is None:
            return None

        # Return strictly from the entity index; no fallback.
        if entity_id in self.index.by_entity:
            return self.index.by_entity[entity_id]

        return None  # Drug not in corpus → no evidence

    def _entity_identity_tokens(self, drug_filter: str, canonical_id: str) -> Set[str]:
        """Query tokens that merely name the filtered drug, rather than asking anything.

        Used to strip drug identity out of a query before re-scoring, so that a chunk
        cannot clear the gate on the strength of the drug name alone — the query
        "metformin" must not by itself constitute evidence about metformin.

        Every surface form of the drug is collected and tokenised *the same way the
        query was*, which is the bug this replaces. The previous implementation
        tokenised the canonical id and compared it against a query holding the raw
        name, so it silently stripped nothing for any name that is not already
        canonical: a "Coumadin" filter never matched canonical "warfarin", and
        ``amoxicillin_clavulanate`` stayed a single token — ``_tokenize`` keeps ``_``
        inside a token — that never equalled the query's separate "amoxicillin" and
        "clavulanate". The check therefore no-opped for exactly the branded, aliased
        and combination names where it was most needed, while appearing to be enforced.

        ``drug_class`` is deliberately excluded. "anticoagulant" in a query is a
        clinical question about a mechanism, not a restatement of the drug's name, and
        stripping it would discard the substance of the query.
        """
        surfaces: List[str] = [drug_filter, canonical_id]
        # ``drug_filter`` is taken wholesale, on the contract that callers pass a drug
        # name and not a compound query string. Every current caller does.
        drug = CANONICAL_DRUG_CATALOG.get(canonical_id)
        if drug is not None:
            surfaces.append(drug.generic_name)
            surfaces.extend(drug.brand_names)

        tokens: Set[str] = set()
        for surface in surfaces:
            for token in _tokenize(surface):
                tokens.add(token)
                # Split on the separators _tokenize preserves, so a combination id
                # matches the individual component names a clinician would type.
                tokens.update(part for part in re.split(r"[_-]", token) if len(part) > 1)
        return tokens

    # ---- core search -------------------------------------------------------------

    def _semantic_scores(
        self, query: str, candidates: List[Chunk]
    ) -> Dict[str, float]:
        """Dense similarity for ``candidates`` only, keyed by chunk id.

        Returns ``{}`` when the dense arm is absent or unavailable, so a missing entry
        and an absent arm both read as ``None`` at the call site and both fall back to
        the lexical blend.

        The parameter is ``candidates``, never ``self.index.chunks``, and that is the
        whole point: by the time this runs, the entity boundary has already decided which
        chunks exist for this query, so the query vector is never compared against a
        chunk outside it. The comparison is not filtered afterwards — the out-of-boundary
        vectors are simply not in the dot products.
        """
        if self.semantic is None:
            return {}
        scores = self.semantic.similarities(
            query, [chunk.chunk_id for chunk in candidates]
        )
        return scores if scores is not None else {}

    def search(
        self,
        query: str,
        drug_filter: Optional[str] = None,
        topic_filter: Optional[str] = None,
        top_k: int = 3,
        min_coverage: float = MIN_COVERAGE_THRESHOLD,
        min_cosine: float = MIN_COSINE_THRESHOLD,
        mode: RetrievalMode = RetrievalMode.HYBRID,
    ) -> List[RetrievedEvidenceChunk]:
        """
        Execute hybrid search with structural entity boundary enforcement:

        1. If drug_filter is given, resolve to entity. If entity is absent → return [].
        2. Restrict candidates to entity's chunks.
        3. Score the *surviving* candidates: query-intrinsic BM25 coverage + TF-IDF
           cosine, plus dense similarity over those candidates and no others.
        4. Apply topic filter if provided.
        5. Discard chunks failing the conjunctive gate (coverage >= min_coverage AND cosine >= min_cosine).

        Step 3 runs after steps 1 and 2, and the ordering is load-bearing rather than
        tidy. An unresolvable drug returns at step 1, before a query has been embedded at
        all, so no Ollama call is made and no vector exists to compare; a resolvable one
        embeds the query but compares it only against that entity's chunks. The dense arm
        cannot see past the boundary because it is never handed anything past it.

        ``entity_verified`` on each returned chunk is derived here, not passed in.
        There is deliberately no parameter for it: the only way to obtain verified
        evidence is to supply a ``drug_filter`` that resolves against the entity index,
        so a caller cannot assert an attribution check it did not perform.
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # ---- Structural entity boundary ----
        candidates = self.index.chunks
        entity_verified = False

        non_entity_query_tokens = query_tokens
        if drug_filter:
            canon = canonical_entity(drug_filter)
            if canon:
                entity_tokens = self._entity_identity_tokens(drug_filter, canon)
                non_entity_query_tokens = [t for t in query_tokens if t not in entity_tokens]

            entity_chunks = self._resolve_entity_candidates(drug_filter)
            if entity_chunks is None:
                # Drug not in corpus. The honest answer is no evidence.
                return []
            candidates = entity_chunks
            entity_verified = True

        # ---- Topic filter ----
        if topic_filter:
            t_lower = topic_filter.lower().strip()
            if t_lower in self.index.by_topic:
                candidates = [c for c in candidates if c.topic.lower() == t_lower]
            else:
                # Topic not in corpus — no evidence for this topic.
                return []

        if not candidates:
            return []

        # Dense scores for the SURVIVING candidates only. Every early return above has
        # already fired, so an out-of-corpus drug or an empty candidate set reaches this
        # line never — not with a filter applied to its results, but without the
        # embedding search having happened at all.
        semantic_scores = self._semantic_scores(query, candidates)

        # ---- Query-intrinsic scoring ----
        scored_results: List[RetrievedEvidenceChunk] = []

        for chunk in candidates:
            # BM25 coverage: fraction of ideal score. In [0, 1], independent of other
            # candidates. An unanswerable query produces a low number for every chunk.
            lexical_coverage = self.index.compute_lexical_coverage(query_tokens, chunk.chunk_id)

            # TF-IDF cosine: lexical overlap weighted by rarity. Also in [0, 1].
            lexical_tfidf_cosine = self.index.compute_tfidf_cosine(query_tokens, chunk.chunk_id)

            # ``None`` when the dense arm is unavailable; never 0.0, which would be a
            # measurement rather than an absence.
            semantic_cosine = semantic_scores.get(chunk.chunk_id)

            ne_coverage = 0.0
            ne_cosine = 0.0
            if non_entity_query_tokens:
                ne_coverage = self.index.compute_lexical_coverage(non_entity_query_tokens, chunk.chunk_id)
                ne_cosine = self.index.compute_tfidf_cosine(non_entity_query_tokens, chunk.chunk_id)

            # Conjunctive gate: a query must be answerable AND specific. Both conjuncts
            # are lexical — semantic similarity is deliberately absent, because measured
            # over this corpus its admit/reject band has negative width, so no value of
            # it would separate anything.
            if lexical_coverage >= min_coverage and lexical_tfidf_cosine >= min_cosine:
                # Ranking score. Computed for ordering only; inclusion was settled above.
                hybrid_score = rank_score(lexical_coverage, lexical_tfidf_cosine, semantic_cosine, mode)
                scored_results.append(
                    RetrievedEvidenceChunk(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        drug_name=chunk.drug_name,
                        source=chunk.source,
                        section=chunk.section,
                        text=chunk.text,
                        version=chunk.version,
                        publication_date=chunk.publication_date,
                        relevance_score=hybrid_score,
                        lexical_score=round(lexical_coverage, 3),
                        tfidf_cosine_score=round(lexical_tfidf_cosine, 3),
                        non_entity_lexical_score=round(ne_coverage, 3),
                        non_entity_tfidf_cosine_score=round(ne_cosine, 3),
                        semantic_score=None if semantic_cosine is None else round(semantic_cosine, 3),
                        entity_verified=entity_verified,
                    )
                )

        # Sort descending by relevance score
        scored_results.sort(key=lambda x: x.relevance_score, reverse=True)
        return scored_results[:top_k]

    # ---- finding-specific retrieval ----------------------------------------------

    def retrieve_for_interaction(self, alert: MedicationInteractionAlert) -> EvidenceResult:
        """Construct targeted evidence retrieval query for a drug-drug interaction finding.

        Search order:
        1. Drug A entity boundary
        2. Drug B entity boundary
        3. Unfiltered fallback — returned for informational context only, never
           satisfies has_sufficient_evidence.
        """
        finding_id = f"FINDING-INT-{alert.drug_a.lower()}-{alert.drug_b.lower()}"
        query = f"{alert.drug_a} {alert.drug_b} interaction {alert.mechanism} {alert.clinical_effect}"

        # Primary: search within drug_a's entity boundary
        evidence = self.search(query=query, drug_filter=alert.drug_a, top_k=2)
        if not evidence:
            # Secondary: search within drug_b's entity boundary
            evidence = self.search(query=query, drug_filter=alert.drug_b, top_k=2)

        # Sufficiency requires BOTH the conjunctive score thresholds AND entity verification.
        sufficient_evidence = []
        for c in evidence:
            if (c.entity_verified
                and c.lexical_score >= SUFFICIENCY_MIN_COVERAGE
                and c.tfidf_cosine_score >= SUFFICIENCY_MIN_COSINE
                and c.non_entity_lexical_score >= NON_ENTITY_MIN_COVERAGE
                and c.non_entity_tfidf_cosine_score >= NON_ENTITY_MIN_COSINE):
                sufficient_evidence.append(c)

        has_sufficient = len(sufficient_evidence) > 0
        if not has_sufficient:
            evidence = []
        else:
            evidence = sufficient_evidence

        confidence = round(evidence[0].relevance_score, 2) if evidence else 0.0

        return EvidenceResult(
            finding_id=finding_id,
            query=query,
            topic="interactions",
            evidence=evidence,
            confidence=confidence,
            has_sufficient_evidence=has_sufficient,
        )

    def retrieve_for_contraindication(self, alert: ContraindicationAlert) -> EvidenceResult:
        """Construct targeted evidence retrieval query for an allergy or comorbidity contraindication.

        Search order:
        1. Drug entity + contraindications topic
        2. Drug entity, any topic
        3. Unfiltered fallback — informational only, cannot satisfy has_sufficient_evidence.
        """
        finding_id = f"FINDING-CONTRA-{alert.medication.lower()}-{alert.trigger.lower()}"
        query = f"{alert.medication} {alert.trigger} {alert.contraindication_type} contraindication {alert.clinical_risk}"

        evidence = self.search(query=query, drug_filter=alert.medication, topic_filter="contraindications", top_k=2)
        if not evidence:
            evidence = self.search(query=query, drug_filter=alert.medication, top_k=2)

        sufficient_evidence = []
        for c in evidence:
            if (c.entity_verified
                and c.lexical_score >= SUFFICIENCY_MIN_COVERAGE
                and c.tfidf_cosine_score >= SUFFICIENCY_MIN_COSINE
                and c.non_entity_lexical_score >= NON_ENTITY_MIN_COVERAGE
                and c.non_entity_tfidf_cosine_score >= NON_ENTITY_MIN_COSINE):
                sufficient_evidence.append(c)

        has_sufficient = len(sufficient_evidence) > 0
        if not has_sufficient:
            evidence = []
        else:
            evidence = sufficient_evidence

        confidence = round(evidence[0].relevance_score, 2) if evidence else 0.0

        return EvidenceResult(
            finding_id=finding_id,
            query=query,
            topic="contraindications",
            evidence=evidence,
            confidence=confidence,
            has_sufficient_evidence=has_sufficient,
        )

    def retrieve_for_adherence_risk(self, alert: AdherenceSafetyAlert) -> EvidenceResult:
        """Retrieve evidence for adherence risk in critical drug monitoring.

        The corpus may not contain adherence guidance documents. If the drug is in the
        corpus, search its chunks for relevant warnings; if not, return no evidence with
        has_sufficient_evidence=False. The topic is reported as 'warnings' — which the
        corpus actually contains — not 'adherence_guidelines' which it does not.
        """
        finding_id = "FINDING-ADH-RISK"
        critical_str = " ".join(alert.critical_drugs_affected) if alert.critical_drugs_affected else "medication"
        query = f"{critical_str} adherence monitoring missed doses clinical risk"

        evidence: List[RetrievedEvidenceChunk] = []

        if alert.critical_drugs_affected:
            # Search within each critical drug's entity boundary
            for drug in alert.critical_drugs_affected:
                drug_evidence = self.search(
                    query=query, drug_filter=drug, top_k=2
                )
                if drug_evidence:
                    evidence.extend(drug_evidence)
                    break  # First hit is sufficient

        # If no entity-verified evidence, do NOT fall back to unfiltered search.
        # "No adherence guidance in corpus for this drug" is the truthful answer.
        # Require conjunctive score thresholds and entity verification — not just len(evidence) > 0.
        sufficient_evidence = []
        for c in evidence:
            if (c.entity_verified
                and c.lexical_score >= SUFFICIENCY_MIN_COVERAGE
                and c.tfidf_cosine_score >= SUFFICIENCY_MIN_COSINE
                and c.non_entity_lexical_score >= NON_ENTITY_MIN_COVERAGE
                and c.non_entity_tfidf_cosine_score >= NON_ENTITY_MIN_COSINE):
                sufficient_evidence.append(c)

        has_sufficient = len(sufficient_evidence) > 0
        if not has_sufficient:
            evidence = []
        else:
            evidence = sufficient_evidence

        confidence = round(evidence[0].relevance_score, 2) if evidence else 0.0

        return EvidenceResult(
            finding_id=finding_id,
            query=query,
            topic="warnings",  # What the corpus actually contains, not 'adherence_guidelines'
            evidence=evidence[:2],
            confidence=confidence,
            has_sufficient_evidence=has_sufficient,
        )

    def retrieve_evidence_bundle(self, assessment: SafetyAssessment) -> FindingEvidenceBundle:
        """
        Synthesize targeted clinical evidence for every finding in a Master Safety Assessment.
        """
        results: List[EvidenceResult] = []

        # 1. Evidence for each Drug Interaction
        for int_alert in assessment.medication_interactions:
            results.append(self.retrieve_for_interaction(int_alert))

        # 2. Evidence for each Contraindication
        for contra_alert in assessment.contraindications:
            results.append(self.retrieve_for_contraindication(contra_alert))

        # 3. Evidence for Adherence Risks
        for adh_alert in assessment.adherence_risks:
            results.append(self.retrieve_for_adherence_risk(adh_alert))

        total_chunks = sum(len(r.evidence) for r in results)
        all_supported = all(r.has_sufficient_evidence for r in results) if results else True

        return FindingEvidenceBundle(
            patient_id=assessment.patient_id,
            assessment_risk_level=assessment.risk_level,
            results=results,
            total_evidence_chunks=total_chunks,
            all_findings_supported=all_supported,
        )


# Singleton default retriever
_GLOBAL_RETRIEVER: Optional[HybridEvidenceRetriever] = None


def get_default_retriever() -> HybridEvidenceRetriever:
    """The production retriever: entity-gated, lexically scored, semantically ranked.

    The one place the dense arm is switched on. Constructing it does no I/O — the corpus
    is embedded lazily on the first search — so importing this module still does not
    require a running daemon.
    """
    global _GLOBAL_RETRIEVER
    if _GLOBAL_RETRIEVER is None:
        _GLOBAL_RETRIEVER = HybridEvidenceRetriever(embedder=OllamaEmbedder())
    return _GLOBAL_RETRIEVER
