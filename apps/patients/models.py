from django.db import models

from apps.accounts.models import Doctor


class Patient(models.Model):
    """
    The single source of truth for a patient record. Every other app
    (visits, documents, tasks) references this via ForeignKey — nothing
    else defines its own patient identity.
    """

    SEX_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
        ("O", "Other"),
    ]

    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="patients"
    )
    full_name = models.CharField(max_length=255)
    date_of_birth = models.DateField()
    sex = models.CharField(max_length=1, choices=SEX_CHOICES)
    mrn = models.CharField(
        max_length=50, unique=True, help_text="Medical Record Number"
    )
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.mrn})"
