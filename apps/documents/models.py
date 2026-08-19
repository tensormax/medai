from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.patients.models import Patient
from apps.visits.models import Visit


class Document(models.Model):
    """
    Covers BOTH report features:
      - kind='uploaded'  -> doctor uploaded an MRI/CT/lab report (Feature B input)
      - kind='generated' -> system produced an automated report (Feature A output)

    patient is required (always resolvable without a join).
    visit is optional (null when the document predates any visit,
    e.g. bulk historical uploads during onboarding).
    """

    KIND_CHOICES = [
        ("uploaded", "Uploaded"),
        ("generated", "Generated"),
    ]
    DOC_TYPE_CHOICES = [
        ("mri", "MRI"),
        ("ct", "CT Scan"),
        ("lab", "Lab Report"),
        ("prescription", "Prescription"),
        ("report", "Generated Report"),
        ("other", "Other"),
    ]
    PROCESSING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="documents"
    )
    visit = models.ForeignKey(
        Visit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default="other")
    file = models.FileField(upload_to="patient_docs/%Y/%m/", blank=True, null=True)
    title = models.CharField(max_length=255, blank=True)
    de_identified = models.BooleanField(default=False)
    processing_status = models.CharField(
        max_length=12,
        choices=PROCESSING_STATUS_CHOICES,
        default="pending",
    )
    chunk_count = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.get_kind_display()} document for {self.patient.full_name}"


class DocumentChunk(models.Model):
    """
    Text chunks used for the RAG pipeline (Feature B). The actual vector
    lives in the external vector store — embedding_id is a pointer kept
    here for traceability so an analysis can cite which chunk it came from.

    patient is denormalized from document.patient for efficient vector
    store queries without joins.
    """

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="chunks"
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="chunks",
        null=True,
        blank=True,
        help_text="Denormalized from document.patient for vector store queries",
    )
    chunk_text = models.TextField()
    embedding_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Pointer into the external vector store",
    )
    embedding = VectorField(
        dimensions=settings.EMBEDDING_DIMENSIONS,
        null=True,
        blank=True,
        help_text="pgvector embedding for semantic search",
    )
    chunk_index = models.PositiveIntegerField(default=0)
    page_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Source page number in the original PDF",
    )
    section = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Clinical section heading (e.g. Laboratory Results)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]

    def __str__(self):
        page = f" p.{self.page_number}" if self.page_number else ""
        section = f" [{self.section}]" if self.section else ""
        return (
            f"Chunk {self.chunk_index}{section}{page} "
            f"of document #{self.document_id}"
        )


class DocumentAnalysis(models.Model):
    """
    Renamed from DocumentSummary — broader on purpose. Covers today's
    summaries plus future trend/risk outputs, and also holds Feature A's
    generated-report content (json + rendered html + final pdf).
    """

    ANALYSIS_TYPE_CHOICES = [
        ("summary", "Summary"),
        ("trend", "Trend Analysis"),
        ("risk", "Risk Assessment"),
        ("generated_report", "Generated Report Content"),
    ]

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="analyses"
    )
    analysis_type = models.CharField(
        max_length=20, choices=ANALYSIS_TYPE_CHOICES, default="summary"
    )
    prompt_used = models.TextField(blank=True)
    llm_response_json = models.JSONField(default=dict, blank=True)
    rendered_html = models.TextField(blank=True)
    pdf_file = models.FileField(
        upload_to="generated_reports/%Y/%m/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Document analyses"

    def __str__(self):
        return f"{self.get_analysis_type_display()} for document #{self.document_id}"


class GeneratedClinicalDocument(models.Model):
    """
    Stores a deterministic, doctor-requested clinical document PDF
    (consultation summary, prescription, medical certificate, referral letter).
    """

    DOC_TYPE_CHOICES = [
        ("consultation_summary", "Visit / Consultation Summary"),
        ("prescription", "Prescription"),
        ("medical_certificate", "Medical Certificate"),
        ("referral_letter", "Referral Letter"),
    ]

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="clinical_documents"
    )
    doctor = models.ForeignKey(
        "accounts.Doctor",
        on_delete=models.CASCADE,
        related_name="generated_clinical_documents",
    )
    visit = models.ForeignKey(
        Visit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clinical_documents",
    )
    document_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    form_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra form fields supplied by the doctor (medications, diagnosis, specialist, etc.)",
    )
    pdf_file = models.FileField(
        upload_to="clinical_docs/%Y/%m/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_document_type_display()} for {self.patient.full_name}"
