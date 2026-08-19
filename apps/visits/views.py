from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.patients.services import get_patient_or_404_for

from .forms import VisitMessageForm
from .services import create_visit, get_visit_or_404_for, post_message


def _render_markdown(text: str) -> str:
    """Render markdown text to safe HTML (same logic as visit_extras.markdown)."""
    import html as html_mod

    import markdown as md

    if not text:
        return ""
    escaped = html_mod.escape(str(text))
    from django.utils.safestring import mark_safe

    return str(mark_safe(md.markdown(escaped, extensions=["extra"])))


@login_required
def visit_create(request, patient_pk):
    doctor = request.user.doctor_profile
    if request.method != "POST":
        return redirect("patients:patient_detail", pk=patient_pk)
    patient = get_patient_or_404_for(doctor, patient_pk)
    visit = create_visit(patient, doctor)
    return redirect("visits:visit_detail", pk=visit.pk)


@login_required
def visit_detail(request, pk):
    doctor = request.user.doctor_profile
    visit = get_visit_or_404_for(doctor, pk)
    return render(
        request,
        "visits/visit_detail.html",
        {"visit": visit, "form": VisitMessageForm()},
    )


@login_required
def message_send(request, pk):
    doctor = request.user.doctor_profile
    visit = get_visit_or_404_for(doctor, pk)
    if request.method == "POST":
        form = VisitMessageForm(request.POST)
        if form.is_valid():
            is_ajax = request.headers.get("X-Requested-With") == "fetch"
            try:
                doctor_msg, ai_msg = post_message(visit, form.cleaned_data["content"])
            except Exception as exc:
                if is_ajax:
                    return JsonResponse({"ok": False, "error": str(exc)}, status=500)
                return redirect("visits:visit_detail", pk=visit.pk)
            if is_ajax:
                from django.utils.formats import date_format

                return JsonResponse(
                    {
                        "ok": True,
                        "doctor_message": {
                            "content": doctor_msg.content,
                            "time": date_format(doctor_msg.created_at, "g:i A"),
                        },
                        "ai_message": {
                            "content": _render_markdown(ai_msg.content),
                            "time": date_format(ai_msg.created_at, "g:i A"),
                        },
                    }
                )
    return redirect("visits:visit_detail", pk=visit.pk)


@login_required
def visit_close(request, pk):
    doctor = request.user.doctor_profile
    visit = get_visit_or_404_for(doctor, pk)
    if request.method == "POST" and visit.status == "open":
        visit.status = "closed"
        visit.closed_at = timezone.now()
        visit.save(update_fields=["status", "closed_at"])
        visit.tasks.filter(status="pending").update(status="completed")
    return redirect("visits:visit_detail", pk=visit.pk)
