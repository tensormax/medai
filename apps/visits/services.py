from apps.ai.facade import AIOrchestrator

from .models import Visit, VisitMessage


def get_visit_or_404_for(doctor, visit_pk: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Visit, doctor=doctor, pk=visit_pk)


def create_visit(patient, doctor):
    return Visit.objects.create(patient=patient, doctor=doctor)


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
