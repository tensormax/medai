from apps.accounts.models import Doctor

from .models import Task


def get_tasks_for(doctor: Doctor):
    return Task.objects.filter(doctor=doctor)


def get_task_or_404_for(doctor: Doctor, task_pk: int):
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Task, doctor=doctor, pk=task_pk)
