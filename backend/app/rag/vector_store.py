import logging
import time
from typing import Dict, List, Optional, Sequence, Tuple
from app.rag.embeddings import Embedder, _RETRY_AFTER_SECONDS, _dot

logger = logging.getLogger(__name__)

class ChromaSemanticIndex:
    """Dense vectors for a fixed set of documents, built once and persisted via ChromaDB.

    Replaces the in-memory SemanticIndex. Automatically initializes and builds the
    index upon first use if it is missing, avoiding re-embedding on every start.
    """
    def __init__(
        self,
        embedder: Embedder,
        documents: Sequence[Tuple[str, str]],
        persist_directory: str = "./chroma_data",
        *,
        retry_after: float = _RETRY_AFTER_SECONDS,
    ) -> None:
        self._embedder = embedder
        self._documents: List[Tuple[str, str]] = list(documents)
        self._persist_directory = persist_directory
        self._retry_after = retry_after
        
        self._dim: Optional[int] = None
        self._failed_at: Optional[float] = None
        self._query_cache: Dict[str, List[float]] = {}
        
        self._client = None
        self._collection = None
        self._memory_fallback = None

    @property
    def model_name(self) -> str:
        return getattr(self._embedder, "model_name", type(self._embedder).__name__)

    def _in_cooldown(self) -> bool:
        if self._failed_at is None:
            return False
        return (time.monotonic() - self._failed_at) < self._retry_after

    def _note_failure(self) -> None:
        self._failed_at = time.monotonic()

    def _init_chroma(self) -> bool:
        if self._collection is not None:
            return True
        if self._in_cooldown():
            return False

        try:
            import chromadb
            
            import uuid
            
            if self._persist_directory is None:
                self._client = chromadb.Client()
                collection_name = f"clinical_corpus_{uuid.uuid4().hex}"
            else:
                self._client = chromadb.PersistentClient(path=self._persist_directory)
                collection_name = "clinical_corpus"
                
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            existing_count = self._collection.count()
            if existing_count < len(self._documents):
                texts = [text for _, text in self._documents]
                ids = [chunk_id for chunk_id, _ in self._documents]
                
                embedded = self._embedder.embed_documents(texts)
                if embedded is None or len(embedded) != len(self._documents):
                    self._note_failure()
                    self._collection = None
                    return False
                    
                dims = {len(v) for v in embedded}
                if len(dims) != 1:
                    logger.warning(
                        "Embedding model %r returned vectors of differing dimension (%s); "
                        "semantic ranking stays off.",
                        self.model_name,
                        sorted(dims),
                    )
                    self._note_failure()
                    self._collection = None
                    return False
                
                self._dim = dims.pop()
                self._collection.upsert(
                    ids=ids,
                    embeddings=embedded,
                    documents=texts
                )
            else:
                result = self._collection.get(limit=1, include=["embeddings"])
                if result and result.get("embeddings") is not None and len(result["embeddings"]) > 0:
                    self._dim = len(result["embeddings"][0])
            
            self._failed_at = None
            return True
        except Exception as exc:
            logger.warning("ChromaDB initialization failed: %s", exc)
            self._note_failure()
            self._collection = None
            return False

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

        if len(self._query_cache) >= 256:
            self._query_cache.clear()
        self._query_cache[query] = vector
        return vector

    def similarities(
        self, query: str, chunk_ids: Sequence[str]
    ) -> Optional[Dict[str, float]]:
        ids = list(chunk_ids)
        if not ids:
            return {}

        if not self._init_chroma():
            if self._memory_fallback is None:
                from app.rag.embeddings import SemanticIndex
                self._memory_fallback = SemanticIndex(self._embedder, self._documents)
            return self._memory_fallback.similarities(query, ids)
            
        try:
            result = self._collection.get(ids=ids, include=["embeddings"])
            if not result or result.get("embeddings") is None or len(result["ids"]) != len(ids):
                missing = [c for c in ids if not result or c not in result.get("ids", [])]
                logger.warning(
                    "Semantic index missing vectors for %s; falling back to in-memory ranking.",
                    missing,
                )
                if self._memory_fallback is None:
                    from app.rag.embeddings import SemanticIndex
                    self._memory_fallback = SemanticIndex(self._embedder, self._documents)
                return self._memory_fallback.similarities(query, ids)
                
            vectors = {id_: emb for id_, emb in zip(result["ids"], result["embeddings"])}
            query_vector = self._query_vector(query)
            if query_vector is None:
                return None
            if self._dim is not None and len(query_vector) != self._dim:
                logger.warning(
                    "Query vector dimension mismatch; semantic ranking skipped."
                )
                return None
                
            return {chunk_id: _dot(query_vector, vectors[chunk_id]) for chunk_id in ids}
        except Exception as exc:
            logger.warning("Failed to fetch vectors from ChromaDB, falling back to in-memory: %s", exc)
            if self._memory_fallback is None:
                from app.rag.embeddings import SemanticIndex
                self._memory_fallback = SemanticIndex(self._embedder, self._documents)
            return self._memory_fallback.similarities(query, ids)
