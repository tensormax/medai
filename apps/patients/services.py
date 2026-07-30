from apps.accounts.models import Doctor

from .models import Patient


def get_patients_for(doctor: Doctor):
    return Patient.objects.filter(doctor=doctor)


def get_patient_or_404_for(doctor: Doctor, patient_pk: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Patient, doctor=doctor, pk=patient_pk)
