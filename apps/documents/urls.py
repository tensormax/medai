from django.conf import settings
from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_index, name="document_index"),
    path(
        "patients/<int:patient_pk>/report/",
        views.report_generate,
        name="report_generate",
    ),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
    path(
        "reports/<int:pk>/download/",
        views.report_download,
        name="report_download",
    ),
    path(
        "reports/<int:pk>/raw/",
        views.report_raw,
        name="report_raw",
    ),
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
        "<int:pk>/analysis/",
        views.analysis_detail,
        name="analysis_detail",
    ),
    # Clinical document generation
    path(
        "patients/<int:patient_pk>/clinical/<str:doc_type>/",
        views.clinical_document_form,
        name="clinical_document_form",
    ),
    path(
        "patients/<int:patient_pk>/clinical/<str:doc_type>/generate/",
        views.clinical_document_generate,
        name="clinical_document_generate",
    ),
    path(
        "clinical/<int:pk>/view/",
        views.clinical_document_view,
        name="clinical_document_view",
    ),
    path(
        "clinical/<int:pk>/raw/",
        views.clinical_document_raw,
        name="clinical_document_raw",
    ),
    path(
        "clinical/<int:pk>/download/",
        views.clinical_document_download,
        name="clinical_document_download",
    ),
    path(
        "patients/<int:patient_pk>/clinical/",
        views.clinical_document_list,
        name="clinical_document_list",
    ),
]

if settings.DEBUG:
    urlpatterns += [
        path(
            "api/<int:pk>/chunks/",
            views.chunk_inspection,
            name="chunk_inspection",
        ),
        path(
            "api/<int:pk>/deidentification/",
            views.deidentification_inspection,
            name="deidentification_inspection",
        ),
    ]
