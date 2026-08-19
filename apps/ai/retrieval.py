"""
Feature B retrieval: turn a doctor's query into a compact context block
of the most relevant chunk texts for a document.

Uses semantic search over the vector store when embeddings are enabled;
falls back to simple keyword scoring over the saved chunks otherwise, so
analysis works even without sentence-transformers/chromadb installed.

When embeddings are enabled and a sufficient number of candidates are
retrieved, results are reranked with a CrossEncoder model for higher
precision.

Context assembly (Phase 7):
    After reranking, candidates are deduplicated, expanded with
    neighboring chunks for clinical continuity, and formatted as
    numbered source blocks for the LLM prompt.
"""

from django.conf import settings

from apps.ai.embeddings import EmbeddingUnavailableError
from apps.ai.vectorstore import query_with_scores

RAG_CANDIDATE_K = getattr(settings, "RAG_CANDIDATE_K", 20)
RAG_FINAL_K = getattr(settings, "RAG_FINAL_K", 5)
RAG_MAX_CONTEXT_CHARS = getattr(settings, "RAG_MAX_CONTEXT_CHARS", 6000)
RAG_EXPAND_NEIGHBORS = getattr(settings, "RAG_EXPAND_NEIGHBORS", True)
RAG_ANSWERABILITY_RERANK_THRESHOLD = getattr(
    settings, "RAG_ANSWERABILITY_RERANK_THRESHOLD", -15.0
)
RAG_ANSWERABILITY_COSINE_THRESHOLD = getattr(
    settings, "RAG_ANSWERABILITY_COSINE_THRESHOLD", 0.8
)


class RerankerUnavailableError(Exception):
    """Raised when the reranker model is not available."""


def _get_reranker():
    from django.apps import apps

    model = apps.get_app_config("ai").reranker_model
    if model is None:
        raise RerankerUnavailableError(
            "Reranker model not loaded. Ensure sentence-transformers is "
            "installed and RAG_EMBEDDINGS_ENABLED=True."
        )
    return model


def rerank(
    query: str, candidates: list[dict]
) -> list[dict]:
    """
    Rerank candidate chunks using a CrossEncoder model.

    Each candidate dict must contain at least a 'chunk_text' key.
    Appends 'reranker_score' to each candidate and returns them
    sorted by score descending.

    The raw score is a logit — higher means more relevant.
    """
    if not candidates:
        return []

    try:
        model = _get_reranker()
    except RerankerUnavailableError:
        return candidates

    pairs = [(query, c["chunk_text"]) for c in candidates]
    scores = model.predict(pairs)

    for candidate, score in zip(candidates, scores):
        candidate["reranker_score"] = float(score)

    return sorted(candidates, key=lambda c: c["reranker_score"], reverse=True)


# ── Keyword fallback ────────────────────────────────────────────────

def _fallback_chunks(document, query: str) -> list[str]:
    terms = [term.lower() for term in query.split() if term.strip()]
    scored = []
    for chunk in document.chunks.all():
        text = chunk.chunk_text.lower()
        score = sum(1 for term in terms if term in text)
        if score:
            scored.append((score, chunk.chunk_text))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in scored[:RAG_FINAL_K]]


# ── Context assembly (Phase 7) ─────────────────────────────────────

def _deduplicate(candidates: list[dict]) -> list[dict]:
    """Remove duplicate chunk texts, keeping the highest-ranked occurrence."""
    seen: set[str] = set()
    unique = []
    for c in candidates:
        text = c["chunk_text"].strip()
        if text not in seen:
            seen.add(text)
            unique.append(c)
    return unique


