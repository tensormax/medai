from django.urls import path

from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("create/", views.task_create, name="task_create"),
    path("<int:pk>/", views.task_update, name="task_update"),
    path("<int:pk>/complete/", views.task_complete, name="task_complete"),
]
