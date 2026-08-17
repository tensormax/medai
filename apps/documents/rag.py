"""
RAG plumbing for the documents app.

Two responsibilities, kept deliberately small for the demo:

1. Embedding — a lazily-loaded singleton of the all-MiniLM-L6-v2
   sentence-transformer (384-dim). Loaded once per process, on first use,
   so `manage.py migrate` etc. never pay the model start-up cost.

2. Vector store — a persistent FAISS index on disk (settings.VECTOR_STORE_DIR).
   The database only stores pointers (`DocumentChunk.embedding_id`); the
   actual vectors live here. We use an IndexIDMap2 over an inner-product
   flat index with L2-normalised embeddings, i.e. cosine similarity, and
   we key every vector by the DocumentChunk primary key so DB rows and
   vectors can always be joined back together.

The generation side (LLM answering over retrieved chunks) is intentionally
NOT here yet — it arrives in the next iteration.
"""

import threading

import numpy as np
from django.conf import settings

_model = None
_model_lock = threading.Lock()


def get_embedder():
    """Return the process-wide SentenceTransformer, loading it on first use."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts):
    """
    Embed a list of strings -> float32 ndarray of shape (n, EMBEDDING_DIM).
    Embeddings are L2-normalised so inner product == cosine similarity.
    """
    vectors = get_embedder().encode(
        list(texts),
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype="float32")


class FaissStore:
    """Thin, thread-safe wrapper around a persistent FAISS index."""

    def __init__(self):
        self._lock = threading.Lock()
        self._index = None

    # -- internals ----------------------------------------------------

    @property
    def _index_path(self):
        return settings.VECTOR_STORE_DIR / "faiss.index"

    def _load(self):
        import faiss

        if self._index is None:
            settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
            if self._index_path.exists():
                self._index = faiss.read_index(str(self._index_path))
            else:
                base = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
                self._index = faiss.IndexIDMap2(base)
        return self._index

    def _persist(self):
        import faiss

        faiss.write_index(self._index, str(self._index_path))

    # -- public API ---------------------------------------------------

    def add(self, ids, vectors):
        """Add vectors keyed by DocumentChunk pks."""
        with self._lock:
            index = self._load()
            index.add_with_ids(
                np.asarray(vectors, dtype="float32"),
                np.asarray(ids, dtype="int64"),
            )
            self._persist()

    def remove(self, ids):
        """Remove vectors for the given DocumentChunk pks (e.g. on delete)."""
        if not ids:
            return
        import faiss

        with self._lock:
            index = self._load()
            selector = faiss.IDSelectorArray(np.asarray(ids, dtype="int64"))
            index.remove_ids(selector)
            self._persist()

    def search(self, vector, top_k=5):
        """Return [(chunk_pk, score), ...] best-first for a single query vector."""
        with self._lock:
            index = self._load()
            if index.ntotal == 0:
                return []
            top_k = min(top_k, index.ntotal)
            query = np.asarray([vector], dtype="float32")
            scores, ids = index.search(query, top_k)
        return [
            (int(chunk_id), float(score))
            for chunk_id, score in zip(ids[0], scores[0])
            if chunk_id != -1
        ]

    def count(self):
        with self._lock:
            return self._load().ntotal

    def reset(self):
        """Drop the in-memory index (used by tests to isolate state)."""
        with self._lock:
            self._index = None


vector_store = FaissStore()
