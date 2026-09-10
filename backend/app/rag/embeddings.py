"""
Dense (semantic) retrieval arm for the clinical corpus.

``nomic-embed-text`` (768-dim) served by the same local Ollama daemon that serves
generation, so nothing patient-adjacent leaves the host here either. This is the model
``app/core/config.py`` has declared since the start and nothing read.

What this module is allowed to decide
-------------------------------------
It ranks. It does not gate. Measured over all 10 chunks and all 51 ``eval_retrieval.py``
cases (re-measured 2026-08-28 against the rank-1 chunk the retriever actually selects),
this model yields a usable *ordering* and an unusable *magnitude*:

    sufficiency separation   must-pass min 0.772  vs  must-fail  max 0.766  -> band  0.007
    inclusion separation     must-include min 0.549  vs  must-exclude max 0.733
                                                                           -> band -0.184

A band under 0.01 is not a threshold, and a band of negative width is not a threshold at
any value — no cut separates "blood thinner" (0.549) from "adverse drug reaction"
(0.691). So semantic similarity appears in no gate: not the ``min_coverage`` /
``min_cosine`` inclusion gate, and not the four sufficiency conjuncts in ``retriever.py``.
It reorders a candidate set that the entity boundary and the lexical gates have already
decided, and it widens nothing.

``eval_retrieval.py`` reprints the sufficiency band on every run rather than trusting
this paragraph, so if a larger corpus ever opens the band to a width worth using, that
becomes visible where the decision would be made.

That restraint is also what makes degradation safe. Were semantic a sufficiency
conjunct, an Ollama hiccup would turn every finding into "no sufficient evidence" — the
safe-but-useless failure — and an outage would be indistinguishable from an empty
corpus. Confined to ranking, an outage costs ordering quality and nothing else.

Never a zero vector
-------------------
Every function here returns ``None`` when an embedding could not be obtained, never a
zero-filled vector of the right shape. A zero vector has similarity 0.0 against
everything, which is indistinguishable from "measured, and genuinely unrelated": the
caller would rank a chunk down on the strength of an infrastructure failure with no way
to tell. Same reasoning as ``entity_verified`` defaulting to ``False`` in
``retriever.py`` — an absent signal is safer than one that fails silently.

Callers must therefore test ``is None`` rather than truthiness. ``embed_documents([])``
returns ``[]``, because an empty corpus is not a failure, and the two must not collapse
into the same check.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


#: nomic-embed-text is trained with task prefixes, and the model card specifies these
#: two. The measured effect on this corpus is small but consistent and in the right
#: direction (the CLEAR warfarin query's rank-1 similarity rose 0.794 -> 0.833), so they
#: are applied as documented model usage rather than because the numbers demanded it.
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

#: Bound on the query-vector cache. Production queries are deterministic constructions
#: from alert fields, so a long-running process sees a small set of queries over and
#: over. Bounded because the key is caller-supplied text, and an unbounded dict keyed on
#: request input is a slow leak rather than a cache.
_QUERY_CACHE_MAX = 256

#: How long a failed corpus embedding stays failed before another attempt is made.
#: Both extremes are wrong. Retrying inside every request makes an outage cost a connect
#: timeout per search. Caching the failure for the life of the process means a daemon
#: that was merely slow to start silently disables semantic ranking until the next
#: deploy, with a single log line minutes earlier as the only trace.
_RETRY_AFTER_SECONDS = 60.0


class Embedder(Protocol):
    """Transport that turns text into unit-length vectors.

    Implementations return L2-normalised vectors, so a similarity is a plain dot product
    and no caller needs to know the model's scale. ``None`` from either method means
    "unavailable" and never "unrelated" — see the module docstring.
    """

    @property
    def model_name(self) -> str:
        """Identifies the embedding function for log messages.

        Nothing keys a cache on this, so it need not be globally unique; it exists so
        that a line reporting degraded ranking says *which* model went missing.
        """

    def embed_documents(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        """One vector per input text, in order, or ``None`` if unavailable."""

    def embed_query(self, text: str) -> Optional[List[float]]:
        """One vector for a search query, or ``None`` if unavailable."""


def _l2_normalise(vector: Sequence[float]) -> Optional[List[float]]:
    """Scale a vector to unit length, or ``None`` where that is not possible.

    A zero-norm vector cannot be normalised, and neither can one carrying a NaN or a
    non-numeric entry. Returning zeros in those cases would satisfy the type signature
    while silently asserting "unrelated to everything", so they are reported as
    unavailable instead.
    """
    try:
        norm = math.sqrt(sum(float(v) * float(v) for v in vector))
    except (TypeError, ValueError):
        return None
    if norm <= 0.0 or not math.isfinite(norm):
        return None
    return [float(v) / norm for v in vector]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product of two equal-length vectors. Callers check the lengths."""
    return sum(x * y for x, y in zip(a, b))


