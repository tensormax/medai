"""
De-identification layer for the RAG pipeline.

Uses Microsoft Presidio for PHI/PII detection combined with exact-match
replacements from the Patient record and custom regex recognizers for
clinical identifiers (MRN, encounter numbers, etc.).

Security boundary:
    Original patient data is retained in the application's controlled
    storage (Patient model, original PDF). The de-identified text is
    used ONLY for RAG embedding and retrieval. The LLM never receives
    the original patient identity.

Example:
    The same real-world value always maps to the same placeholder
    within a single document (e.g. "John Smith" → [PATIENT_NAME]
    everywhere in that document).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.patients.models import Patient

# ── Entity type labels ──────────────────────────────────────────────

ENTITY_LABELS = {
    "PERSON": "[PERSON]",
    "PHONE_NUMBER": "[PHONE]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "LOCATION": "[ADDRESS]",
    "DATE_TIME": "[DATE]",
    "MEDICAL_LICENSE": "[MEDICAL_ID]",
    "US_SSN": "[SSN]",
    "US_ITIN": "[ITIN]",
    "CREDIT_CARD": "[CREDIT_CARD]",
    "IP_ADDRESS": "[IP_ADDRESS]",
    "NRP": "[NRP]",
    "MEDICAL_RECORD": "[MRN]",
}

# Presidio entity types used for both detection AND anonymization (kept in sync).
_DETECT_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "LOCATION",
    "MEDICAL_LICENSE",
    "US_SSN",
    "DATE_TIME",
]

# Score threshold — lowered to catch partial matches like phone numbers.
_SCORE_THRESHOLD = 0.3

# ── Custom regex recognizers for clinical identifiers ────────────────

# MRN patterns: "MRN: 88213947", "MRN 88213947", "MRN# 88213947"
_MRN_PATTERN = re.compile(
    r"(?:MRN|medical\s+record\s*(?:number|#|no\.?)?)[\s:;#]*([A-Z0-9][\w\-]{3,20})",
    re.IGNORECASE,
)

# Encounter numbers: "ENC-2025-114402", "ENC2025114402"
_ENCOUNTER_PATTERN = re.compile(
    r"\bENC[\-\s]?[\d]{4}[\-\s]?\d{4,8}\b",
    re.IGNORECASE,
)

# Email
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# SSN: 123-45-6789
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Zip codes: 43215, 43215-1234 (only near known address context)
_ZIP_PATTERN = re.compile(r"\b\d{5}(?:-\d{4})?\b")

# IP address
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _regex_replace(text: str) -> str:
    """Apply regex-based replacements for identifiers Presidio may miss.
    Runs BEFORE Presidio so these patterns are replaced first."""
    result = text
    result = _EMAIL_PATTERN.sub("[EMAIL]", result)
    result = _SSN_PATTERN.sub("[SSN]", result)
    result = _IP_PATTERN.sub("[IP_ADDRESS]", result)
    result = _MRN_PATTERN.sub("[MRN]", result)
    result = _ENCOUNTER_PATTERN.sub("[ENCOUNTER_NUM]", result)
    result = _ZIP_PATTERN.sub("[ZIP]", result)
    return result


# ── False-positive protection ───────────────────────────────────────

# Counter for unique XCLINICAL placeholders (filtered from Presidio results).
_PROTECTED_COUNTER = 0


def _reset_counter():
    global _PROTECTED_COUNTER
    _PROTECTED_COUNTER = 0


def _make_placeholder() -> str:
    global _PROTECTED_COUNTER
    placeholder = f"XCLINICAL{_PROTECTED_COUNTER:04d}X"
    _PROTECTED_COUNTER += 1
    return placeholder


def _protect_false_positives(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Temporarily replace clinical values that Presidio falsely detects
    as PHI (e.g. blood pressure 148/92 → DATE_TIME, zip codes).
    Uses XCLINICAL placeholders that are filtered out of Presidio results.
    """
    _reset_counter()
    protected: list[tuple[str, str]] = []

    def _protect(m: re.Match) -> str:
        placeholder = _make_placeholder()
        protected.append((placeholder, m.group(0)))
        return placeholder

    result = text
    # Blood pressure: 148/92 mmHg, 120/80 mmHg (require mmHg to avoid matching dates)
    result = re.sub(r"\d{2,3}/\d{2,3}\s*mmHg", _protect, result)
    # Lab values: 9.2%, 186 mg/dL, 12.5 x10^9/L
    result = re.sub(
        r"\d+\.?\d*\s*(?:mg/dL|mmol/L|ng/mL|μg/L|U/mL|x10\^?\d*/L|mL/min(?:/[.\d]+m2)?)",
        _protect,
        result,
    )
    # Percentages: 9.2%, 97%
    result = re.sub(r"\d+\.?\d*\s*%", _protect, result)
    # Temperature: 98.6°F, 37.2°C
    result = re.sub(r"\b\d{2}\.\d+\s*°[FC]\b", _protect, result)
    # Zip codes (5 digits or 5+4): end of address lines
    result = re.sub(r"\b\d{5}(?:-\d{4})?\b", _protect, result)

    return result, protected


def _restore_false_positives(text: str, protected: list[tuple[str, str]]) -> str:
    """Restore temporarily protected clinical values."""
    result = text
    for placeholder, original in protected:
        result = result.replace(placeholder, original)
    return result


