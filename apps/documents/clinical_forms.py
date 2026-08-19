from django import forms

from apps.visits.models import Visit


class ConsultationSummaryForm(forms.Form):
    visit = forms.ModelChoiceField(
        queryset=Visit.objects.none(),
        label="Visit",
        help_text="Select the visit to summarise.",
    )
    diagnosis = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Assessment / diagnosis (optional).",
    )
    treatment_plan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Treatment plan (optional).",
    )
    medications = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Medications prescribed (optional).",
    )
    follow_up = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Follow-up instructions (optional).",
    )


class PrescriptionForm(forms.Form):
    """Medications are submitted as JSON in a hidden field, populated by JS."""

    medications_json = forms.CharField(
        widget=forms.HiddenInput,
        initial="[]",
        help_text="JSON array of medication objects.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Additional notes (optional).",
    )


class MedicalCertificateForm(forms.Form):
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Reason for evaluation.",
    )
    diagnosis = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Diagnosis (optional).",
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Leave start date.",
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Leave end date.",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Additional remarks (optional).",
    )


class ReferralLetterForm(forms.Form):
    specialist = forms.CharField(
        required=False,
        max_length=255,
        help_text="Referred specialist name (optional).",
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Reason for referral.",
    )
    diagnosis = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Relevant diagnosis.",
    )
    findings = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Clinical findings.",
    )
    history = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Relevant medical history.",
    )
    medications = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Current medications.",
    )
    purpose = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Requested specialist evaluation / purpose.",
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Additional notes.",
    )
