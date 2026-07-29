from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Doctor


class DoctorRegistrationForm(UserCreationForm):
    full_name = forms.CharField(max_length=255)
    specialization = forms.CharField(max_length=255, required=False)
    license_number = forms.CharField(max_length=100, required=False)
    phone_number = forms.CharField(max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_license_number(self):
        value = self.cleaned_data.get("license_number")
        if value and Doctor.objects.filter(license_number=value).exists():
            raise forms.ValidationError(
                "A doctor with this license number already exists."
            )
        return value

    def save(self, commit=True):
        user = super().save(commit=commit)
        doctor = Doctor(
            user=user,
            full_name=self.cleaned_data["full_name"],
            specialization=self.cleaned_data.get("specialization", ""),
            license_number=self.cleaned_data.get("license_number") or None,
            phone_number=self.cleaned_data.get("phone_number", ""),
        )
        if commit:
            doctor.save()
        return user


class DoctorProfileForm(forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ["full_name", "specialization", "phone_number"]
