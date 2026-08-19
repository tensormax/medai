"""
Local embeddings via sentence-transformers. No external API call — this
model runs on the machine, so testing is free and rate-limit-free.

When RAG_EMBEDDINGS_ENABLED
is False, or the dependency is missing, embed_chunks raises
EmbeddingUnavailableError and callers fall back to keyword retrieval.
"""

from django.conf import settings

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class EmbeddingUnavailableError(Exception):
    """Raised when local embeddings are disabled or the dependency is missing."""


def _get_model():
    if not settings.RAG_EMBEDDINGS_ENABLED:
        raise EmbeddingUnavailableError(
            "Local embeddings are disabled. Set RAG_EMBEDDINGS_ENABLED=True "
            "in settings and install sentence-transformers to enable "
            "semantic retrieval."
        )
    from django.apps import apps

    model = apps.get_app_config("ai").embedding_model
    if model is None:
        raise EmbeddingUnavailableError(
            "Embedding model not loaded. Ensure sentence-transformers is "
            "installed and RAG_EMBEDDINGS_ENABLED=True."
        )
    return model


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    return _get_model().encode(chunks).tolist()
