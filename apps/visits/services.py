from datetime import timedelta

from django.utils import timezone

from apps.ai.facade import AIOrchestrator

from .models import Visit, VisitMessage


def get_visit_or_404_for(doctor, visit_pk: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Visit, doctor=doctor, pk=visit_pk)


def create_visit(patient, doctor):
    from apps.tasks.models import Task

    visit = Visit.objects.create(patient=patient, doctor=doctor)

    previous_visits = Visit.objects.filter(patient=patient, doctor=doctor).exclude(pk=visit.pk)
    if previous_visits.exists():
        last_visit = previous_visits.order_by("-started_at").first()
        today_end = timezone.now().replace(hour=23, minute=59, second=59)
        Task.objects.create(
            doctor=doctor,
            patient=patient,
            linked_visit=last_visit,
            title=f"Follow-up — {patient.full_name}",
            notes=f"Follow-up after visit on {last_visit.started_at:%d/%m/%Y}.",
            due_at=today_end,
        )

    return visit


def post_message(visit: Visit, content: str):
    """
    Save the doctor's message, then generate the AI reply via the
    AIOrchestrator facade and save it as a second message. The doctor
    always posts role="doctor"; the reply is always role="ai".
    """
    doctor_message = VisitMessage.objects.create(
        visit=visit, role="doctor", content=content
    )
    reply_text = AIOrchestrator.generate_visit_reply(visit, content)
    ai_message = VisitMessage.objects.create(
        visit=visit, role="ai", content=reply_text
    )
    return doctor_message, ai_message
