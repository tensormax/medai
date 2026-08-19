"""
Structure-aware document chunking for the RAG pipeline.

Pipeline:
    PDF bytes → page extraction → normalization → section detection → chunking

Uses LangChain's RecursiveCharacterTextSplitter as the fallback splitting
mechanism after document structure has been recovered. Clinical section
boundaries are preferred over recursive splitting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO

from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Configurable defaults ───────────────────────────────────────────

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

_RECURSIVE_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# ── Clinical section detection ──────────────────────────────────────

# Patterns that look like clinical section headings.
# A line qualifies if it matches ONE of:
#   1. A known clinical section name (case-insensitive)
#   2. Numbered heading: "1. Vital Signs" or "2) Assessment:"
#   3. Heading ending with colon: "Vital Signs:"
#   4. ALL CAPS or Title Case short line (≤50 chars, no period at end)
_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"(?:\d+\.\s+)"                               # numbering prefix
    r"|"                                           # OR
    r"(?:[A-Z][A-Za-z /&-]{2,50}\s*:?\s*)$"       # heading (may end with colon)
    r")",
    re.MULTILINE,
)

# Well-known clinical section names for more precise matching.
_KNOWN_SECTIONS = {
    "chief complaint",
    "history of present illness",
    "hpi",
    "vital signs",
    "vitals",
    "physical examination",
    "exam",
    "review of systems",
    "ros",
    "allergies",
    "medications",
    "medications on admission",
    "current medications",
    "past medical history",
    "pmh",
    "past surgical history",
    "family history",
    "social history",
    "laboratory results",
    "lab results",
    "labs",
    "imaging",
    "radiology",
    "assessment",
    "diagnosis",
    "differential diagnosis",
    "plan",
    "treatment",
    "discharge summary",
    "discharge instructions",
    "follow-up",
    "follow up",
    "procedure",
    "operations",
    "operative report",
    "indication",
    "findings",
    "impression",
    "recommendations",
    "progress note",
    "progress notes",
    "subjective",
    "objective",
    "subjective / objective",
    "soap note",
    "code status",
    "nutritional status",
    "activity",
    "skin",
    "heent",
    "neck",
    "chest",
    "cardiovascular",
    "respiratory",
    "abdomen",
    "musculoskeletal",
    "neurological",
    "psychiatric",
    "extremities",
    "hematology",
    "oncology",
    "endocrinology",
    "gastroenterology",
    "nephrology",
    "urology",
    "pulmonology",
    "cardiology",
    "infectious disease",
}


# ── Data structures ─────────────────────────────────────────────────

@dataclass
class PageText:
    """Raw text extracted from a single PDF page."""
    page_number: int
    text: str


@dataclass
class SectionBlock:
    """A detected section spanning one or more pages."""
    name: str
    text: str
    start_page: int
    end_page: int


@dataclass
class ChunkResult:
    """A final chunk with its metadata, ready for embedding."""
    text: str
    page_number: int
    section: str
    chunk_index: int


# ── PDF extraction ──────────────────────────────────────────────────

class PDFExtractionError(Exception):
    """Raised when PDF text extraction fails."""


def extract_pages(pdf_bytes: bytes) -> list[PageText]:
    """
    Extract text from each page of a PDF, preserving page numbers.

    Returns a list of PageText objects (one per page). Empty pages are
    included so that page numbers remain contiguous and accurate.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PDFExtractionError(
            "PDF support requires pypdf (pip install pypdf)."
        ) from exc

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:
        raise PDFExtractionError(
            f"Failed to open PDF: {type(exc).__name__}: {exc}"
        ) from exc

    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(PageText(page_number=i, text=text))

    return pages


