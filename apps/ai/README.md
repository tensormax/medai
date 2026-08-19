# apps/ai — AI stack

Single public entry point: `AIOrchestrator` in `facade.py`. All other apps
import only that class. Feature A (report generation) and Feature B (RAG)
live behind it.

## Stack

| Concern        | Choice                                                              |
| -------------- | ------------------------------------------------------------------- |
| LLM access     | OpenRouter via the `openai` Python library (OpenAI-compatible `base_url`) |
| Model          | `LLM_MODEL` in `llm.py` — currently `"nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"`; set by Max, do not choose |
| API key        | `OPENROUTER_API_KEY` from the environment only, read when the client is constructed in `llm.py`. Never logged, never read from a file. |
| PDF extraction | `pypdf` for page-level text extraction (`apps/ai/chunking.py`)      |
| Chunking       | Section-aware chunking + LangChain `RecursiveCharacterTextSplitter` (`apps/ai/chunking.py`) |
| Vector store   | Chroma, local + persisted, under `media/chroma/` (`apps/ai/vectorstore.py`) |
| Embeddings     | Local `sentence-transformers` model, `EMBEDDING_MODEL = "all-MiniLM-L6-v2"` (`apps/ai/embeddings.py`), no external API |
| De-identification | Rule-based/regex in `apps/ai/deidentify.py`                          |

## Modules

- `llm.py` — the only module that touches the provider/key. `call_llm(prompt) -> str`.
- `prompts.py` — `build_report_prompt(patient, context_data)` and
  `build_analysis_prompt(document, query, context)`; the JSON contracts
  the LLM must return are defined here.
- `report_generation.py` — Feature A pipeline. Gathers structured patient
  data (demographics, recent visit messages, existing analyses) -> prompt ->
  `call_llm` -> `parse_llm_json` (handles code fences, raises
  `ReportGenerationError` on empty/malformed output).
- `chunking.py` — Structure-aware chunking pipeline:
  - `extract_pages(pdf_bytes)` → `list[PageText]` (preserves page numbers)
  - `normalize_text(text)` → cleaned text (artifacts removed)
  - `detect_sections(pages)` → `list[SectionBlock]` (clinical heading detection)
  - `chunk_document(pages)` → `list[ChunkResult]` with metadata
  - Uses LangChain `RecursiveCharacterTextSplitter` as fallback for large sections
  - Configurable `CHUNK_SIZE` (800) and `CHUNK_OVERLAP` (150)
- `deidentify.py` — masks exact occurrences of the patient's full name,
  name parts, DOB, MRN, phone, and address.
- `embeddings.py` / `vectorstore.py` — embedding + Chroma persistence;
  `upsert(document_id, chunks, vectors)` and `query(document_id, query_text, k)`.
- `retrieval.py` — `retrieve_context(document, query)` joins the top-k
  chunks (k=3) into a context block.

## Feature A — Report generation

Doctor requests a report -> prompt from structured patient data -> LLM
returns JSON (`title`, `summary`, `sections[]`) -> rendered to
`templates/documents/pdf/generated_report.html` -> PDF via WeasyPrint ->
saved as `Document(kind="generated")` + `DocumentAnalysis(analysis_type="generated_report")`.

Failure handling: LLM failure or malformed JSON raises
`ReportGenerationError`; the view shows a clear error and writes nothing.
PDF failure raises `PDFRenderingError`; the analysis (HTML) is still
saved, no partial PDF is written.

## Feature B — Document understanding / RAG (Phase 2)

Upload (`.txt`/`.pdf`) → extract pages with `pypdf` → normalize text →
detect clinical section headers → split with LangChain
`RecursiveCharacterTextSplitter` → save `DocumentChunk` rows with
metadata (`page_number`, `section`, `chunk_index`, `patient`).

Processing status tracked on `Document.processing_status`:
`pending` → `processing` → `completed` | `failed`

Chunk inspection available at `/documents/<pk>/chunks/` for development.

## Known limitations

- **De-identification is exact-match only.** A phone written as
  `555-123-4567` when the record stores `5551234567`, or a DOB in a
  different format, is NOT masked.
- WeasyPrint needs native GTK/Pango/Cairo on Windows; without them
  `render_html_to_pdf` raises `PDFRenderingError`.
- Retrieval is keyword-based fallback only (embeddings disabled by default).
- No reranking, no answerability detection, no LLM generation in RAG pipeline yet.

## Phase status

| Phase | Status |
|-------|--------|
| Phase 1 — Audit | Complete |
| Phase 2 — PDF ingestion RAG-ready | Complete |
| Phase 3 — De-identification | Pending |
| Phase 4 — Embeddings and pgvector | Pending |
| Phase 5 — Dense retrieval | Pending |
| Phase 6 — CrossEncoder reranking | Pending |
| Phase 7 — Context assembly | Pending |
| Phase 8 — Answerability | Pending |
| Phase 9 — LLM integration and generation | Pending |
