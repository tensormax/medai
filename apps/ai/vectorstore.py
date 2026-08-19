"""
Thin wrapper around pgvector via Django ORM.

No other module touches the embedding vector column directly — this is the
only place that upserts or queries vectors.  Embeddings for queries are
computed with the local model via apps.ai.embeddings.
"""

from django.conf import settings

from apps.ai.embeddings import EmbeddingUnavailableError, embed_chunks


def upsert(
    document_id: int,
    chunks: list[str],
    vectors: list[list[float]],
) -> list[str]:
    """
    Store chunk texts + vectors into DocumentChunk.embedding via pgvector.
    Returns placeholder ids (the chunk PKs) for traceability.
    """
    if not settings.RAG_EMBEDDINGS_ENABLED:
        raise EmbeddingUnavailableError(
            "The vector store is disabled. Set RAG_EMBEDDINGS_ENABLED=True "
            "in settings and install psycopg2-binary + django-pgvector."
        )

    from apps.documents.models import DocumentChunk

    chunk_ids = []
    for index, (text, vector) in enumerate(zip(chunks, vectors)):
        chunk, _created = DocumentChunk.objects.update_or_create(
            document_id=document_id,
            chunk_index=index,
            defaults={
                "chunk_text": text,
                "embedding": vector,
                "embedding_id": f"doc-{document_id}-chunk-{index}",
            },
        )
        chunk_ids.append(str(chunk.pk))
    return chunk_ids


def query(document_id: int, query_text: str, k: int) -> list[str]:
    """
    Return the top-k most similar chunk texts for a document using
    cosine distance (<=>) via pgvector.
    """
    return [r["chunk_text"] for r in query_with_scores(document_id, query_text, k)]


def query_with_scores(
    document_id: int, query_text: str, k: int
) -> list[dict]:
    """
    Return the top-k most similar chunks for a document using cosine
    distance via pgvector, including full metadata for each result.

    Each dict contains:
        chunk_text, chunk_index, page_number, section,
        document_id, patient_id, embedding_id, cosine_distance
    """
    if not settings.RAG_EMBEDDINGS_ENABLED:
        raise EmbeddingUnavailableError(
            "The vector store is disabled. Set RAG_EMBEDDINGS_ENABLED=True "
            "in settings and install psycopg2-binary + django-pgvector."
        )

    from pgvector.django import CosineDistance

    from apps.documents.models import DocumentChunk

    query_vector = embed_chunks([query_text])[0]

    results = (
        DocumentChunk.objects.filter(
            document_id=document_id,
            embedding__isnull=False,
        )
        .annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")
        .values(
            "chunk_text",
            "chunk_index",
            "page_number",
            "section",
            "document_id",
            "patient_id",
            "embedding_id",
            "distance",
        )[:k]
    )

    return [
        {
            "chunk_text": r["chunk_text"],
            "chunk_index": r["chunk_index"],
            "page_number": r["page_number"],
            "section": r["section"],
            "document_id": r["document_id"],
            "patient_id": r["patient_id"],
            "embedding_id": r["embedding_id"],
            "cosine_distance": float(r["distance"]),
        }
        for r in results
    ]


def query_patient_scoped(
    patient_id: int,
    query_text: str,
    k: int,
    document_id: int | None = None,
) -> list[dict]:
    """
    Patient-scoped retrieval across all (or one) document(s).
    Returns the same metadata format as query_with_scores.
    """
    if not settings.RAG_EMBEDDINGS_ENABLED:
        raise EmbeddingUnavailableError(
            "The vector store is disabled. Set RAG_EMBEDDINGS_ENABLED=True "
            "in settings and install psycopg2-binary + django-pgvector."
        )

    from pgvector.django import CosineDistance

    from apps.documents.models import DocumentChunk

    query_vector = embed_chunks([query_text])[0]

    qs = DocumentChunk.objects.filter(
        patient_id=patient_id,
        embedding__isnull=False,
    )
    if document_id is not None:
        qs = qs.filter(document_id=document_id)

    results = (
        qs.annotate(distance=CosineDistance("embedding", query_vector))
        .order_by("distance")
        .values(
            "chunk_text",
            "chunk_index",
            "page_number",
            "section",
            "document_id",
            "patient_id",
            "embedding_id",
            "distance",
        )[:k]
    )

    return [
        {
            "chunk_text": r["chunk_text"],
            "chunk_index": r["chunk_index"],
            "page_number": r["page_number"],
            "section": r["section"],
            "document_id": r["document_id"],
            "patient_id": r["patient_id"],
            "embedding_id": r["embedding_id"],
            "cosine_distance": float(r["distance"]),
        }
        for r in results
    ]
