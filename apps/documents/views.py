from pathlib import Path

import json
from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.ai.facade import AIOrchestrator
from apps.ai.report_generation import ReportGenerationError
from apps.patients.services import get_patient_or_404_for
from apps.visits.services import get_visit_or_404_for

from .clinical_docs import DOCUMENT_TYPE_LABELS, generate_document
from .clinical_forms import (
    ConsultationSummaryForm,
    MedicalCertificateForm,
    PrescriptionForm,
    ReferralLetterForm,
)
from .forms import DocumentUploadForm
from .models import Document, GeneratedClinicalDocument
from .pdf import PDFRenderingError, render_html_to_pdf
from .services import (
    UploadProcessingError,
    get_document_analysis_or_404_for,
    get_document_or_404_for,
    get_or_create_analysis,
    process_upload,
)


@login_required
def document_index(request):
    doctor = request.user.doctor_profile
    documents = Document.objects.filter(patient__doctor=doctor).select_related(
        "patient"
    )
    return render(
        request, "documents/document_index.html", {"documents": documents}
    )


@login_required
def report_generate(request, patient_pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    if request.method != "POST":
        return redirect("patients:patient_detail", pk=patient.pk)
    try:
        result = AIOrchestrator.generate_report(patient)
    except ReportGenerationError as exc:
        messages.error(request, f"Report generation failed: {exc}")
        return redirect("patients:patient_detail", pk=patient.pk)

    report = result["report"]
    html = render_to_string(
        "documents/pdf/generated_report.html",
        {"report": report, "patient": patient},
    )
    document = Document.objects.create(
        patient=patient,
        kind="generated",
        doc_type="report",
        title=(report.get("title") or f"Report for {patient.full_name}")[:255],
        de_identified=False,
    )
    analysis = document.analyses.create(
        analysis_type="generated_report",
        prompt_used=result["prompt"],
        llm_response_json=report,
        rendered_html=html,
    )
    try:
        pdf_bytes = render_html_to_pdf(html)
        analysis.pdf_file.save(
            f"report_patient_{patient.pk}_analysis_{analysis.pk}.pdf",
            ContentFile(pdf_bytes),
            save=True,
        )
    except PDFRenderingError as exc:
        messages.error(request, f"Report saved but PDF rendering failed: {exc}")
    return redirect("documents:report_detail", pk=analysis.pk)


@login_required
def report_detail(request, pk):
    doctor = request.user.doctor_profile
    analysis = get_document_analysis_or_404_for(doctor, pk)
    return render(
        request, "documents/report_detail.html", {"analysis": analysis}
    )


@login_required
def report_download(request, pk):
    doctor = request.user.doctor_profile
    analysis = get_document_analysis_or_404_for(doctor, pk)
    if not analysis.pdf_file:
        raise Http404("No PDF is available for this report.")
    return FileResponse(
        analysis.pdf_file.open("rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename=Path(analysis.pdf_file.name).name,
    )


@login_required
@xframe_options_sameorigin
def report_raw(request, pk):
    """Serve the raw report PDF inline (for embed)."""
    doctor = request.user.doctor_profile
    analysis = get_document_analysis_or_404_for(doctor, pk)
    if not analysis.pdf_file:
        raise Http404("No PDF is available for this report.")
    return FileResponse(
        analysis.pdf_file.open("rb"),
        content_type="application/pdf",
    )


@login_required
def document_list(request, patient_pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    documents = Document.objects.filter(patient=patient)
    return render(
        request,
        "documents/document_list.html",
        {"patient": patient, "documents": documents},
    )


@login_required
def document_upload(request, patient_pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.patient = patient
            document.kind = "uploaded"
            document.title = Path(form.cleaned_data["file"].name).name
            document.save()
            try:
                process_upload(document)
            except UploadProcessingError as exc:
                messages.error(request, f"Could not process document: {exc}")
                return redirect(
                    "documents:document_list", patient_pk=patient.pk
                )
            messages.success(
                request,
                f"Document processed: {document.chunk_count} chunks created.",
            )
            return redirect("documents:chunk_inspection", pk=document.pk)
    else:
        form = DocumentUploadForm()
    return render(
        request,
        "documents/document_upload.html",
        {"form": form, "patient": patient},
    )


@login_required
def analysis_detail(request, pk):
    doctor = request.user.doctor_profile
    document = get_document_or_404_for(doctor, pk)

    # Check if an analysis already exists
    existing = (
        document.analyses.filter(analysis_type="summary")
        .order_by("-created_at")
        .first()
    )

    if existing:
        return render(
            request,
            "documents/analysis_detail.html",
            {"document": document, "analysis": existing, "query": None},
        )

    # No analysis yet — in Phase 2, redirect to chunk inspection
    # (LLM generation is not connected yet)
    return redirect("documents:chunk_inspection", pk=document.pk)


@login_required
def chunk_inspection(request, pk):
    """Development-only view to inspect processed document chunks."""
    doctor = request.user.doctor_profile
    document = get_document_or_404_for(doctor, pk)
    chunks = document.chunks.select_related("patient").order_by("chunk_index")

    chunk_data = []
    for chunk in chunks:
        chunk_data.append({
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "section": chunk.section or "(no section)",
            "text": chunk.chunk_text,
            "embedding_id": chunk.embedding_id or "(not embedded)",
        })

    return render(
        request,
        "documents/chunk_inspection.html",
        {
            "document": document,
            "chunks": chunk_data,
            "chunk_count": len(chunk_data),
            "processing_status": document.get_processing_status_display(),
        },
    )


@login_required
def deidentification_inspection(request, pk):
    """
    Development-only view comparing original vs de-identified text.
    NOT for production use — exposes original PHI to authorized doctors.
    """
    doctor = request.user.doctor_profile
    document = get_document_or_404_for(doctor, pk)

    # Read original text
    from .services import extract_text

    original_text = extract_text(document)

    # Get de-identified text from chunks
    chunks = document.chunks.order_by("chunk_index")
    deidentified_text = "\n\n".join(c.chunk_text for c in chunks)

    # Detect PHI entities for the inspection display
    from apps.ai.deidentify import detect_phi

    phi_entities = detect_phi(original_text) if original_text else []

    return render(
        request,
        "documents/deidentification_inspection.html",
        {
            "document": document,
            "original_text": original_text,
            "deidentified_text": deidentified_text,
            "phi_entities": phi_entities,
            "phi_count": len(phi_entities),
        },
    )



# Clinical document generation


CLINICAL_FORM_MAP = {
    "consultation_summary": ConsultationSummaryForm,
    "prescription": PrescriptionForm,
    "medical_certificate": MedicalCertificateForm,
    "referral_letter": ReferralLetterForm,
}


def _get_clinical_form_data(form):
    """Extract cleaned data as a plain dict, handling medications_json."""
    data = dict(form.cleaned_data)
    if "medications_json" in data:
        try:
            data["medications"] = json.loads(data["medications_json"])
        except (json.JSONDecodeError, TypeError):
            data["medications"] = []
        del data["medications_json"]
    if "visit" in data:
        data["visit"] = data["visit"]  # keep the visit object for context
    # Convert date/datetime objects to ISO strings for JSON serialization
    for key, val in data.items():
        if isinstance(val, (date, datetime)):
            data[key] = val.isoformat()
    return data


@login_required
def clinical_document_form(request, patient_pk, doc_type):
    """Show the form for generating a clinical document."""
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)

    if doc_type not in CLINICAL_FORM_MAP:
        raise Http404("Unknown document type.")

    FormClass = CLINICAL_FORM_MAP[doc_type]
    form = FormClass()

    # Populate visit queryset for consultation summary
    if doc_type == "consultation_summary":
        form.fields["visit"].queryset = patient.visits.order_by("-started_at")

    return render(
        request,
        "documents/clinical_document_form.html",
        {
            "form": form,
            "patient": patient,
            "doc_type": doc_type,
            "doc_type_label": DOCUMENT_TYPE_LABELS[doc_type],
        },
    )


@login_required
def clinical_document_generate(request, patient_pk, doc_type):
    """Process the form and generate the PDF."""
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)

    if doc_type not in CLINICAL_FORM_MAP:
        raise Http404("Unknown document type.")

    if request.method != "POST":
        return redirect("documents:clinical_document_form", patient_pk=patient.pk, doc_type=doc_type)

    FormClass = CLINICAL_FORM_MAP[doc_type]
    form = FormClass(request.POST)

    # Populate visit queryset for validation
    if doc_type == "consultation_summary":
        form.fields["visit"].queryset = patient.visits.order_by("-started_at")

    if not form.is_valid():
        return render(
            request,
            "documents/clinical_document_form.html",
            {
                "form": form,
                "patient": patient,
                "doc_type": doc_type,
                "doc_type_label": DOCUMENT_TYPE_LABELS[doc_type],
            },
        )

    form_data = _get_clinical_form_data(form)
    visit = form_data.pop("visit", None)

    try:
        pdf_bytes, title = generate_document(
            document_type=doc_type,
            patient=patient,
            doctor=doctor,
            visit=visit,
            form_data=form_data,
        )
    except Exception as exc:
        messages.error(request, f"Document generation failed: {exc}")
        return redirect("documents:clinical_document_form", patient_pk=patient.pk, doc_type=doc_type)

    # Store the generated document
    doc = GeneratedClinicalDocument.objects.create(
        patient=patient,
        doctor=doctor,
        visit=visit,
        document_type=doc_type,
        title=title,
        form_data=form_data,
    )
    doc.pdf_file.save(
        f"{doc_type}_{patient.pk}_{doc.pk}.pdf",
        ContentFile(pdf_bytes),
        save=True,
    )

    messages.success(request, f"{title} generated successfully.")
    return redirect("documents:clinical_document_view", pk=doc.pk)


@login_required
def clinical_document_view(request, pk):
    """Show the PDF viewer page with download button."""
    doc = get_object_or_404_or_403(request.user.doctor_profile, pk)
    return render(
        request,
        "documents/clinical_document_view.html",
        {"doc": doc, "patient": doc.patient},
    )


@login_required
@xframe_options_sameorigin
def clinical_document_raw(request, pk):
    """Serve the raw PDF inline (for embed/iframe)."""
    doc = get_object_or_404_or_403(request.user.doctor_profile, pk)
    if not doc.pdf_file:
        raise Http404("PDF not available.")
    return FileResponse(
        doc.pdf_file.open("rb"),
        content_type="application/pdf",
    )


@login_required
def clinical_document_download(request, pk):
    """Download a generated clinical document PDF."""
    doc = get_object_or_404_or_403(request.user.doctor_profile, pk)
    if not doc.pdf_file:
        raise Http404("PDF not available.")
    return FileResponse(
        doc.pdf_file.open("rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename=Path(doc.pdf_file.name).name,
    )


@login_required
def clinical_document_list(request, patient_pk):
    """List all generated clinical documents for a patient."""
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    docs = GeneratedClinicalDocument.objects.filter(
        patient=patient, doctor=doctor
    )
    return render(
        request,
        "documents/clinical_document_list.html",
        {"patient": patient, "documents": docs},
    )


def get_object_or_404_or_403(doctor, pk):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(
        GeneratedClinicalDocument, doctor=doctor, pk=pk
    )
