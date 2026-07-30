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
    return render(request, "patients/patient_detail.html", {"patient": patient})


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
