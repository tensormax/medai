"""
End-to-end tests for the document INGESTION pipeline (upload -> extract
-> chunk -> embed with all-MiniLM-L6-v2 -> FAISS) and the retrieval
endpoint. Generation (Feature A) is a later iteration and only has a
stub test here.

Note: these tests load the real sentence-transformer, so the first run
downloads the model (~90 MB) into the HF cache.
"""

import shutil
import tempfile
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Doctor
from apps.patients.models import Patient

from . import rag
from .models import Document, DocumentChunk

_TMP_MEDIA = Path(tempfile.mkdtemp(prefix="medai_test_media_"))
_TMP_VECTORS = Path(tempfile.mkdtemp(prefix="medai_test_vectors_"))

DUMMY_REPORT = """
PATIENT DISCHARGE SUMMARY — DEMO DATA (SYNTHETIC)

Patient: John Demo. Diagnosis: Type 2 Diabetes Mellitus, poorly controlled.
HbA1c measured at 9.1 percent, fasting blood glucose 182 mg/dL.
Blood pressure recorded at 148/92 mmHg, indicating stage 2 hypertension.
Lipid panel shows LDL cholesterol of 162 mg/dL and triglycerides 210 mg/dL.
MRI of the brain shows no acute infarct; mild chronic small vessel changes.
Plan: start metformin 500 mg twice daily, lisinopril 10 mg once daily,
atorvastatin 20 mg at night. Advise low-carbohydrate diet and 30 minutes
of daily walking. Follow up in 6 weeks with repeat HbA1c and renal panel.
"""


@override_settings(MEDIA_ROOT=_TMP_MEDIA, VECTOR_STORE_DIR=_TMP_VECTORS)
class DocumentIngestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drdemo", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Demo Doctor")
        cls.patient = Patient.objects.create(
            doctor=cls.doctor,
            full_name="John Demo",
            date_of_birth=date(1970, 5, 1),
            sex="M",
            mrn="MRN-TEST-001",
        )
        other_user = User.objects.create_user("other", password="pass12345")
        cls.other_doctor = Doctor.objects.create(
            user=other_user, full_name="Other Doctor"
        )

    def setUp(self):
        rag.vector_store.reset()
        for f in _TMP_VECTORS.glob("*"):
            f.unlink()
        self.client.login(username="drdemo", password="pass12345")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP_MEDIA, ignore_errors=True)
        shutil.rmtree(_TMP_VECTORS, ignore_errors=True)

    def _upload(self, filename="report.txt", content=DUMMY_REPORT):
        return self.client.post(
            reverse("documents:document_upload", kwargs={"patient_pk": self.patient.pk}),
            {
                "title": "Discharge summary",
                "doc_type": "lab",
                "file": SimpleUploadedFile(filename, content.encode("utf-8")),
            },
        )

    def test_upload_ingests_and_indexes(self):
        response = self._upload()
        document = Document.objects.get()
        self.assertRedirects(
            response, reverse("documents:document_detail", kwargs={"pk": document.pk})
        )
        self.assertEqual(document.kind, "uploaded")
        chunks = document.chunks.all()
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertEqual(chunk.embedding_id, f"faiss:{chunk.pk}")
        self.assertEqual(rag.vector_store.count(), len(chunks))

    def test_list_detail_render_ok(self):
        self._upload()
        document = Document.objects.get()
        list_url = reverse(
            "documents:document_list", kwargs={"patient_pk": self.patient.pk}
        )
        self.assertEqual(self.client.get(list_url).status_code, 200)
        detail_url = reverse("documents:document_detail", kwargs={"pk": document.pk})
        self.assertEqual(self.client.get(detail_url).status_code, 200)

    def test_semantic_search_returns_relevant_chunk(self):
        self._upload()
        url = reverse(
            "documents:document_search", kwargs={"patient_pk": self.patient.pk}
        )
        response = self.client.get(url, {"q": "diabetes blood sugar control"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["results"], "expected at least one retrieved chunk")
        self.assertIn("HbA1c", data["results"][0]["text"])

    def test_search_requires_query(self):
        url = reverse(
            "documents:document_search", kwargs={"patient_pk": self.patient.pk}
        )
        self.assertEqual(self.client.get(url).status_code, 400)

    def test_rejects_unsupported_extension(self):
        response = self._upload(filename="scan.exe")
        self.assertEqual(response.status_code, 200)  # form re-rendered with error
        self.assertEqual(Document.objects.count(), 0)

    def test_delete_removes_chunks_and_vectors(self):
        self._upload()
        document = Document.objects.get()
        self.client.post(
            reverse("documents:document_delete", kwargs={"pk": document.pk})
        )
        self.assertEqual(Document.objects.count(), 0)
        self.assertEqual(DocumentChunk.objects.count(), 0)
        self.assertEqual(rag.vector_store.count(), 0)

    def test_other_doctor_cannot_see_document(self):
        self._upload()
        document = Document.objects.get()
        self.client.login(username="other", password="pass12345")
        detail_url = reverse("documents:document_detail", kwargs={"pk": document.pk})
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        list_url = reverse(
            "documents:document_list", kwargs={"patient_pk": self.patient.pk}
        )
        self.assertEqual(self.client.get(list_url).status_code, 404)

    def test_report_generate_is_stubbed_for_next_iteration(self):
        response = self.client.post(
            reverse(
                "documents:report_generate", kwargs={"patient_pk": self.patient.pk}
            )
        )
        self.assertRedirects(
            response, reverse("patients:patient_detail", kwargs={"pk": self.patient.pk})
        )