class OllamaEmbedder:
    """Sync embeddings transport for a local Ollama daemon.

    Deliberately separate from ``app/llm/client.py``. ``OllamaClient`` is the *async*
    generation transport; the retriever is sync from top to bottom and its one async
    caller offloads with ``anyio.to_thread``. One class serving both would have to serve
    two callers with opposite concurrency models, and the shared surface — a base URL —
    is not worth that.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.EMBEDDING_MODEL
        # Shorter than the generation timeout by a wide margin, but not because embedding
        # is quick. Measured on this box (CPU inference, warm daemon, 2026-08-28):
        #
        #     1 input     2.39s        10 inputs (whole corpus)    3.75s
        #     1 query     2.12s        repeated, five calls        2.12-2.16s
        #
        # So the cost is ~2.2s of fixed per-round-trip overhead and ~0.15s per additional
        # input. Two things follow. Batching is load-bearing rather than tidy: the corpus
        # costs 3.75s in one call against ~24s as ten. And a *distinct* query costs ~2.1s
        # on the request path, which is what makes the query cache below matter and what
        # makes the ``anyio.to_thread`` offload at the one async call site mandatory.
        #
        # 30s therefore leaves ~8x headroom over the corpus batch, not the 1000x an
        # earlier version of this comment implied by guessing "tens of milliseconds".
        # Anything near 30s still means wedged, but the margin is thinner than it looks,
        # and a slower host or a larger corpus should re-measure rather than assume.
        self.timeout = timeout

    @property
    def model_name(self) -> str:
        return self.model

    def embed_documents(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        return self._embed([DOCUMENT_PREFIX + t for t in texts])

    def embed_query(self, text: str) -> Optional[List[float]]:
        vectors = self._embed([QUERY_PREFIX + text])
        if vectors is None:
            return None
        # An empty query string is still one input, so one vector is expected back.
        return vectors[0] if vectors else None

    def _embed(self, inputs: Sequence[str]) -> Optional[List[List[float]]]:
        """One batched call to ``/api/embed``.

        Batched rather than one request per chunk: the whole corpus is 10 short strings,
        and ten sequential round trips would make a lazily-built index noticeably slower
        to warm for no benefit.
        """
        if not inputs:
            return []

        payload = {"model": self.model, "input": list(inputs)}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Embedding model %r at %s unavailable (%s); retrieval falls back to "
                "lexical ranking for this query.",
                self.model,
                self.base_url,
                exc,
            )
            return None

        raw = body.get("embeddings")
        if not isinstance(raw, list) or len(raw) != len(inputs):
            logger.warning(
                "Embedding model %r returned %s embeddings for %d inputs; discarding "
                "the batch rather than guessing which input each vector belongs to.",
                self.model,
                len(raw) if isinstance(raw, list) else type(raw).__name__,
                len(inputs),
            )
            return None

        vectors: List[List[float]] = []
        for vector in raw:
            normalised = _l2_normalise(vector) if isinstance(vector, list) else None
            if normalised is None:
                logger.warning(
                    "Embedding model %r returned a vector that cannot be normalised; "
                    "discarding the batch.",
                    self.model,
                )
                return None
            vectors.append(normalised)
        return vectors


class SemanticIndex:
    """Dense vectors for a fixed set of documents, built once and lazily.

    Lazy because construction happens at import time through
    ``retriever.get_default_retriever()``, and an HTTP call there would make module
    import depend on a running daemon. Once, because the corpus is immutable for the
    life of the object: the ``(chunk_id, text)`` pairs are captured at construction, so
    a corpus edit produces a new index and a new retriever rather than a stale cache
    that has to be invalidated.

    The ``similarities`` contract is the load-bearing part. It scores exactly the chunk
    ids it is handed and no others, which is what lets the retriever put the entity
    boundary *before* the embedding comparison instead of filtering after it.
    """

    def __init__(
        self,
        embedder: Embedder,
        documents: Sequence[Tuple[str, str]],
        *,
        retry_after: float = _RETRY_AFTER_SECONDS,
    ) -> None:
        self._embedder = embedder
        self._documents: List[Tuple[str, str]] = list(documents)
        self._retry_after = retry_after

        self._vectors: Optional[Dict[str, List[float]]] = None
        self._dim: Optional[int] = None
        self._failed_at: Optional[float] = None
        self._query_cache: Dict[str, List[float]] = {}

    @property
    def model_name(self) -> str:
        return getattr(self._embedder, "model_name", type(self._embedder).__name__)

    # -- availability ---------------------------------------------------------------

    def _in_cooldown(self) -> bool:
        if self._failed_at is None:
            return False
        return (time.monotonic() - self._failed_at) < self._retry_after

    def _note_failure(self) -> None:
        self._failed_at = time.monotonic()

    def _document_vectors(self) -> Optional[Dict[str, List[float]]]:
        """Corpus vectors, embedding them on first use. ``None`` while unavailable."""
        if self._vectors is not None:
            return self._vectors
        if self._in_cooldown():
            return None

        texts = [text for _, text in self._documents]
        embedded = self._embedder.embed_documents(texts)
        if embedded is None or len(embedded) != len(self._documents):
            self._note_failure()
            return None

        dims = {len(v) for v in embedded}
        if len(dims) != 1:
            logger.warning(
                "Embedding model %r returned vectors of differing dimension (%s); "
                "semantic ranking stays off.",
                self.model_name,
                sorted(dims),
            )
            self._note_failure()
            return None

        self._dim = dims.pop()
        self._vectors = {
            chunk_id: vector
            for (chunk_id, _), vector in zip(self._documents, embedded)
        }
        self._failed_at = None
        return self._vectors

    def _query_vector(self, query: str) -> Optional[List[float]]:
        cached = self._query_cache.get(query)
        if cached is not None:
            return cached
        if self._in_cooldown():
            return None

        vector = self._embedder.embed_query(query)
        if vector is None:
            self._note_failure()
            return None

        if len(self._query_cache) >= _QUERY_CACHE_MAX:
            # Cleared wholesale rather than evicted one entry at a time. With a bound
            # this far above the number of distinct queries production generates, an
            # eviction policy would be tuning a code path that never runs.
            self._query_cache.clear()
        self._query_cache[query] = vector
        return vector

    # -- scoring ---------------------------------------------------------------------

    def similarities(
        self, query: str, chunk_ids: Sequence[str]
    ) -> Optional[Dict[str, float]]:
        """Cosine similarity of ``query`` against each id in ``chunk_ids``.

        Returns a mapping whose keys are exactly ``chunk_ids``, or ``None`` if semantic
        scoring is unavailable for this call. Nothing outside ``chunk_ids`` is ever
        compared against the query — the ids the caller passes are the entire universe
        of this comparison, which is how the entity boundary gates the dense arm
        structurally rather than filtering its output.

        All-or-nothing on purpose. A partial mapping would leave some chunks ranked on a
        three-signal blend and others on two, and scores produced by different formulas
        are not comparable: a chunk could out-rank another by being measured differently
        rather than by being a better answer. That is the ranking-side form of the
        query-relative denominator that the ``retriever.py`` scoring invariant forbids.
        """
        ids = list(chunk_ids)
        if not ids:
            return {}

        vectors = self._document_vectors()
        if vectors is None:
            return None

        missing = [chunk_id for chunk_id in ids if chunk_id not in vectors]
        if missing:
            # The lexical index and this one disagree about what the corpus holds, which
            # should be impossible while both are built from the same chunk list. Refuse
            # the whole query rather than score the subset that happens to line up.
            logger.warning(
                "Semantic index has no vector for %s; semantic ranking skipped for "
                "this query.",
                missing,
            )
            return None

        query_vector = self._query_vector(query)
        if query_vector is None:
            return None
        if self._dim is not None and len(query_vector) != self._dim:
            logger.warning(
                "Query vector has dimension %d against document dimension %d; "
                "semantic ranking skipped for this query.",
                len(query_vector),
                self._dim,
            )
            return None

        return {chunk_id: _dot(query_vector, vectors[chunk_id]) for chunk_id in ids}


class StaticEmbedder:
    """Deterministic test double. No I/O, no daemon, no network.

    Similarity is a function of the *document* alone: a document whose text contains one
    of the given markers takes that marker's similarity, and anything unmatched takes
    ``default``. The query text is ignored. That is enough to exercise ranking
    arithmetic, boundary containment and the degradation path, which is all this is for
    — reproducing what the real model *means* by a query is the live test's job.

    The construction is exact rather than approximate. With the query at ``[1, 0]`` and a
    document at ``[s, sqrt(1 - s^2)]``, both are unit vectors and their dot product is
    exactly ``s``, so a test can state the similarity it wants to rank against and get
    that number back rather than something near it.
    """

    def __init__(
        self,
        similarity_by_marker: Optional[Dict[str, float]] = None,
        *,
        default: float = 0.0,
        unavailable: bool = False,
        name: str = "static-embedder",
    ) -> None:
        self._markers = dict(similarity_by_marker or {})
        self._default = default
        #: When set, both methods return ``None``, standing in for an unreachable daemon.
        self.unavailable = unavailable
        self._name = name

        #: Every call is counted so a test can assert that no embedding happened at all
        #: outside the entity boundary. Absence of a call is the assertion that matters,
        #: and it cannot be made without a counter.
        self.document_calls = 0
        self.query_calls = 0
        self.embedded_texts: List[str] = []
        self.embedded_queries: List[str] = []

    @property
    def model_name(self) -> str:
        return self._name

    def similarity_for(self, text: str) -> float:
        lowered = text.lower()
        for marker, score in self._markers.items():
            if marker.lower() in lowered:
                return score
        return self._default

    def embed_documents(self, texts: Sequence[str]) -> Optional[List[List[float]]]:
        self.document_calls += 1
        self.embedded_texts.extend(texts)
        if self.unavailable:
            return None
        return [self._vector_for(self.similarity_for(t)) for t in texts]

    def embed_query(self, text: str) -> Optional[List[float]]:
        self.query_calls += 1
        self.embedded_queries.append(text)
        if self.unavailable:
            return None
        return [1.0, 0.0]

    @staticmethod
    def _vector_for(similarity: float) -> List[float]:
        s = max(-1.0, min(1.0, similarity))
        return [s, math.sqrt(max(0.0, 1.0 - s * s))]
