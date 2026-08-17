"""
MINIMAL visits stubs.

The visits app is scheduled for a later iteration — these views exist
only so the URL names referenced by templates/patients/patient_detail.html
(`visits:visit_create`, `visits:visit_detail`, `visits:message_send`)
resolve and the patient page renders. The AI reply side of `message_send`
is intentionally absent: the model layer isn't written yet.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.patients.services import get_patient_or_404_for

from .models import Visit, VisitMessage


def _get_visit_or_404_for(doctor, pk):
    return get_object_or_404(Visit, pk=pk, doctor=doctor)


@login_required
@require_POST
def visit_create(request, patient_pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, patient_pk)
    Visit.objects.create(patient=patient, doctor=doctor, status="open")
    messages.success(request, "Visit started.")
    return redirect("patients:patient_detail", pk=patient.pk)


@login_required
def visit_detail(request, pk):
    doctor = request.user.doctor_profile
    visit = _get_visit_or_404_for(doctor, pk)
    return render(
        request,
        "visits/visit_detail.html",
        {"visit": visit, "patient": visit.patient},
    )


@login_required
@require_POST
def message_send(request, pk):
    doctor = request.user.doctor_profile
    visit = _get_visit_or_404_for(doctor, pk)
    content = (request.POST.get("content") or "").strip()
    if content:
        VisitMessage.objects.create(visit=visit, role="doctor", content=content)
        messages.info(
            request,
            "Message saved. AI answers over your ingested documents arrive "
            "in the next iteration (RAG generation).",
        )
    return redirect("visits:visit_detail", pk=visit.pk)
