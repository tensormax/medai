"""
Document ingestion services (Feature B, step 1).

Pipeline for an uploaded document:

    file -> extract_text -> chunk_text -> embed (all-MiniLM-L6-v2)
         -> FAISS vector store + DocumentChunk rows

After ingestion a document is fully "RAG-ready": every chunk has a row in
the DB (for citation/traceability) and a vector in the FAISS store keyed
by the chunk's pk. `search_chunks` proves retrieval works end-to-end;
the LLM generation step on top of it lands in the next iteration.

Query-scoping helpers mirror apps/patients/services.py so every view can
guarantee a doctor only ever touches their own patients' documents.
"""

import re

from django.db import transaction
from django.shortcuts import get_object_or_404

from apps.accounts.models import Doctor
from apps.patients.models import Patient

from . import rag
from .models import Document, DocumentChunk


class IngestionError(Exception):
    """Raised when an uploaded file cannot be turned into text chunks."""


# ── Scoped queries (same pattern as apps.patients.services) ───────────


def get_documents_for(doctor: Doctor, patient: Patient | None = None):
    qs = Document.objects.filter(patient__doctor=doctor)
    if patient is not None:
        qs = qs.filter(patient=patient)
    return qs.select_related("patient", "visit")


def get_document_or_404_for(doctor: Doctor, document_pk: int) -> Document:
    return get_object_or_404(
        Document.objects.select_related("patient", "visit"),
        pk=document_pk,
        patient__doctor=doctor,
    )


# ── Text extraction ────────────────────────────────────────────────────


def extract_text(file_obj, filename: str) -> str:
    """Extract plain text from an uploaded .pdf/.txt/.md file."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(file_obj)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except Exception as exc:  # corrupt / encrypted / not a real PDF
            raise IngestionError(f"Could not read PDF: {exc}") from exc
    if name.endswith((".txt", ".md")):
        raw = file_obj.read()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return raw
    raise IngestionError("Unsupported file type. Upload a PDF, TXT or MD file.")


# ── Chunking ───────────────────────────────────────────────────────────


def chunk_text(text: str, max_words: int = 180, overlap_words: int = 30) -> list[str]:
    """
    Split text into overlapping word-window chunks sized for
    all-MiniLM-L6-v2 (256-token input limit). Overlap keeps sentences
    that straddle a boundary retrievable from both sides.
    """
    words = re.sub(r"\s+", " ", text or "").strip().split(" ")
    words = [w for w in words if w]
    if not words:
        return []

    chunks = []
    step = max(max_words - overlap_words, 1)
    for start in range(0, len(words), step):
        window = words[start : start + max_words]
        if not window:
            break
        chunks.append(" ".join(window))
        if start + max_words >= len(words):
            break
    return chunks


# ── Ingestion pipeline ─────────────────────────────────────────────────


def ingest_document(document: Document) -> int:
    """
    Extract, chunk, embed and index `document.file`.
    Returns the number of chunks created. Raises IngestionError when the
    file yields no usable text (caller decides what to do with the row).
    """
    if not document.file:
        raise IngestionError("Document has no file attached.")

    document.file.open("rb")
    try:
        text = extract_text(document.file, document.file.name)
    finally:
        document.file.close()

    chunks = chunk_text(text)
    if not chunks:
        raise IngestionError(
            "No extractable text found in this file (is it a scanned image?)."
        )

    vectors = rag.embed_texts(chunks)

    with transaction.atomic():
        # Replace any previous chunks (idempotent re-ingestion).
        old_ids = list(document.chunks.values_list("pk", flat=True))
        if old_ids:
            document.chunks.all().delete()
            rag.vector_store.remove(old_ids)

        chunk_rows = DocumentChunk.objects.bulk_create(
            DocumentChunk(
                document=document,
                chunk_text=chunk,
                chunk_index=index,
                embedding_id="pending",
            )
            for index, chunk in enumerate(chunks)
        )
        for row in chunk_rows:
            row.embedding_id = f"faiss:{row.pk}"
        DocumentChunk.objects.bulk_update(chunk_rows, ["embedding_id"])

    rag.vector_store.add([row.pk for row in chunk_rows], vectors)
    return len(chunk_rows)


def delete_document(document: Document) -> None:
    """Delete a document plus its vectors and stored file."""
    chunk_ids = list(document.chunks.values_list("pk", flat=True))
    rag.vector_store.remove(chunk_ids)
    if document.file:
        document.file.delete(save=False)
    document.delete()


# ── Retrieval (proves the embeddings are queryable) ────────────────────


def search_chunks(doctor: Doctor, patient: Patient, query: str, top_k: int = 5):
    """
    Semantic search over one patient's ingested documents.
    Returns [{document_id, document_title, chunk_index, score, text}, ...].
    """
    query_vector = rag.embed_texts([query])[0]
    # Over-fetch, then filter down to this doctor+patient in the DB —
    # the flat FAISS index itself has no metadata filtering.
    hits = rag.vector_store.search(query_vector, top_k=max(top_k * 10, 50))
    if not hits:
        return []

    scores = dict(hits)
    allowed = DocumentChunk.objects.filter(
        pk__in=list(scores),
        document__patient=patient,
        document__patient__doctor=doctor,
    ).select_related("document")

    rows = sorted(allowed, key=lambda c: scores[c.pk], reverse=True)[:top_k]
    return [
        {
            "chunk_id": row.pk,
            "document_id": row.document_id,
            "document_title": row.document.title or row.document.get_doc_type_display(),
            "chunk_index": row.chunk_index,
            "score": round(scores[row.pk], 4),
            "text": row.chunk_text,
        }
        for row in rows
    ]
