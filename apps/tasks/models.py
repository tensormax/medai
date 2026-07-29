from django.db import models

from apps.accounts.models import Doctor
from apps.patients.models import Patient
from apps.visits.models import Visit


class Task(models.Model):
    """
    Doctor's own dashboard item: today's tasks, upcoming follow-ups,
    completed items. Deliberately separate from Visit — this is future
    administrative time, not the clinical record itself.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
    ]

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="tasks")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="tasks")
    linked_visit = models.ForeignKey(
        Visit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        help_text="Set once this follow-up becomes an actual visit",
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    due_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at"]

    def __str__(self):
        return f"{self.title} — {self.patient.full_name}"
