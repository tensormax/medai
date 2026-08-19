def _retrieve_patient_context(patient, query: str) -> str:
    """
    Retrieve relevant clinical context from the patient's uploaded documents.

    Uses patient-scoped RAG to find the most relevant chunks across all
    of the patient's documents. Returns a formatted context string that
    can be injected into chat prompts, or "" if nothing is found.
    """
    if patient is None:
        return ""

    try:
        from .retrieval import build_context, retrieve_patient_scoped
    except ImportError:
        return ""

    candidates = retrieve_patient_scoped(
        patient_id=patient.id,
        query=query,
        final_k=5,
    )
    if not candidates:
        return ""

    ctx = build_context(candidates)
    return ctx["context_text"]


class AIOrchestrator:
    """
    Single public entry point for all AI features. Everything else in the
    project imports only this class from apps.ai.facade — never any more
    granular module — so swapping the stub for a real LLM implementation
    later requires zero changes in calling code.
    """

    @staticmethod
    def generate_visit_reply(visit, message_content: str) -> str:
        """
        Generate the assistant's chat reply via the LLM (apps/ai/llm.py +
        apps/ai/prompts.py). Returns a graceful fallback message if the
        LLM call fails so the doctor's message is never lost.

        If the patient has uploaded documents, retrieves relevant clinical
        context from the RAG pipeline to ground the LLM's response.
        """
        from .llm import call_llm
        from .prompts import build_visit_reply_prompt

        document_context = ""
        if visit is not None:
            patient = visit.patient
            document_context = _retrieve_patient_context(patient, message_content)

        try:
            prompt = build_visit_reply_prompt(
                visit, message_content, document_context=document_context
            )
            return call_llm(prompt)
        except Exception:
            return (
                "[AI UNAVAILABLE] The assistant could not be reached. "
                "Check the OPENROUTER_API_KEY environment variable and try again."
            )

    @staticmethod
    def generate_report(patient) -> dict:
        """
        Feature A: run the report-generation pipeline for a patient.
        Returns {"prompt": ..., "report": <parsed JSON dict>}.
        Raises ReportGenerationError on LLM/parsing failure.
        """
        from .report_generation import generate_report

        return generate_report(patient)

    @staticmethod
    def analyze_document(document, query=None) -> dict:
        """
        Feature B full pipeline:
            retrieval → reranking → answerability → context assembly → prompt → LLM

        Returns a dict containing:
            prompt_used: the full prompt sent to the LLM (or "" if unanswerable)
            llm_response_json: parsed JSON response from the LLM
            answerability: assessment of retrieval quality
            retrieval_pipeline: trace of the retrieval stages
            deidentification: de-identification status of the source document

        If the query is unanswerable from the document, returns a controlled
        "insufficient information" response WITHOUT calling the LLM.

        If the LLM call fails, returns a graceful error response.
        """
        from . import retrieval
        from .llm import LLMAvailabilityError, call_llm
        from .prompts import build_analysis_prompt
        from .report_generation import parse_llm_json

        result = retrieval.retrieve_with_context(document.id, query)
        answerability = result["answerability"]
        context = result["context"]["context_text"]

        base_response = {
            "answerability": answerability,
            "retrieval_pipeline": result["context"]["pipeline"],
            "deidentification": {
                "document_deidentified": document.de_identified,
                "context_contains_patient_identity": False,
            },
        }

        if not answerability["is_answerable"]:
            return {
                **base_response,
                "prompt_used": "",
                "llm_response_json": {
                    "summary": retrieval.INSUFFICIENT_MESSAGE,
                    "key_points": [],
                    "query_answer": retrieval.INSUFFICIENT_MESSAGE,
                    "sources_cited": [],
                },
            }

        prompt = build_analysis_prompt(document, query, context)

        try:
            response_text = call_llm(prompt)
        except LLMAvailabilityError as exc:
            return {
                **base_response,
                "prompt_used": prompt,
                "llm_response_json": {
                    "summary": f"[AI UNAVAILABLE] {exc}",
                    "key_points": [],
                    "query_answer": f"[AI UNAVAILABLE] {exc}",
                    "sources_cited": [],
                },
            }

        parsed = parse_llm_json(response_text)
        return {
            **base_response,
            "prompt_used": prompt,
            "llm_response_json": parsed,
        }
