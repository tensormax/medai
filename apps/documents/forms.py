from django import forms

from .models import Document


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["file", "doc_type"]
        widgets = {
            "doc_type": forms.Select(),
        }

    def clean_file(self):
        file = self.cleaned_data.get("file")
        if file:
            name = file.name.lower()
            if not (name.endswith(".txt") or name.endswith(".pdf")):
                raise forms.ValidationError("Only .txt and .pdf files are supported.")
        return file
