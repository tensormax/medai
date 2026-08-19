from django.urls import path

from . import views

app_name = "visits"

urlpatterns = [
    path("create/<int:patient_pk>/", views.visit_create, name="visit_create"),
    path("<int:pk>/", views.visit_detail, name="visit_detail"),
    path("<int:pk>/send/", views.message_send, name="message_send"),
    path("<int:pk>/close/", views.visit_close, name="visit_close"),
]
