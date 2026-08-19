from django import forms

from .models import VisitMessage


class VisitMessageForm(forms.ModelForm):
    class Meta:
        model = VisitMessage
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Type your message..."}
            ),
        }
