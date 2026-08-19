"""
Prompt builders. Keeping the prompt text out of the call/parsing code
makes the contracts reviewable in one place and keeps `report_generation`
and the facade focused on control flow.
"""

REPORT_JSON_CONTRACT = """\
{
  "title": "Short title for the report",
  "summary": "One-paragraph plain-language summary",
  "sections": [
    {
      "heading": "Section heading",
      "content": "Paragraph text for that section"
    }
  ]
}
"""

ANALYSIS_JSON_CONTRACT = """\
{
  "summary": "One-paragraph plain-language summary of the document",
  "key_points": ["bullet 1", "bullet 2"],
  "query_answer": "Direct answer to the doctor's question, or an empty string if no question was asked",
  "sources_cited": ["SOURCE 1", "SOURCE 2"]
}
"""


def build_visit_reply_prompt(visit, message_content, document_context="") -> str:
    """Build the prompt for the doctor's chat-workspace assistant reply."""
    if visit is None:
        return f"""\
You are a clinical assistant supporting a physician's chat workspace.
The doctor wrote the message below. Reply directly, concisely, and in a
professional clinical register. Do not invent patient facts you cannot see.

DOCTOR'S MESSAGE:
{message_content}
"""

    patient = visit.patient
    demographics = (
        f"Patient: {patient.full_name} (MRN {patient.mrn}, "
        f"{patient.get_sex_display()}, born {patient.date_of_birth})"
    )
    prior_messages = visit.messages.exclude(content=message_content).order_by(
        "created_at"
    )[:10]
    thread_block = "\n".join(
        f"[{m.role.upper()}] {m.content}" for m in prior_messages
    ) or "(no prior messages)"

    context_block = ""
    if document_context:
        context_block = (
            "\nCLINICAL DOCUMENT CONTEXT (from uploaded patient documents):\n"
            f"{document_context}\n"
            "\nBase your answer on this clinical context when available. "
            "If the clinical context does not contain enough information "
            "to answer the question, say so explicitly.\n"
        )

    return f"""\
You are a clinical assistant supporting a physician's chat workspace.
Reply to the doctor's latest message directly and concisely in a
professional clinical register. Base your answer only on the context
provided; never invent facts.

{demographics}

{context_block}
RECENT CONVERSATION:
{thread_block}

DOCTOR'S LATEST MESSAGE:
{message_content}

Your response is shown as-is in the chat. Do not use Markdown headers or JSON.
"""


def build_report_prompt(patient, context_data) -> str:
    """Build the prompt that turns structured patient data into a report."""
    demographics = context_data["demographics"]
    visits = context_data["visits"]
    analyses = context_data["analyses"]

    demographics_block = "\n".join(
        f"- {key.replace('_', ' ').title()}: {value}"
        for key, value in demographics.items()
    )

    if visits:
        visits_block = "\n\n".join(
            f"Visit on {visit['date']} ({visit['status']}):\n"
            + "\n".join(f"- {message}" for message in visit["messages"])
            for visit in visits
        )
    else:
        visits_block = "No recorded visits."

    if analyses:
        analyses_block = "\n\n".join(
            f"{analysis['type']} (created {analysis['created_at']}):\n"
            f"{analysis['content']}"
            for analysis in analyses
        )
    else:
        analyses_block = "No existing automated analyses."

    return f"""\
You are a clinical assistant drafting an automated report for a physician.
Write in a professional, neutral clinical register. Never invent facts:
base every statement on the patient data provided below.

PATIENT DEMOGRAPHICS:
{demographics_block}

RECENT VISIT NOTES:
{visits_block}

EXISTING AUTOMATED ANALYSES:
{analyses_block}

Respond with ONLY a JSON object, no commentary, matching exactly this shape:
{REPORT_JSON_CONTRACT}
"""


def build_analysis_prompt(document, query, context) -> str:
    """Build the prompt for Feature B (RAG) document analysis."""
    query_block = query or "(no specific question — give an overall summary)"
    return f"""\
You are a clinical assistant reading a patient's medical document
(MRI, CT, lab report, or similar).

CRITICAL RULES:
- The text below has been DE-IDENTIFIED. Patient names and identifiers
  were replaced with placeholders like [PATIENT_NAME], [MRN], [DOB],
  [PHONE], [ADDRESS], [EMAIL]. Never reconstruct or guess original
  patient identities.
- Answer ONLY from the evidence in the EXCERPT below. Do NOT invent
  clinical facts, lab values, diagnoses, or treatments not present in
  the sources.
- When citing information, reference the source number (e.g. "SOURCE 1").
- If the excerpt does not contain enough information to answer the
  question, say so explicitly. Do not speculate.
- Distinguish between documented findings and your interpretation.
- Use the exact clinical values from the sources. Do not round,
  approximate, or transform lab values.

DOCUMENT TYPE: {document.get_doc_type_display()}

DOCTOR'S QUESTION:
{query_block}

RELEVANT EXCERPT FROM THE DOCUMENT:
{context}

Respond with ONLY a JSON object, no commentary, matching exactly this shape:
{ANALYSIS_JSON_CONTRACT}
"""