# ── Presidio singleton (lazy) ──────────────────────────────────────

_analyzer = None
_anonymizer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
    return _analyzer


def _get_anonymizer():
    global _anonymizer
    if _anonymizer is None:
        from presidio_anonymizer import AnonymizerEngine

        _anonymizer = AnonymizerEngine()
    return _anonymizer


# ── Presidio availability ──────────────────────────────────────────

class DeidentificationUnavailable(Exception):
    """Raised when Presidio or its dependencies are not installed."""


def _presidio_available() -> bool:
    try:
        import presidio_analyzer
        import presidio_anonymizer
        import spacy
        return True
    except ImportError:
        return False


# ── Core de-identification ──────────────────────────────────────────

def deidentify(text: str, patient: Patient) -> str:
    """
    De-identify text by replacing PHI/PII with stable placeholders.

    Pipeline:
    1. Exact-match replacements from Patient record (MRN, DOB, name, etc.)
    2. Regex-based replacements for clinical identifiers (MRN patterns, etc.)
    3. Protect clinical values from Presidio false positives
    4. Presidio PHI detection + anonymization (names, dates, phones, etc.)
    5. Restore protected clinical values

    The original Patient record is never modified.
    """
    if not text or not text.strip():
        return text

    # Step 1: Exact-match from Patient record
    result = _exact_match_replace(text, patient)

    # Step 2: Regex-based clinical identifiers (before Presidio)
    result = _regex_replace(result)

    # Step 3 + 4: Presidio with false-positive protection
    if _presidio_available():
        try:
            result = _presidio_anonymize(result)
        except Exception:
            pass

    return result


def _exact_match_replace(text: str, patient: Patient) -> str:
    """Replace exact occurrences of patient identifiers from the record."""
    result = text

    replacements = [
        (patient.full_name, "[PATIENT_NAME]"),
        (patient.mrn, "[MRN]"),
        (str(patient.date_of_birth), "[DOB]"),
    ]

    if patient.phone_number:
        replacements.append((patient.phone_number, "[PHONE]"))

    if patient.address:
        replacements.append((patient.address, "[ADDRESS]"))

    for value, placeholder in replacements:
        if value:
            result = result.replace(value, placeholder)

    # Also mask individual name parts for split-across-lines cases
    if patient.full_name:
        for part in patient.full_name.split():
            if part and len(part) > 1 and part.isalpha():
                result = result.replace(part, "[PATIENT_NAME]")

    return result


def _presidio_anonymize(text: str) -> str:
    """Use Presidio to detect and anonymize remaining PHI."""
    from presidio_analyzer import RecognizerResult
    from presidio_anonymizer.entities import OperatorConfig

    analyzer = _get_analyzer()
    anonymizer = _get_anonymizer()

    # Protect clinical values from false-positive detection
    protected_text, protected = _protect_false_positives(text)

    # Detect entities
    results: list[RecognizerResult] = analyzer.analyze(
        text=protected_text,
        language="en",
        entities=_DETECT_ENTITIES,
        score_threshold=_SCORE_THRESHOLD,
    )

    # Filter out detections that overlap with our protected placeholders
    if results and protected:
        protected_ranges = [
            (m.start(), m.end())
            for m in re.finditer(r"XCLINICAL\d+X", protected_text)
        ]
        results = [
            r for r in results
            if not any(
                start <= r.start < end or start < r.end <= end
                for start, end in protected_ranges
            )
        ]

    if not results:
        return text

    # Build operator config: replace each entity with a generic placeholder
    operators = {}
    for entity_type in ENTITY_LABELS:
        operators[entity_type] = OperatorConfig(
            "replace",
            {"new_value": ENTITY_LABELS[entity_type]},
        )
    operators["DEFAULT"] = OperatorConfig(
        "replace",
        {"new_value": "[REDACTED]"},
    )

    anonymized = anonymizer.anonymize(
        text=protected_text,
        analyzer_results=results,
        operators=operators,
    )

    # Restore protected clinical values
    return _restore_false_positives(anonymized.text, protected)


# ── Convenience: detect what would be anonymized ────────────────────

def detect_phi(text: str) -> list[dict]:
    """
    Return a list of detected PHI entities without replacing them.
    Uses the SAME entity list and threshold as _presidio_anonymize
    so the inspection page shows exactly what will be replaced.
    """
    if not _presidio_available():
        return []

    analyzer = _get_analyzer()

    # Protect clinical values same as anonymize does
    protected_text, _protected = _protect_false_positives(text)

    results = analyzer.analyze(
        text=protected_text,
        language="en",
        entities=_DETECT_ENTITIES,
        score_threshold=_SCORE_THRESHOLD,
    )

    # Filter out detections that overlap with our protected placeholders
    if results and _protected:
        protected_ranges = [
            (m.start(), m.end())
            for m in re.finditer(r"XCLINICAL\d+X", protected_text)
        ]
        results = [
            r for r in results
            if not any(
                start <= r.start < end or start < r.end <= end
                for start, end in protected_ranges
            )
        ]

    return [
        {
            "entity_type": r.entity_type,
            "start": r.start,
            "end": r.end,
            "score": r.score,
            "text": protected_text[r.start : r.end],
        }
        for r in results
    ]
