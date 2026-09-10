"""
Clinical Corpus Indexer

Builds four indexes over the curated clinical corpus:

1. Entity index (``by_entity``) — canonical drug id -> chunks. This is the *safety*
   index: it is what lets a drug filter fail closed, and it is built from declared
   associations (``Chunk.related_drugs``), never from names scraped out of the prose.
2. Inverted term-frequency index for BM25 lexical scoring.
3. TF-IDF term-weight vectors for cosine ranking. These are sparse bag-of-words
   vectors, **not** embeddings. Two chunks that share no vocabulary score zero however
   close in meaning they are, and "blood thinner" retrieves no warfarin evidence
   because neither token is in the corpus vocabulary. Dense vectors now exist alongside
   these, in ``app/rag/embeddings.py``, and are built over the same text via
   ``indexed_texts``; the method names here still say ``tfidf`` rather than
   ``semantic`` because that is what they compute.
4. Metadata slicing indexes (by drug_name, topic).

Both scoring functions are **query-intrinsic**: the score of a chunk depends only on
that chunk and the query, never on what else happened to be retrieved. That property
is the point. A score normalised against the best result in the same batch measures
which candidate won a race, and reports a confident number even when every candidate
is irrelevant.
"""

import math
import re
from collections import Counter, defaultdict
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from app.rag.corpus import Chunk, build_corpus_chunks
from app.rules.drug_normalizer import normalize_drug

# BM25 free parameters. Standard defaults; k1 controls how fast term-frequency
# saturates, b how strongly document length is normalised.
BM25_K1 = 1.2
BM25_B = 0.75


