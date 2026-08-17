import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.patients.services import get_patient_or_404_for

from .forms import DocumentUploadForm
from .services import (
    IngestionError,
    delete_document,
    get_document_or_404_for,
    get_documents_for,
    ingest_document,
    search_chunks,
)


@login_required
def document_list(request, patient_pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    documents = get_documents_for(doctor, patient)
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
        form = DocumentUploadForm(request.POST, request.FILES, patient=patient)
        if form.is_valid():
            document = form.save(commit=False)
            document.patient = patient
            document.kind = "uploaded"
            if not document.title:
                document.title = os.path.basename(document.file.name)
            document.save()
            try:
                chunk_count = ingest_document(document)
            except IngestionError as exc:
                document.delete()
                form.add_error("file", str(exc))
            else:
                messages.success(
                    request,
                    f"Document ingested: {chunk_count} chunks embedded and "
                    f"indexed for retrieval.",
                )
                return redirect("documents:document_detail", pk=document.pk)
    else:
        form = DocumentUploadForm(patient=patient)

    return render(
        request,
        "documents/document_form.html",
        {"form": form, "patient": patient},
    )


@login_required
def document_detail(request, pk):
    doctor = request.user.doctor_profile
    document = get_document_or_404_for(doctor, pk)
    chunks = document.chunks.all()
    return render(
        request,
        "documents/document_detail.html",
        {"document": document, "patient": document.patient, "chunks": chunks},
    )


@login_required
@require_POST
def document_delete(request, pk):
    doctor = request.user.doctor_profile
    document = get_document_or_404_for(doctor, pk)
    patient_pk = document.patient_id
    delete_document(document)
    messages.info(request, "Document and its embeddings were removed.")
    return redirect("documents:document_list", patient_pk=patient_pk)


@login_required
def document_search(request, patient_pk):
    """
    JSON endpoint: semantic search over a patient's ingested documents.
    GET ?q=<query>&k=<top_k>. This is the retrieval half of the RAG
    pipeline; generation plugs in on top of it next iteration.
    """
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)

    query = (request.GET.get("q") or "").strip()
    if not query:
        return JsonResponse(
            {"error": "Provide a query with ?q=", "results": []}, status=400
        )
    try:
        top_k = min(max(int(request.GET.get("k", 5)), 1), 20)
    except ValueError:
        top_k = 5

    results = search_chunks(doctor, patient, query, top_k=top_k)
    return JsonResponse(
        {"patient_id": patient.pk, "query": query, "results": results}
    )


@login_required
@require_POST
def report_generate(request, patient_pk):
    """
    Feature A (generated reports) is the NEXT iteration — the AI model
    layer is not written yet. This stub keeps the button on the patient
    page working instead of raising NoReverseMatch.
    """
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    messages.info(
        request,
        "Report generation is coming in the next iteration — documents "
        "uploaded now are already embedded and RAG-ready for it.",
    )
    return redirect("patients:patient_detail", pk=patient.pk)
