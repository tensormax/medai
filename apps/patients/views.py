from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

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
    visits = patient.visits.all()
    latest_visit = visits.first()
    latest_open_visit = visits.filter(status="open").first()
    ai_insight = None
    if latest_visit is not None:
        from apps.visits.models import VisitMessage

        ai_insight = (
            VisitMessage.objects.filter(visit__patient=patient, role="ai")
            .select_related("visit")
            .order_by("-created_at")
            .first()
        )
    next_task = patient.tasks.filter(status="pending").order_by("due_at").first()
    latest_lab = patient.documents.filter(doc_type="lab").first()
    return render(
        request,
        "patients/patient_detail.html",
        {
            "patient": patient,
            "latest_visit": latest_visit,
            "latest_open_visit": latest_open_visit,
            "ai_insight": ai_insight,
            "next_task": next_task,
            "latest_lab": latest_lab,
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