# Medical/English common stopwords to suppress noise in BM25 scoring
STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "with",
    "by", "of", "from", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "can", "could", "should", "would",
    "may", "might", "must", "shall", "will", "this", "that", "these", "those",
    "it", "its", "as", "such", "than", "too", "very", "patient", "patients"
}


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    tokens = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def _distinct(tokens: Iterable[str]) -> List[str]:
    """Order-preserving de-duplication.

    BM25 is defined as a sum over the *distinct* terms of a query. Summing over a raw
    token list instead means "bleeding bleeding bleeding" scores three times
    "bleeding" — query-side amplification with no saturation, which is a way to inflate
    a score by repeating yourself.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def canonical_entity(term: str) -> Optional[str]:
    """Canonical drug id for a free-text term, or ``None`` if the term names nothing.

    ``normalize_drug`` never returns ``None``: an unrecognised name comes back as a
    synthesised ``CanonicalDrug`` so display code always has something to show. For a
    *filter* that shape is wrong — a synthesised id is exactly the input that must not
    be allowed to widen a search — so the caller checks the returned id against
    ``by_entity``, and an id that is not there retrieves nothing.

    Empty and whitespace-only terms return ``None`` meaning "unusable", not "no
    filter". Treating a blank string as "search everything" is the fail-open pattern
    this module exists to remove: ``if drug_filter:`` silently turned ``""`` into an
    unfiltered corpus-wide search.
    """
    if not term or not term.strip():
        return None
    return normalize_drug(term).canonical_id


class ClinicalCorpusIndex:
    """In-memory hybrid search index for the clinical evidence repository."""

    def __init__(self, chunks: Optional[List[Chunk]] = None):
        self.chunks: List[Chunk] = chunks or build_corpus_chunks()
        self.chunk_by_id: Dict[str, Chunk] = {c.chunk_id: c for c in self.chunks}

        # Slicing indexes
        self.by_drug: Dict[str, List[Chunk]] = defaultdict(list)
        self.by_topic: Dict[str, List[Chunk]] = defaultdict(list)

        # Entity index: canonical drug id -> chunks that are *about* that drug,
        # whether as the document's subject or as a declared associated entity.
        self.by_entity: Dict[str, List[Chunk]] = defaultdict(list)
        # Reverse view, for post-condition checks on a filtered result set.
        self.entities_of: Dict[str, FrozenSet[str]] = {}

        # token -> {chunk_id: raw occurrence count}
        self.term_freq: Dict[str, Dict[str, int]] = defaultdict(dict)
        self.doc_freq: Dict[str, int] = defaultdict(int)
        self.chunk_vectors: Dict[str, Dict[str, float]] = {}
        self.chunk_lengths: Dict[str, int] = {}
        self.avg_doc_len: float = 1.0

        self._build_index()

    # -- construction ---------------------------------------------------------------

    def _indexed_text(self, chunk: Chunk) -> str:
        return f"{chunk.drug_name} {chunk.drug_class} {chunk.section} {chunk.text}"

    def indexed_texts(self) -> List[Tuple[str, str]]:
        """``(chunk_id, indexed_text)`` for every chunk, in corpus order.

        Exists so the dense arm in ``app/rag/embeddings.py`` embeds the same string the
        sparse vectors were built from. Two arms reading different text would describe
        two different documents while claiming to rank one, and the discrepancy would
        surface only as unexplainable ranking — nothing would fail.
        """
        return [(chunk.chunk_id, self._indexed_text(chunk)) for chunk in self.chunks]

    def _build_index(self) -> None:
        total_len = 0
        total_docs = len(self.chunks)

        for chunk in self.chunks:
            self.by_drug[chunk.drug_name.lower()].append(chunk)
            self.by_topic[chunk.topic.lower()].append(chunk)

            entities = self._entities_for(chunk)
            self.entities_of[chunk.chunk_id] = entities
            for entity in entities:
                self.by_entity[entity].append(chunk)

            tokens = _tokenize(self._indexed_text(chunk))
            doc_len = len(tokens)
            self.chunk_lengths[chunk.chunk_id] = doc_len
            total_len += doc_len

            # Raw counts, not count/doc_len. BM25 does its own length normalisation
            # through b, so pre-dividing would apply it twice — and the previous
            # implementation then discarded the stored value and recomputed tf by
            # counting *postings*, of which there is exactly one per (term, chunk).
            # That made every term frequency 0 or 1: a chunk mentioning "bleeding"
            # five times ranked identically to one mentioning it once.
            for token, count in Counter(tokens).items():
                self.doc_freq[token] += 1
                self.term_freq[token][chunk.chunk_id] = count

        self.avg_doc_len = total_len / total_docs if total_docs > 0 else 1.0

        # TF-IDF vectors for cosine similarity
        for chunk in self.chunks:
            tokens = _tokenize(self._indexed_text(chunk))
            counts = Counter(tokens)
            vec: Dict[str, float] = {}
            for token, count in counts.items():
                idf = math.log((total_docs + 1) / (self.doc_freq[token] + 1)) + 1.0
                vec[token] = (count / len(tokens)) * idf

            norm = math.sqrt(sum(v * v for v in vec.values()))
            self.chunk_vectors[chunk.chunk_id] = (
                {k: v / norm for k, v in vec.items()} if norm > 0 else vec
            )

    def _entities_for(self, chunk: Chunk) -> FrozenSet[str]:
        """Canonical ids this chunk carries evidence about.

        The chunk's own drug only. Previously this included declared associations,
        which caused entity boundary leakage (e.g. a warfarin-ibuprofen interaction
        chunk was returned for ibuprofen contraindication queries).
        """
        ids = {normalize_drug(chunk.drug_name).canonical_id}
        return frozenset(ids)

    # -- scoring --------------------------------------------------------------------

    def _idf_at_df(self, df: int) -> float:
        n = len(self.chunks)
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def _idf(self, token: str) -> float:
        """BM25 inverse document frequency for an indexed term."""
        return self._idf_at_df(self.doc_freq.get(token, 0))

    def _unknown_term_idf(self) -> float:
        """Weight given to a query term that appears in no chunk.

        Out-of-vocabulary terms are never in the numerator — no document contains
        them — so this value governs only how much an unmatched term *dilutes* a
        score. That dilution is the mechanism that stops "clot prevention drug" from
        scoring well on a chunk that merely contains the word "drug".

        Set to the weight of the rarest indexed term rather than to the value the idf
        formula gives for df=0 (which on a 10-chunk corpus is ~3.09, higher than any
        real term scores). On a corpus this small there is no evidence that an unknown
        token is a meaningful clinical term at all — it may be "knee" or "please" —
        so treating it as strictly more informative than every genuine indexed term
        would penalise ordinary verbose questions far harder than it penalises
        irrelevant ones, which is the wrong way round.
        """
        return self._idf_at_df(1)

    def compute_lexical_score(self, query_tokens: Sequence[str], chunk_id: str) -> float:
        """Raw BM25 score. Unbounded above; comparable across chunks, not across queries."""
        doc_len = self.chunk_lengths.get(chunk_id, self.avg_doc_len)
        length_norm = BM25_K1 * (1 - BM25_B + BM25_B * (doc_len / self.avg_doc_len))

        score = 0.0
        for token in _distinct(query_tokens):
            freq = self.term_freq.get(token, {}).get(chunk_id, 0)
            if freq == 0:
                continue
            score += self._idf(token) * (freq * (BM25_K1 + 1)) / (freq + length_norm)
        return score

    def compute_lexical_coverage(
        self, query_tokens: Sequence[str], chunk_id: str
    ) -> float:
        """BM25 score as a fraction of what this query could have scored. In [0, 1].

        The denominator is the score a hypothetical chunk would earn by containing
        every query term once at average document length — ``idf * (k1+1)/(1+k1)``,
        which is ``idf * 1.0``. It depends only on the query, so two chunks scored for
        the same query are compared against the same yardstick, and a chunk's score
        does not move when a different chunk joins or leaves the candidate set.

        That is the difference from ``raw / max(raw for all candidates)``. A relative
        denominator guarantees some chunk scores 1.0 for *every* query, including
        queries the corpus cannot answer, so the top result always looks strong. Here
        an unanswerable query produces a low number for every chunk, which is what a
        threshold needs in order to mean anything.

        Every query term is in the denominator, including terms in no chunk — see
        ``_unknown_term_idf``. Clamped at 1.0 because a chunk that repeats a term can
        exceed the reference score.
        """
        distinct = _distinct(query_tokens)
        if not distinct:
            return 0.0

        ideal = sum(
            self._idf(t) if t in self.doc_freq else self._unknown_term_idf()
            for t in distinct
        )
        if ideal <= 0:
            return 0.0

        return min(1.0, self.compute_lexical_score(distinct, chunk_id) / ideal)

    def compute_tfidf_cosine(self, query_tokens: Sequence[str], chunk_id: str) -> float:
        """Cosine similarity between the TF-IDF query vector and the chunk vector.

        Lexical overlap weighted by rarity. Named for what it is: there is no
        embedding model behind this, so it cannot match a paraphrase that shares no
        words with the corpus.
        """
        total_docs = len(self.chunks)
        q_vec: Dict[str, float] = {}
        for token in _distinct(query_tokens):
            # Binary query weight. Repeating a term rotates the query vector rather
            # than scaling it, so counts here would let repetition change the ranking.
            idf = math.log((total_docs + 1) / (self.doc_freq.get(token, 0) + 1)) + 1.0
            q_vec[token] = idf

        q_norm = math.sqrt(sum(v * v for v in q_vec.values()))
        if q_norm == 0:
            return 0.0
        q_vec = {k: v / q_norm for k, v in q_vec.items()}

        doc_vec = self.chunk_vectors.get(chunk_id, {})
        cosine_sim = sum(w * doc_vec[t] for t, w in q_vec.items() if t in doc_vec)
        return max(0.0, min(1.0, cosine_sim))


# Singleton default index
_GLOBAL_INDEX: Optional[ClinicalCorpusIndex] = None


def get_default_index() -> ClinicalCorpusIndex:
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = ClinicalCorpusIndex()
    return _GLOBAL_INDEX
