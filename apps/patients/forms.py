from django import forms

from .models import Patient


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "full_name",
            "date_of_birth",
            "sex",
            "mrn",
            "phone_number",
            "address",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_mrn(self):
        value = self.cleaned_data.get("mrn")
        if not value:
            return value
        qs = Patient.objects.filter(mrn=value)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "A patient with this Medical Record Number already exists."
            )
        return value
