from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.documents.models import Document, GeneratedClinicalDocument

from .forms import PatientForm
from .services import get_patient_or_404_for, get_patients_for


@login_required
def patient_list(request):
    doctor = request.user.doctor_profile
    patients = get_patients_for(doctor)
    return render(request, "patients/patient_list.html", {"patients": patients})


@login_required
def patient_detail(request, pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, pk)
    latest_visit = patient.visits.order_by("-started_at").first()
    latest_open_visit = (
        patient.visits.filter(status="open").order_by("-started_at").first()
    )
    ai_insight = None
    if latest_open_visit:
        ai_insight = (
            latest_open_visit.messages.filter(role="ai")
            .order_by("-created_at")
            .first()
        )

    latest_summary = (
        GeneratedClinicalDocument.objects.filter(
            patient=patient, document_type="consultation_summary"
        )
        .order_by("-created_at")
        .first()
    )
    latest_rx = (
        GeneratedClinicalDocument.objects.filter(
            patient=patient, document_type="prescription"
        )
        .order_by("-created_at")
        .first()
    )

    return render(
        request,
        "patients/patient_detail.html",
        {
            "patient": patient,
            "latest_visit": latest_visit,
            "latest_open_visit": latest_open_visit,
            "ai_insight": ai_insight,
            "next_task": (
                patient.tasks.filter(status="pending").order_by("due_at").first()
            ),
            "latest_lab": (
                Document.objects.filter(
                    patient=patient, kind="uploaded", doc_type="lab"
                )
                .order_by("-uploaded_at")
                .first()
            ),
            "vital_signs": _extract_vital_signs(latest_summary, latest_rx),
        },
    )


@login_required
def patient_create(request):
    doctor = request.user.doctor_profile
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            patient.doctor = doctor
            patient.save()
            return redirect("patients:patient_detail", pk=patient.pk)
    else:
        form = PatientForm()
    return render(request, "patients/patient_form.html", {"form": form, "editing": False})


@login_required
def patient_update(request, pk):
    doctor = request.user.doctor_profile
    patient = get_patient_or_404_for(doctor, pk)
    if request.method == "POST":
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            return redirect("patients:patient_detail", pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    return render(request, "patients/patient_form.html", {"form": form, "editing": True})


def _extract_vital_signs(summary, rx):
    """Pull clinical findings from the latest consultation summary and prescription."""
    findings = {}
    if summary and summary.form_data:
        d = summary.form_data
        if d.get("diagnosis"):
            findings["diagnosis"] = d["diagnosis"]
        if d.get("medications"):
            findings["medications"] = d["medications"]
        if d.get("treatment_plan"):
            findings["treatment_plan"] = d["treatment_plan"]
        if d.get("follow_up"):
            findings["follow_up"] = d["follow_up"]
        findings["date"] = summary.created_at.strftime("%d/%m/%Y")
    if rx and rx.form_data:
        meds = rx.form_data.get("medications_json")
        if meds:
            try:
                import json as _json
                med_list = _json.loads(meds) if isinstance(meds, str) else meds
                names = [m.get("name", m.get("drug", "")) for m in med_list if m.get("name") or m.get("drug")]
                if names:
                    findings["rx_medications"] = ", ".join(names)
            except (ValueError, TypeError):
                pass
        if rx.form_data.get("notes"):
            findings["rx_notes"] = rx.form_data["notes"]
        if "date" not in findings:
            findings["date"] = rx.created_at.strftime("%d/%m/%Y")
    return findings
