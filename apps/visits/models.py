from django.db import models

from apps.accounts.models import Doctor
from apps.patients.models import Patient


class Visit(models.Model):
    """
    A single timeline entry for a patient — the clinical encounter.
    A Patient has many Visits; a Visit has many VisitMessages.
    """

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
    ]

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="visits"
    )
    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="visits"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    summary = models.TextField(
        blank=True, help_text="Short auto-generated summary of this visit"
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Visit for {self.patient.full_name} on {self.started_at:%d/%m/%Y}"


class VisitMessage(models.Model):
    """
    One turn within a Visit — what used to be called a 'chat message'.
    """

    ROLE_CHOICES = [
        ("doctor", "Doctor"),
        ("ai", "AI"),
    ]

    visit = models.ForeignKey(
        Visit, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role} message in visit #{self.visit_id}"
