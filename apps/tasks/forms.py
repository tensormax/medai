from django import forms

from apps.patients.models import Patient

from .models import Task


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["patient", "title", "notes", "due_at", "status"]
        widgets = {
            "due_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, doctor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor = doctor
        if doctor is not None:
            self.fields["patient"].queryset = Patient.objects.filter(doctor=doctor)

    def clean_patient(self):
        patient = self.cleaned_data.get("patient")
        if self.doctor is not None and patient and patient.doctor_id != self.doctor.pk:
            raise forms.ValidationError(
                "You can only create tasks for your own patients."
            )
        return patient
