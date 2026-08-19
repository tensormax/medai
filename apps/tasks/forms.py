from django import forms

from apps.patients.models import Patient
from apps.visits.models import Visit

from .models import Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["patient", "linked_visit", "title", "notes", "due_at", "status"]
        widgets = {
            "due_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "linked_visit": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, doctor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor = doctor
        if doctor is not None:
            self.fields["patient"].queryset = Patient.objects.filter(doctor=doctor)
        self.fields["linked_visit"].required = False
        self.fields["linked_visit"].queryset = Visit.objects.none()
        if self.instance and self.instance.pk and self.instance.patient_id:
            self.fields["linked_visit"].queryset = Visit.objects.filter(
                patient=self.instance.patient, doctor=self.instance.doctor
            ).order_by("-started_at")
        patient_id = self.data.get("patient") or (self.instance.patient_id if self.instance and self.instance.pk else None)
        if patient_id:
            self.fields["linked_visit"].queryset = Visit.objects.filter(
                patient_id=patient_id, doctor=doctor
            ).order_by("-started_at")

    def clean_patient(self):
        patient = self.cleaned_data.get("patient")
        if self.doctor is not None and patient and patient.doctor_id != self.doctor.pk:
            raise forms.ValidationError(
                "You can only create tasks for your own patients."
            )
        return patient