def _expand_neighbors(
    candidates: list[dict],
    all_chunks: list[dict] | None = None,
    document_id: int | None = None,
) -> list[dict]:
    """
    For each selected candidate, check if the adjacent chunk (chunk_index ± 1)
    from the same document would provide clinical continuity.

    If the neighbor exists in all_chunks but not already in candidates,
    insert it directly after the candidate.

    Returns a new list with neighbor chunks interleaved.
    """
    if not RAG_EXPAND_NEIGHBORS:
        return candidates

    if all_chunks is None and document_id is not None:
        from apps.documents.models import DocumentChunk
        all_chunks = list(
            DocumentChunk.objects.filter(document_id=document_id)
            .order_by("chunk_index")
            .values("chunk_index", "chunk_text", "page_number", "section")
        )

    if not all_chunks:
        return candidates

    index_map = {c["chunk_index"]: c for c in all_chunks}
    selected_indices = {c["chunk_index"] for c in candidates}

    expanded = []
    for c in candidates:
        expanded.append(c)
        idx = c["chunk_index"]

        for neighbor_idx in (idx - 1, idx + 1):
            if (
                neighbor_idx not in selected_indices
                and neighbor_idx in index_map
            ):
                neighbor = index_map[neighbor_idx]
                neighbor_text = neighbor["chunk_text"].strip()
                if neighbor_text and neighbor_text != c["chunk_text"].strip():
                    expanded.append({
                        "chunk_text": neighbor_text,
                        "chunk_index": neighbor_idx,
                        "page_number": neighbor.get("page_number"),
                        "section": neighbor.get("section", ""),
                        "document_id": document_id or c.get("document_id"),
                        "patient_id": c.get("patient_id"),
                        "embedding_id": "",
                        "cosine_distance": None,
                        "reranker_score": None,
                        "_expanded": True,
                    })
                    selected_indices.add(neighbor_idx)

    return expanded


def build_context(
    candidates: list[dict],
    document_id: int | None = None,
    max_chars: int | None = None,
) -> dict:
    """
    Assemble the final LLM context from reranked candidates.

    Steps:
        1. Deduplicate identical chunk texts
        2. Expand with neighbor chunks for clinical continuity
        3. Format as numbered [SOURCE N] blocks
        4. Bound total context length

    Returns a dict with:
        context_text: formatted string for LLM prompt
        sources: list of source dicts used in the context
        total_chars: total character count of the context
        pipeline: summary dict for development inspection
    """
    max_chars = max_chars or RAG_MAX_CONTEXT_CHARS

    # Step 1: deduplicate
    deduplicated = _deduplicate(candidates)

    # Step 2: expand neighbors
    expanded = _expand_neighbors(deduplicated, document_id=document_id)

    # Step 3: format and bound
    sources = []
    blocks = []
    total = 0

    source_num = 0
    for c in expanded:
        text = c["chunk_text"].strip()
        if not text:
            continue

        # Truncate individual chunk if needed
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining]

        source_num += 1
        page = c.get("page_number") or "?"
        section = c.get("section") or "Untitled"
        is_expanded = c.get("_expanded", False)

        block = (
            f"[SOURCE {source_num}]\n"
            f"Page: {page}\n"
            f"Section: {section}"
            f"{' (context expansion)' if is_expanded else ''}\n\n"
            f"{text}"
        )
        blocks.append(block)
        total += len(block) + 2  # +2 for \n\n separator

        sources.append({
            "source_num": source_num,
            "chunk_index": c["chunk_index"],
            "page_number": c.get("page_number"),
            "section": c.get("section", ""),
            "document_id": c.get("document_id"),
            "cosine_distance": c.get("cosine_distance"),
            "reranker_score": c.get("reranker_score"),
            "_expanded": is_expanded,
        })

    context_text = "\n\n".join(blocks) if blocks else ""

    return {
        "context_text": context_text,
        "sources": sources,
        "total_chars": len(context_text),
        "pipeline": {
            "input_candidates": len(candidates),
            "after_dedup": len(deduplicated),
            "after_expansion": len(expanded),
            "final_sources": len(sources),
            "total_chars": len(context_text),
        },
    }


# ── Answerability assessment (Phase 8) ─────────────────────────────

INSUFFICIENT_MESSAGE = (
    "Insufficient information was found in the available patient document "
    "to answer this question."
)


