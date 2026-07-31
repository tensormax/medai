from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.patients.services import get_patient_or_404_for

from .forms import TaskForm
from .services import get_task_or_404_for, get_tasks_for


@login_required
def dashboard(request):
    doctor = request.user.doctor_profile
    today = timezone.localdate()
    tasks = get_tasks_for(doctor)
    context = {
        "today_tasks": tasks.filter(status="pending", due_at__date=today),
        "upcoming_tasks": tasks.filter(status="pending", due_at__date__gt=today),
        "completed_tasks": tasks.filter(status="completed"),
    }
    return render(request, "tasks/dashboard.html", context)


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
    return render(request, "tasks/task_form.html", {"form": form, "editing": False})


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
    return render(request, "tasks/task_form.html", {"form": form, "editing": True})


@login_required
def task_complete(request, pk):
    doctor = request.user.doctor_profile
    task = get_task_or_404_for(doctor, pk)
    if request.method == "POST":
        task.status = "completed"
        task.save(update_fields=["status"])
    return redirect("tasks:dashboard")
