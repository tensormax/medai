from django.contrib import admin

from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["full_name", "mrn", "doctor"]
    search_fields = ["full_name", "mrn"]