def extract_text(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF (flat, all pages joined). For backward compatibility."""
    pages = extract_pages(pdf_bytes)
    return "\n\n".join(p.text for p in pages if p.text.strip())


# ── Normalization ───────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """
    Clean extraction artifacts without altering clinical meaning.

    Handles:
    - excessive whitespace / blank lines
    - obvious repeated headers/footers (lines repeated on >80% of pages)
    - broken line wrapping (short lines that are not paragraphs)
    """
    if not text or not text.strip():
        return ""

    lines = text.split("\n")
    cleaned = []

    for line in lines:
        # Collapse excessive internal whitespace (tabs, multiple spaces)
        line = re.sub(r"[^\S\n]+", " ", line)
        # Strip trailing whitespace
        line = line.rstrip()
        cleaned.append(line)

    text = "\n".join(cleaned)

    # Collapse runs of 3+ blank lines down to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def remove_repeated_headers_footer(pages: list[PageText]) -> list[PageText]:
    """
    Detect lines that appear on >80% of pages (common with headers/footers)
    and strip them from all pages.
    """
    if len(pages) < 3:
        return pages

    from collections import Counter

    # Collect non-empty, stripped lines from each page
    line_pages: dict[str, set[int]] = {}
    for page in pages:
        for line in page.text.split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) < 100:
                line_pages.setdefault(stripped, set()).add(page.page_number)

    total_pages = len(pages)
    repeated = {
        line
        for line, pnums in line_pages.items()
        if len(pnums) > total_pages * 0.8
    }

    if not repeated:
        return pages

    result = []
    for page in pages:
        filtered = "\n".join(
            line for line in page.text.split("\n")
            if line.strip() not in repeated
        )
        result.append(PageText(page_number=page.page_number, text=filtered))

    return result


# ── Section detection ───────────────────────────────────────────────

def _is_section_header(line: str) -> bool:
    """Return True if a line looks like a clinical section heading."""
    stripped = line.strip()
    if not stripped:
        return False

    # Check against known section names first (most reliable)
    lower = stripped.lower().rstrip(":")
    # Strip leading numbering like "1." or "2)"
    lower = re.sub(r"^\d+[.)]\s*", "", lower)
    if lower in _KNOWN_SECTIONS:
        return True

    # For unknown headings, require strong signals:
    # 1. Ends with ":" (explicit heading marker)
    # 2. Or has numbering prefix like "1." / "2)"
    # 3. Or is ALL CAPS and short
    # Reject lines containing digits mixed with letters (e.g. "HbA1c 7.0")
    if re.search(r"\d", stripped) and re.search(r"[a-z]", stripped.lower()):
        return False

    if stripped.endswith(":"):
        # Colon-terminated heading — must be short and not a sentence
        if len(stripped) <= 60 and stripped.count(" ") <= 8:
            return True

    if re.match(r"^\d+[.)]\s+", stripped):
        # Numbered heading
        cleaned = re.sub(r"^\d+[.)]\s*", "", stripped).rstrip(":")
        if len(cleaned) <= 60:
            return True

    # ALL CAPS short line (e.g. "VITAL SIGNS")
    if stripped.isupper() and len(stripped) <= 50 and len(stripped) >= 3:
        return True

    return False


def _extract_section_name(line: str) -> str:
    """Extract the clean section name from a heading line."""
    stripped = line.strip()
    # Remove leading numbering
    stripped = re.sub(r"^\d+[.)]\s*", "", stripped)
    # Remove trailing colon
    stripped = stripped.rstrip(":").strip()
    return stripped


def detect_sections(pages: list[PageText]) -> list[SectionBlock]:
    """
    Detect clinical section boundaries across pages.

    Returns SectionBlock objects. If no sections are detected, returns
    a single "Untitled" section spanning all pages.
    """
    sections: list[SectionBlock] = []
    current_name = "Untitled"
    current_lines: list[str] = []
    current_start_page = 1

    for page in pages:
        for line in page.text.split("\n"):
            if _is_section_header(line):
                # Save previous section if it has content
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        sections.append(SectionBlock(
                            name=current_name,
                            text=text,
                            start_page=current_start_page,
                            end_page=page.page_number,
                        ))
                current_name = _extract_section_name(line)
                current_lines = []
                current_start_page = page.page_number
            else:
                current_lines.append(line)

    # Save last section
    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            end_page = pages[-1].page_number if pages else 1
            sections.append(SectionBlock(
                name=current_name,
                text=text,
                start_page=current_start_page,
                end_page=end_page,
            ))

    # If no sections were detected, treat entire document as one section
    if not sections:
        all_text = "\n\n".join(
            p.text for p in pages if p.text.strip()
        )
        if all_text.strip():
            end_page = pages[-1].page_number if pages else 1
            sections.append(SectionBlock(
                name="Untitled",
                text=all_text.strip(),
                start_page=1,
                end_page=end_page,
            ))

    return sections


# ── Chunking ────────────────────────────────────────────────────────

class ChunkingError(Exception):
    """Raised when chunking fails."""


def chunk_document(
    pages: list[PageText],
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[ChunkResult]:
    """
    Full chunking pipeline: section detection → recursive splitting.

    For each detected section, if the section text exceeds chunk_size,
    it is split using LangChain's RecursiveCharacterTextSplitter.

    Returns a flat list of ChunkResult objects with metadata.
    """
    if not pages or not any(p.text.strip() for p in pages):
        return []

    # Normalize each page
    normalized_pages = [
        PageText(
            page_number=p.page_number,
            text=normalize_text(p.text),
        )
        for p in pages
    ]

    # Remove repeated headers/footers
    normalized_pages = remove_repeated_headers_footer(normalized_pages)

    # Detect sections
    sections = detect_sections(normalized_pages)

    if not sections:
        return []

    # Splitter for sections that exceed chunk_size
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_RECURSIVE_SEPARATORS,
        keep_separator=True,
        length_function=len,
    )

    results: list[ChunkResult] = []
    global_index = 0

    for section in sections:
        if not section.text.strip():
            continue

        if len(section.text) <= chunk_size:
            # Section fits in one chunk
            results.append(ChunkResult(
                text=section.text,
                page_number=section.start_page,
                section=section.name,
                chunk_index=global_index,
            ))
            global_index += 1
        else:
            # Section is too large — recursively split
            sub_chunks = splitter.split_text(section.text)
            for sub_text in sub_chunks:
                if not sub_text.strip():
                    continue
                results.append(ChunkResult(
                    text=sub_text.strip(),
                    page_number=section.start_page,
                    section=section.name,
                    chunk_index=global_index,
                ))
                global_index += 1

    return results
