"""
Feature A pipeline: structured patient data -> prompt -> LLM -> JSON.

This module owns the JSON contract parsing and its failure handling.
It never touches templates or PDFs — it returns the parsed report and
lets the view render/save it.
"""

import json
import re

from apps.ai.llm import LLMAvailabilityError, call_llm
from apps.ai.prompts import build_report_prompt
from apps.documents.models import DocumentAnalysis


class ReportGenerationError(Exception):
    """Raised when the LLM call fails or returns unusable output."""


def parse_llm_json(response_text):
    if not response_text or not response_text.strip():
        raise ReportGenerationError("The LLM returned an empty response.")
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportGenerationError(
            "The LLM returned malformed JSON that could not be parsed."
        ) from exc


def _gather_context(patient):
    demographics = {
        "full name": patient.full_name,
        "date of birth": str(patient.date_of_birth),
        "sex": patient.get_sex_display(),
        "mrn": patient.mrn,
    }
    if patient.phone_number:
        demographics["phone number"] = patient.phone_number
    if patient.address:
        demographics["address"] = patient.address

    visits = [
        {
            "date": visit.started_at.strftime("%d/%m/%Y"),
            "status": visit.get_status_display(),
            "messages": [m.content for m in visit.messages.all()],
        }
        for visit in patient.visits.all()[:5]
    ]

    analyses = [
        {
            "type": analysis.get_analysis_type_display(),
            "created_at": analysis.created_at.strftime("%d/%m/%Y"),
            "content": (
                analysis.llm_response_json.get("summary", "")
                if isinstance(analysis.llm_response_json, dict)
                else str(analysis.llm_response_json)
            ),
        }
        for analysis in DocumentAnalysis.objects.filter(
            document__patient=patient
        )[:5]
    ]

    return {"demographics": demographics, "visits": visits, "analyses": analyses}


def generate_report(patient) -> dict:
    """
    Build the prompt, call the LLM, parse the JSON report.
    Returns {"prompt": <prompt text>, "report": <parsed JSON dict>}.
    Raises ReportGenerationError on any LLM/parsing failure.
    """
    context = _gather_context(patient)
    prompt = build_report_prompt(patient, context)
    try:
        response_text = call_llm(prompt)
    except LLMAvailabilityError as exc:
        raise ReportGenerationError(str(exc)) from exc
    report = parse_llm_json(response_text)
    return {"prompt": prompt, "report": report}
