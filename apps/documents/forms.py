import os

from django import forms
from django.conf import settings

from .models import Document


class DocumentUploadForm(forms.ModelForm):
    """
    Upload form for Feature B input documents (kind='uploaded').
    `patient` and `kind` are never form input — the view sets them from
    the URL / constant, so a doctor can't attach a file to someone
    else's patient. The optional `visit` dropdown is scoped to the
    patient's own visits for the same reason.
    """

    class Meta:
        model = Document
        fields = ["title", "doc_type", "file", "visit"]
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "e.g. MRI Brain — 12 Aug 2026"}
            ),
        }

    def __init__(self, *args, patient=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].required = True
        allowed = ", ".join(settings.DOCUMENT_ALLOWED_EXTENSIONS)
        self.fields["file"].help_text = f"Allowed: {allowed} (max 10 MB)"
        self.fields["visit"].required = False
        if patient is not None:
            self.fields["visit"].queryset = patient.visits.all()
        else:
            self.fields["visit"].queryset = self.fields["visit"].queryset.none()

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in settings.DOCUMENT_ALLOWED_EXTENSIONS:
            allowed = ", ".join(settings.DOCUMENT_ALLOWED_EXTENSIONS)
            raise forms.ValidationError(
                f"Unsupported file type '{ext or 'unknown'}'. Allowed: {allowed}."
            )
        if file.size > settings.DOCUMENT_MAX_UPLOAD_SIZE:
            raise forms.ValidationError("File is larger than the 10 MB limit.")
        return file