def assess_answerability(
    candidates: list[dict],
    rerank_threshold: float | None = None,
    cosine_threshold: float | None = None,
) -> dict:
    """
    Determine whether retrieval results contain sufficient evidence
    for the LLM to generate a grounded answer.

    Uses two signals:
        1. Top cosine distance (pgvector — lower = more similar) [PRIMARY]
        2. Top reranker score (CrossEncoder logit — higher = more relevant) [SECONDARY]

    The cosine distance is the primary gate because the CrossEncoder
    ms-marco model produces unreliable (mostly negative) scores for
    medical/clinical text. The reranker threshold acts as a safety net.

    Returns a dict with:
        is_answerable: bool
        reason: str (human-readable explanation)
        top_reranker_score: float | None
        top_cosine_distance: float | None
        candidate_count: int
    """
    rerank_threshold = (
        rerank_threshold
        if rerank_threshold is not None
        else RAG_ANSWERABILITY_RERANK_THRESHOLD
    )
    cosine_threshold = (
        cosine_threshold
        if cosine_threshold is not None
        else RAG_ANSWERABILITY_COSINE_THRESHOLD
    )

    if not candidates:
        return {
            "is_answerable": False,
            "reason": "No candidates retrieved from the document.",
            "top_reranker_score": None,
            "top_cosine_distance": None,
            "candidate_count": 0,
        }

    top = candidates[0]
    top_rerank = top.get("reranker_score")
    top_cosine = top.get("cosine_distance")

    # PRIMARY: Check cosine distance (reliable for all domains)
    if top_cosine is not None and top_cosine > cosine_threshold:
        return {
            "is_answerable": False,
            "reason": (
                f"Top cosine distance {top_cosine:.4f} exceeds threshold "
                f"{cosine_threshold:.4f}. The retrieved content is too "
                f"dissimilar to the query."
            ),
            "top_reranker_score": top_rerank,
            "top_cosine_distance": top_cosine,
            "candidate_count": len(candidates),
        }

    # SECONDARY: Check reranker score (safety net)
    if top_rerank is not None and top_rerank < rerank_threshold:
        return {
            "is_answerable": False,
            "reason": (
                f"Top reranker score {top_rerank:.2f} is critically low "
                f"(below {rerank_threshold:.2f}). The retrieved content "
                f"may not be relevant."
            ),
            "top_reranker_score": top_rerank,
            "top_cosine_distance": top_cosine,
            "candidate_count": len(candidates),
        }

    return {
        "is_answerable": True,
        "reason": (
            f"Top cosine distance {top_cosine:.4f} is within threshold "
            f"{cosine_threshold:.4f}."
        )
        if top_cosine is not None
        else "Candidates present; scores not fully available for assessment.",
        "top_reranker_score": top_rerank,
        "top_cosine_distance": top_cosine,
        "candidate_count": len(candidates),
    }


# ── Public retrieval API ────────────────────────────────────────────

def retrieve_context(document, query: str) -> str:
    """
    Retrieve relevant chunks for a query against a document.
    Returns a formatted string for direct inclusion in prompts.
    """
    result = retrieve_with_context(document.id, query)
    ctx = result["context"]
    if not ctx["context_text"]:
        return "(No relevant content retrieved from the document.)"
    return ctx["context_text"]


def retrieve_with_context(
    document_id: int,
    query: str,
    candidate_k: int | None = None,
    final_k: int | None = None,
    max_chars: int | None = None,
) -> dict:
    """
    Full retrieval pipeline returning candidates, assembled context,
    and answerability assessment.

    Returns:
        {
            candidates: [...],
            context: {context_text, sources, total_chars, pipeline},
            answerability: {is_answerable, reason, scores, candidate_count}
        }
    """
    candidates = retrieve_candidates(
        document_id, query, candidate_k=candidate_k, final_k=final_k
    )
    ctx = build_context(candidates, document_id=document_id, max_chars=max_chars)
    answerability = assess_answerability(candidates)
    return {
        "candidates": candidates,
        "context": ctx,
        "answerability": answerability,
    }


def retrieve_candidates(
    document_id: int,
    query: str,
    candidate_k: int | None = None,
    final_k: int | None = None,
) -> list[dict]:
    """
    Retrieve and optionally rerank candidates for a document query.

    Returns a list of dicts with:
        chunk_text, chunk_index, page_number, section,
        document_id, patient_id, embedding_id,
        cosine_distance, (reranker_score if reranked)

    Pipeline:
        query → embedding → pgvector top candidate_k → CrossEncoder rerank → top final_k
    """
    candidate_k = candidate_k or RAG_CANDIDATE_K
    final_k = final_k or RAG_FINAL_K

    try:
        candidates = query_with_scores(document_id, query, candidate_k)
    except EmbeddingUnavailableError:
        return []

    if not candidates:
        return []

    reranked = rerank(query, candidates)
    return reranked[:final_k]


def retrieve_patient_scoped(
    patient_id: int,
    query: str,
    candidate_k: int | None = None,
    final_k: int | None = None,
    document_id: int | None = None,
) -> list[dict]:
    """
    Patient-scoped retrieval with reranking.
    Searches across all documents for a patient (or a specific one).
    """
    from apps.ai.vectorstore import query_patient_scoped

    candidate_k = candidate_k or RAG_CANDIDATE_K
    final_k = final_k or RAG_FINAL_K

    try:
        candidates = query_patient_scoped(
            patient_id, query, candidate_k, document_id=document_id
        )
    except EmbeddingUnavailableError:
        return []

    if not candidates:
        return []

    reranked = rerank(query, candidates)
    return reranked[:final_k]
