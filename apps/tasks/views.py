from datetime import timedelta

import json

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.documents.models import Document
from apps.patients.services import get_patient_or_404_for
from apps.visits.models import Visit

from .forms import TaskForm
from .services import get_task_or_404_for, get_tasks_for


@login_required
def dashboard(request):
    doctor = request.user.doctor_profile
    today = timezone.localdate()
    tasks = get_tasks_for(doctor)
    pending = tasks.filter(status="pending")
    context = {
        "today_tasks": pending.filter(due_at__date=today),
        "followup_tasks": pending.filter(linked_visit__isnull=False),
        "upcoming_tasks": pending.filter(due_at__date__gt=today),
        "completed_tasks": tasks.filter(status="completed"),
        "new_lab_count": Document.objects.filter(
            patient__doctor=doctor,
            kind="uploaded",
            doc_type="lab",
            uploaded_at__date__gte=today - timedelta(days=7),
        ).count(),
        "greeting": _greeting_for(timezone.localtime().hour),
    }
    return render(request, "tasks/dashboard.html", context)


def _greeting_for(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


@login_required
def task_create(request):
    doctor = request.user.doctor_profile
    if request.method == "POST":
        form = TaskForm(request.POST, doctor=doctor)
        if form.is_valid():
            task = form.save(commit=False)
            task.doctor = doctor
            task.save()
            return redirect("tasks:dashboard")
    else:
        initial = {}
        patient_pk = request.GET.get("patient")
        if patient_pk:
            try:
                initial["patient"] = get_patient_or_404_for(doctor, patient_pk)
            except Http404:
                pass
        form = TaskForm(doctor=doctor, initial=initial)
    visits = Visit.objects.filter(doctor=doctor).select_related("patient").order_by("-started_at")
    visits_json = json.dumps([{"id": v.id, "label": f"{v.patient.full_name} — {v.started_at:%d/%m/%Y}", "patient_id": v.patient_id} for v in visits])
    return render(request, "tasks/task_form.html", {"form": form, "editing": False, "visits_json": visits_json})


@login_required
def task_update(request, pk):
    doctor = request.user.doctor_profile
    task = get_task_or_404_for(doctor, pk)
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, doctor=doctor)
        if form.is_valid():
            form.save()
            return redirect("tasks:dashboard")
    else:
        form = TaskForm(instance=task, doctor=doctor)
    visits = Visit.objects.filter(doctor=doctor).select_related("patient").order_by("-started_at")
    visits_json = json.dumps([{"id": v.id, "label": f"{v.patient.full_name} — {v.started_at:%d/%m/%Y}", "patient_id": v.patient_id} for v in visits])
    return render(request, "tasks/task_form.html", {"form": form, "editing": True, "visits_json": visits_json})


@login_required
def task_complete(request, pk):
    doctor = request.user.doctor_profile
    task = get_task_or_404_for(doctor, pk)
    if request.method == "POST":
        task.status = "completed"
        task.save(update_fields=["status"])
    return redirect("tasks:dashboard")
