from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path(
        "patients/<int:patient_pk>/documents/",
        views.document_list,
        name="document_list",
    ),
    path(
        "patients/<int:patient_pk>/documents/upload/",
        views.document_upload,
        name="document_upload",
    ),
    path(
        "patients/<int:patient_pk>/documents/search/",
        views.document_search,
        name="document_search",
    ),
    path(
        "patients/<int:patient_pk>/report/generate/",
        views.report_generate,
        name="report_generate",
    ),
    path("documents/<int:pk>/", views.document_detail, name="document_detail"),
    path("documents/<int:pk>/delete/", views.document_delete, name="document_delete"),
]
