from apps.ai.facade import AIOrchestrator

from .models import Document, DocumentAnalysis, DocumentChunk


class UploadProcessingError(Exception):
    """Raised when an uploaded file cannot be turned into indexed chunks."""


def get_document_or_404_for(doctor, document_pk: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Document, patient__doctor=doctor, pk=document_pk)


def get_document_analysis_or_404_for(doctor, analysis_pk: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        DocumentAnalysis, document__patient__doctor=doctor, pk=analysis_pk
    )


def extract_text(document: Document) -> str:
    """Extract plain text from an uploaded .txt or .pdf file."""
    name = (document.file.name or "").lower()
    document.file.seek(0)
    raw = document.file.read()
    if name.endswith(".pdf"):
        from apps.ai.chunking import extract_text as pdf_extract_text

        return pdf_extract_text(raw)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def process_upload(document: Document) -> None:
    """
    Full ingestion pipeline:
    extract pages → de-identify → detect structure → chunk → save.

    De-identification happens BEFORE chunking so the vector store
    contains only de-identified text. The original PDF and patient
    record remain unchanged.
    """
    from apps.ai.chunking import (
        ChunkingError,
        PageText,
        PDFExtractionError,
        chunk_document,
        extract_pages,
    )
    from apps.ai.deidentify import deidentify

    raw = document.file.read()

    # Determine extraction strategy based on file type
    name = (document.file.name or "").lower()
    if name.endswith(".pdf"):
        try:
            pages = extract_pages(raw)
        except PDFExtractionError as exc:
            document.processing_status = "failed"
            document.save(update_fields=["processing_status"])
            raise UploadProcessingError(
                f"PDF_EXTRACTION_FAILED: {exc}"
            ) from exc
    elif name.endswith(".txt"):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
        pages = [PageText(page_number=1, text=text)]
    else:
        raise UploadProcessingError(
            f"Unsupported file type: {name}"
        )

    if not pages or not any(p.text.strip() for p in pages):
        document.processing_status = "failed"
        document.save(update_fields=["processing_status"])
        raise UploadProcessingError(
            "PDF_EXTRACTION_FAILED: The uploaded file contained no extractable text."
        )

    # Mark document as processing
    document.processing_status = "processing"
    document.save(update_fields=["processing_status"])

    # De-identify each page's text before chunking
    patient = document.patient
    deidentified_pages = [
        PageText(
            page_number=p.page_number,
            text=deidentify(p.text, patient),
        )
        for p in pages
    ]

    # Chunk the de-identified text
    try:
        chunk_results = chunk_document(deidentified_pages)
    except ChunkingError as exc:
        document.processing_status = "failed"
        document.save(update_fields=["processing_status"])
        raise UploadProcessingError(
            f"CHUNKING_FAILED: {exc}"
        ) from exc

    if not chunk_results:
        document.processing_status = "failed"
        document.save(update_fields=["processing_status"])
        raise UploadProcessingError(
            "CHUNKING_FAILED: No chunks could be produced from this file."
        )

    # Delete any existing chunks (reprocessing)
    document.chunks.all().delete()

    # Save chunks with metadata (all de-identified)
    chunk_texts = [chunk.text for chunk in chunk_results]
    created_chunks = DocumentChunk.objects.bulk_create(
        [
            DocumentChunk(
                document=document,
                patient=document.patient,
                chunk_text=text,
                embedding_id="",
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                section=chunk.section,
            )
            for chunk, text in zip(chunk_results, chunk_texts)
        ]
    )

    # Compute and store embeddings when enabled
    from django.conf import settings as dj_settings

    if dj_settings.RAG_EMBEDDINGS_ENABLED:
        from apps.ai.embeddings import EmbeddingUnavailableError, embed_chunks

        try:
            vectors = embed_chunks(chunk_texts)
            for chunk_obj, vector in zip(created_chunks, vectors):
                chunk_obj.embedding = vector
                chunk_obj.embedding_id = f"doc-{document.pk}-chunk-{chunk_obj.chunk_index}"
                chunk_obj.save(update_fields=["embedding", "embedding_id"])
        except EmbeddingUnavailableError:
            pass  # embeddings unavailable — chunks stored without vectors

    # Update document status
    document.de_identified = True
    document.chunk_count = len(chunk_results)
    document.processing_status = "completed"
    document.save(update_fields=["processing_status", "chunk_count", "de_identified"])


def get_or_create_analysis(document: Document, query=None):
    """
    Return an existing summary for a document, or run the LLM to create
    one. Recall, don't regenerate: an existing analysis means no second
    LLM call.
    """
    existing = (
        document.analyses.filter(analysis_type="summary")
        .order_by("-created_at")
        .first()
    )
    if existing:
        return existing, False
    result = AIOrchestrator.analyze_document(document, query)
    analysis = DocumentAnalysis.objects.create(
        document=document,
        analysis_type="summary",
        prompt_used=result["prompt_used"],
        llm_response_json=result["llm_response_json"],
    )
    return analysis, True
