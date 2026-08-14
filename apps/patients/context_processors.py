from datetime import date

from django.utils import timezone
from datetime import timedelta


def sidebar_patients(request):
    """Inject the doctor's patients into every template context for the sidebar."""
    if not request.user.is_authenticated:
        return {}

    doctor = getattr(request.user, "doctor_profile", None)
    if not doctor:
        return {}

    from apps.patients.models import Patient

    patients = (
        Patient.objects.filter(doctor=doctor)
        .prefetch_related("visits")
        .order_by("full_name")
    )

    now = timezone.now()
    week_ago = now - timedelta(days=7)

    patient_data = []
    for p in patients:
        latest_visit = p.visits.order_by("-started_at").first()
        has_open_visit = p.visits.filter(status="open").exists()

        # Status: green = recent visit (<7d), orange = open visit, gray = no visits
        if has_open_visit:
            status_color = "orange"
        elif latest_visit and latest_visit.started_at >= week_ago:
            status_color = "green"
        else:
            status_color = "gray"

        # Age
        today = date.today()
        age_years = (
            today.year
            - p.date_of_birth.year
            - ((today.month, today.day) < (p.date_of_birth.month, p.date_of_birth.day))
        )

        # Last visit summary
        if latest_visit:
            last_visit_text = latest_visit.summary or f"Visit {latest_visit.started_at.strftime('%d/%m/%Y')}"
        else:
            last_visit_text = "No visits yet"

        patient_data.append({
            "id": p.pk,
            "full_name": p.full_name,
            "mrn": p.mrn,
            "age": age_years,
            "last_visit_text": last_visit_text,
            "status_color": status_color,
        })

    # Determine active patient from URL
    active_patient_id = None
    match = getattr(request, "resolver_match", None)
    if match and match.app_name == "patients" and match.kwargs:
        active_patient_id = match.kwargs.get("pk")

    return {
        "sidebar_patients": patient_data,
        "active_patient_id": active_patient_id,
    }
