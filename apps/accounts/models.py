from django.conf import settings
from django.db import models


class Doctor(models.Model):
    """
    Extends the built-in User model. Only doctors register/authenticate
    in this system — there is no separate patient-facing account.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    full_name = models.CharField(max_length=255)
    specialization = models.CharField(max_length=255, blank=True)
    license_number = models.CharField(max_length=100, unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"Dr. {self.full_name}"
