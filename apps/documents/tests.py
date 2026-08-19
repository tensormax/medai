"""
Phase 2 tests: PDF ingestion RAG pipeline.

Tests cover:
- successful PDF extraction
- invalid/empty PDF handling
- page preservation
- section preservation where available
- no empty chunks
- chunk metadata
- deterministic processing
- upload flow integration
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

from .models import Document, DocumentChunk

_TMP_MEDIA = Path(tempfile.mkdtemp(prefix="medai_test_media_"))

# ── PDF generators using fpdf2 ─────────────────────────────────────

def _make_pdf(text: str) -> bytes:
    """Create a minimal single-page PDF containing the given text."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    return pdf.output()


def _make_multipage_pdf(pages_text: list[str]) -> bytes:
    """Create a multi-page PDF with one page per string."""
    from fpdf import FPDF

    pdf = FPDF()
    for text in pages_text:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 10, text)
    return pdf.output()


# ── Clinical document text for testing ──────────────────────────────

CLINICAL_DOCUMENT = """\
PATIENT DISCHARGE SUMMARY

Patient: John Demo. Diagnosis: Type 2 Diabetes Mellitus, poorly controlled.
HbA1c measured at 9.1 percent, fasting blood glucose 182 mg/dL.
Blood pressure recorded at 148/92 mmHg, indicating stage 2 hypertension.
Lipid panel shows LDL cholesterol of 162 mg/dL and triglycerides 210 mg/dL.

Vital Signs:
Temperature: 98.6 F
Heart Rate: 78 bpm
Blood Pressure: 148/92 mmHg
Respiratory Rate: 16 breaths/min

Laboratory Results:
HbA1c: 9.1%
Fasting Blood Glucose: 182 mg/dL
LDL Cholesterol: 162 mg/dL
Triglycerides: 210 mg/dL
Creatinine: 1.1 mg/dL
eGFR: 72 mL/min/1.73m2

Assessment:
Type 2 Diabetes Mellitus, poorly controlled
Stage 2 Hypertension
Hyperlipidemia

Plan:
Start metformin 500 mg twice daily
Start lisinopril 10 mg once daily
Start atorvastatin 20 mg at night
Advise low-carbohydrate diet
30 minutes of daily walking
Follow up in 6 weeks with repeat HbA1c and renal panel
"""


# ── Chunking unit tests ─────────────────────────────────────────────

class ChunkingTests(TestCase):
    """Direct tests for apps.ai.chunking module."""

    def test_extract_pages_returns_page_objects(self):
        from apps.ai.chunking import PageText, extract_pages

        pdf = _make_pdf("Hello World")
        pages = extract_pages(pdf)
        self.assertEqual(len(pages), 1)
        self.assertIsInstance(pages[0], PageText)
        self.assertEqual(pages[0].page_number, 1)
        self.assertIn("Hello World", pages[0].text)

    def test_multipage_pdf_preserves_page_numbers(self):
        from apps.ai.chunking import extract_pages

        pdf = _make_multipage_pdf(["Page one content", "Page two content", "Page three content"])
        pages = extract_pages(pdf)
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0].page_number, 1)
        self.assertEqual(pages[1].page_number, 2)
        self.assertEqual(pages[2].page_number, 3)

    def test_extract_pages_empty_pdf(self):
        from apps.ai.chunking import extract_pages

        pdf = _make_pdf("")
        pages = extract_pages(pdf)
        self.assertEqual(len(pages), 1)

    def test_extract_pages_invalid_pdf(self):
        from apps.ai.chunking import PDFExtractionError, extract_pages

        with self.assertRaises(PDFExtractionError):
            extract_pages(b"not a pdf at all")

    def test_chunk_document_returns_chunk_results(self):
        from apps.ai.chunking import ChunkResult, PageText, chunk_document

        pages = [PageText(page_number=1, text="Simple test document")]
        chunks = chunk_document(pages)
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertIsInstance(chunk, ChunkResult)

    def test_no_empty_chunks(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [PageText(page_number=1, text=CLINICAL_DOCUMENT)]
        chunks = chunk_document(pages)
        for chunk in chunks:
            self.assertTrue(
                chunk.text.strip(),
                f"Chunk {chunk.chunk_index} is empty",
            )

    def test_chunk_indices_are_sequential(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [PageText(page_number=1, text=CLINICAL_DOCUMENT)]
        chunks = chunk_document(pages)
        indices = [c.chunk_index for c in chunks]
        expected = list(range(len(chunks)))
        self.assertEqual(indices, expected)

    def test_section_detection_in_clinical_text(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [PageText(page_number=1, text=CLINICAL_DOCUMENT)]
        chunks = chunk_document(pages)
        sections = {c.section for c in chunks}
        # Should detect at least some clinical sections
        self.assertTrue(
            len(sections) > 1,
            f"Expected multiple sections, got: {sections}",
        )

    def test_section_metadata_preserved(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [PageText(page_number=1, text=CLINICAL_DOCUMENT)]
        chunks = chunk_document(pages)
        for chunk in chunks:
            self.assertIsInstance(chunk.section, str)
            self.assertTrue(len(chunk.section) > 0)

    def test_page_number_preserved_in_chunks(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [
            PageText(page_number=1, text="Vital Signs:\nBP 120/80"),
            PageText(page_number=2, text="Lab Results:\nHbA1c 7.0"),
        ]
        chunks = chunk_document(pages)
        page_numbers = {c.page_number for c in chunks}
        self.assertIn(1, page_numbers)
        self.assertIn(2, page_numbers)

    def test_multipage_chunking_preserves_page_numbers(self):
        from apps.ai.chunking import extract_pages

        pdf = _make_multipage_pdf([
            "Vital Signs:\nBP 120/80",
            "Lab Results:\nHbA1c 7.0",
        ])
        pages = extract_pages(pdf)
        from apps.ai.chunking import chunk_document

        chunks = chunk_document(pages)
        self.assertGreater(len(chunks), 0)
        for chunk in chunks:
            self.assertIn(chunk.page_number, [1, 2])

    def test_deterministic_processing(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [PageText(page_number=1, text=CLINICAL_DOCUMENT)]
        chunks1 = chunk_document(pages)
        chunks2 = chunk_document(pages)
        self.assertEqual(len(chunks1), len(chunks2))
        for c1, c2 in zip(chunks1, chunks2):
            self.assertEqual(c1.text, c2.text)
            self.assertEqual(c1.page_number, c2.page_number)
            self.assertEqual(c1.section, c2.section)
            self.assertEqual(c1.chunk_index, c2.chunk_index)

    def test_empty_pages_produce_no_chunks(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [
            PageText(page_number=1, text=""),
            PageText(page_number=2, text="   "),
            PageText(page_number=3, text="\n\n\n"),
        ]
        chunks = chunk_document(pages)
        self.assertEqual(len(chunks), 0)

    def test_long_sections_are_split(self):
        from apps.ai.chunking import PageText, chunk_document

        long_text = "This is a sentence about diabetes. " * 50
        pages = [PageText(page_number=1, text=long_text)]
        chunks = chunk_document(pages, chunk_size=200, chunk_overlap=20)
        self.assertGreater(len(chunks), 1)

    def test_short_text_single_chunk(self):
        from apps.ai.chunking import PageText, chunk_document

        pages = [PageText(page_number=1, text="Short text.")]
        chunks = chunk_document(pages)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Short text.", chunks[0].text)


# ── Normalization tests ─────────────────────────────────────────────

class NormalizationTests(TestCase):
    def test_excessive_whitespace_collapsed(self):
        from apps.ai.chunking import normalize_text

        text = "Hello    world   there"
        result = normalize_text(text)
        self.assertEqual(result, "Hello world there")

    def test_excessive_blank_lines_collapsed(self):
        from apps.ai.chunking import normalize_text

        text = "Line 1\n\n\n\n\nLine 2"
        result = normalize_text(text)
        self.assertNotIn("\n\n\n", result)

    def test_empty_text(self):
        from apps.ai.chunking import normalize_text

        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text("   "), "")

    def test_no_clinical_content_altered(self):
        from apps.ai.chunking import normalize_text

        text = "HbA1c: 9.1%\nBP: 148/92 mmHg"
        result = normalize_text(text)
        self.assertIn("HbA1c: 9.1%", result)
        self.assertIn("BP: 148/92 mmHg", result)


# ── Section detection tests ─────────────────────────────────────────

class SectionDetectionTests(TestCase):
    def test_known_sections_detected(self):
        from apps.ai.chunking import PageText, detect_sections

        text = (
            "Some intro text\n"
            "Vital Signs:\n"
            "BP 120/80\n"
            "HR 72\n"
            "Laboratory Results:\n"
            "HbA1c 7.0\n"
            "Assessment:\n"
            "Diabetes mellitus\n"
        )
        pages = [PageText(page_number=1, text=text)]
        sections = detect_sections(pages)
        names = [s.name for s in sections]
        self.assertIn("Vital Signs", names)
        self.assertIn("Laboratory Results", names)
        self.assertIn("Assessment", names)

    def test_no_sections_returns_untitled(self):
        from apps.ai.chunking import PageText, detect_sections

        pages = [PageText(page_number=1, text="Just some plain text without headers.")]
        sections = detect_sections(pages)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].name, "Untitled")

    def test_section_page_tracking(self):
        from apps.ai.chunking import PageText, detect_sections

        pages = [
            PageText(page_number=1, text="Intro text\nVital Signs:\nBP normal"),
            PageText(page_number=2, text="More vitals\nLab Results:\nHbA1c 6.5"),
        ]
        sections = detect_sections(pages)
        self.assertTrue(len(sections) >= 1)
        # At least one section should start on page 1
        page1_sections = [s for s in sections if s.start_page == 1]
        self.assertTrue(len(page1_sections) >= 1)

    def test_numbered_sections_detected(self):
        from apps.ai.chunking import PageText, detect_sections

        text = "1. Vital Signs\nBP 120/80\n2. Lab Results\nHbA1c 7.0"
        pages = [PageText(page_number=1, text=text)]
        sections = detect_sections(pages)
        names = [s.name for s in sections]
        self.assertIn("Vital Signs", names)
        self.assertIn("Lab Results", names)


# ── Service-level tests ─────────────────────────────────────────────

@override_settings(MEDIA_ROOT=_TMP_MEDIA)
class DocumentIngestionTests(TestCase):
    """Integration tests for the document upload and processing pipeline."""

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

    def setUp(self):
        self.client.login(username="drdemo", password="pass12345")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP_MEDIA, ignore_errors=True)

    def _upload_txt(self, filename="report.txt", content=None):
        if content is None:
            content = CLINICAL_DOCUMENT
        return self.client.post(
            reverse("documents:document_upload", kwargs={"patient_pk": self.patient.pk}),
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(filename, content.encode("utf-8")),
            },
        )

    def _upload_pdf(self, filename="report.pdf", text=None):
        if text is None:
            text = "Vital Signs:\nBP 120/80\n\nLab Results:\nHbA1c 7.0"
        pdf_bytes = _make_pdf(text)
        return self.client.post(
            reverse("documents:document_upload", kwargs={"patient_pk": self.patient.pk}),
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(filename, pdf_bytes),
            },
        )

    def test_txt_upload_creates_chunks(self):
        self._upload_txt()
        document = Document.objects.get()
        self.assertEqual(document.processing_status, "completed")
        self.assertGreater(document.chunk_count, 0)
        chunks = document.chunks.all()
        self.assertEqual(len(chunks), document.chunk_count)

    def test_pdf_upload_creates_chunks(self):
        self._upload_pdf()
        document = Document.objects.get()
        self.assertEqual(document.processing_status, "completed")
        self.assertGreater(document.chunk_count, 0)

    def test_chunks_have_metadata(self):
        self._upload_pdf()
        document = Document.objects.get()
        chunks = document.chunks.all()
        for chunk in chunks:
            self.assertIsNotNone(chunk.page_number)
            self.assertIsInstance(chunk.section, str)
            self.assertEqual(chunk.patient, self.patient)

    def test_empty_file_fails(self):
        self._upload_txt(filename="empty.txt", content="")
        self.assertEqual(Document.objects.filter(processing_status="completed").count(), 0)

    def test_whitespace_only_fails(self):
        self._upload_txt(filename="blank.txt", content="   \n\n   ")
        doc = Document.objects.first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.processing_status, "failed")

    def test_rejects_unsupported_extension(self):
        response = self._upload_txt(filename="scan.exe")
        self.assertEqual(response.status_code, 200)  # form re-rendered
        self.assertEqual(Document.objects.count(), 0)

    def test_upload_redirects_to_chunk_inspection(self):
        response = self._upload_pdf()
        document = Document.objects.get()
        self.assertRedirects(
            response,
            reverse("documents:chunk_inspection", kwargs={"pk": document.pk}),
        )

    def test_chunk_inspection_view_renders(self):
        self._upload_pdf()
        document = Document.objects.get()
        url = reverse("documents:chunk_inspection", kwargs={"pk": document.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chunk Inspection")

    def test_chunks_deterministic(self):
        content = CLINICAL_DOCUMENT
        self._upload_txt(filename="a.txt", content=content)
        doc1 = Document.objects.get()

        self._upload_txt(filename="b.txt", content=content)
        doc2 = Document.objects.exclude(pk=doc1.pk).get()

        chunks1 = list(doc1.chunks.values("chunk_text", "section", "page_number"))
        chunks2 = list(doc2.chunks.values("chunk_text", "section", "page_number"))
        self.assertEqual(chunks1, chunks2)

    def test_document_list_renders(self):
        url = reverse("documents:document_list", kwargs={"patient_pk": self.patient.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_other_doctor_cannot_see_chunks(self):
        self._upload_pdf()
        document = Document.objects.get()
        other_user = User.objects.create_user("other", password="pass12345")
        Doctor.objects.create(user=other_user, full_name="Other Doctor")
        self.client.login(username="other", password="pass12345")
        url = reverse("documents:chunk_inspection", kwargs={"pk": document.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_de_identified_flag_set_after_upload(self):
        self._upload_txt()
        document = Document.objects.get()
        self.assertTrue(document.de_identified)

    def test_deidentification_inspection_renders(self):
        self._upload_txt()
        document = Document.objects.get()
        url = reverse("documents:deidentification_inspection", kwargs={"pk": document.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "De-identification Inspection")


# ── De-identification unit tests ────────────────────────────────────

class DeidentificationTests(TestCase):
    """Tests for apps.ai.deidentify module."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drdi", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. Di")
        cls.patient = Patient.objects.create(
            doctor=cls.doctor,
            full_name="John Smith",
            date_of_birth=date(1985, 3, 15),
            sex="M",
            mrn="MRN-DEID-001",
            phone_number="0300-1234567",
            address="10 Example Street, Lahore",
        )

    def test_name_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("John Smith presented to clinic.", self.patient)
        self.assertNotIn("John Smith", result)
        self.assertIn("[PATIENT_NAME]", result)

    def test_mrn_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("MRN: MRN-DEID-001", self.patient)
        self.assertNotIn("MRN-DEID-001", result)
        self.assertIn("[MRN]", result)

    def test_dob_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("DOB: 1985-03-15", self.patient)
        self.assertNotIn("1985-03-15", result)
        self.assertIn("[DOB]", result)

    def test_phone_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("Call 0300-1234567 for appointment.", self.patient)
        self.assertNotIn("0300-1234567", result)
        self.assertIn("[PHONE]", result)

    def test_address_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("Lives at 10 Example Street, Lahore.", self.patient)
        self.assertNotIn("10 Example Street, Lahore", result)
        self.assertIn("[ADDRESS]", result)

    def test_repeated_name_consistent(self):
        from apps.ai.deidentify import deidentify

        text = (
            "John Smith presented on 14/08/2026.\n"
            "Mr. Smith was prescribed medication.\n"
            "John Smith returned for follow-up."
        )
        result = deidentify(text, self.patient)
        self.assertNotIn("John", result)
        self.assertNotIn("Smith", result)
        self.assertNotIn("John Smith", result)

    def test_clinical_text_preserved(self):
        from apps.ai.deidentify import deidentify

        text = (
            "John Smith has HbA1c of 9.1%.\n"
            "Blood pressure is 148/92 mmHg.\n"
            "Plan: start metformin 500mg BD."
        )
        result = deidentify(text, self.patient)
        self.assertIn("HbA1c of 9.1%", result)
        self.assertIn("148/92 mmHg", result)
        self.assertIn("metformin 500mg BD", result)

    def test_original_patient_unchanged(self):
        from apps.ai.deidentify import deidentify

        deidentify("John Smith text", self.patient)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.full_name, "John Smith")
        self.assertEqual(self.patient.mrn, "MRN-DEID-001")
        self.assertEqual(self.patient.phone_number, "0300-1234567")
        self.assertEqual(self.patient.address, "10 Example Street, Lahore")

    def test_empty_text(self):
        from apps.ai.deidentify import deidentify

        self.assertEqual(deidentify("", self.patient), "")
        self.assertEqual(deidentify("   ", self.patient), "   ")

    def test_no_phi_unchanged(self):
        from apps.ai.deidentify import deidentify

        text = "HbA1c: 9.1%. Blood pressure 148/92 mmHg. Start metformin."
        result = deidentify(text, self.patient)
        self.assertEqual(result, text)

    def test_presidio_detects_dates(self):
        from apps.ai.deidentify import detect_phi

        text = "Patient seen on 14 August 2026 for routine checkup."
        entities = detect_phi(text)
        date_entities = [e for e in entities if e["entity_type"] == "DATE_TIME"]
        self.assertTrue(len(date_entities) > 0, "Expected at least one DATE_TIME entity")

    def test_presidio_detects_names(self):
        from apps.ai.deidentify import detect_phi

        text = "Dr. Sarah Johnson reviewed the MRI results."
        entities = detect_phi(text)
        person_entities = [e for e in entities if e["entity_type"] == "PERSON"]
        self.assertTrue(len(person_entities) > 0, "Expected at least one PERSON entity")

    def test_presidio_detects_emails(self):
        from apps.ai.deidentify import detect_phi

        text = "Contact the patient at john@example.com for follow-up."
        entities = detect_phi(text)
        email_entities = [e for e in entities if e["entity_type"] == "EMAIL_ADDRESS"]
        self.assertTrue(len(email_entities) > 0, "Expected at least one EMAIL entity")

    def test_presidio_detects_phones(self):
        from apps.ai.deidentify import detect_phi

        text = "Call the patient at (555) 123-4567 for appointment."
        entities = detect_phi(text)
        phone_entities = [e for e in entities if e["entity_type"] == "PHONE_NUMBER"]
        self.assertTrue(len(phone_entities) > 0, "Expected at least one PHONE entity")

    def test_upload_chunks_are_deidentified(self):
        """Verify that chunks stored in DB contain no original patient name."""
        user = User.objects.create_user("drdeidtest", password="pass12345")
        doctor = Doctor.objects.create(user=user, full_name="Dr. DeID Test")
        patient = Patient.objects.create(
            doctor=doctor,
            full_name="Alice Wonder",
            date_of_birth=date(1990, 7, 4),
            sex="F",
            mrn="MRN-DEID-002",
            phone_number="555-9876",
            address="42 Fantasy Lane",
        )

        self.client.login(username="drdeidtest", password="pass12345")
        content = (
            "Patient: Alice Wonder\n"
            "Phone: 555-9876\n"
            "Address: 42 Fantasy Lane\n"
            "MRN: MRN-DEID-002\n"
            "DOB: 1990-07-04\n"
            "HbA1c: 8.5%. Plan: metformin."
        )
        self.client.post(
            reverse("documents:document_upload", kwargs={"patient_pk": patient.pk}),
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile("test.txt", content.encode("utf-8")),
            },
        )
        document = Document.objects.get()
        all_text = " ".join(document.chunks.values_list("chunk_text", flat=True))
        self.assertNotIn("Alice Wonder", all_text)
        self.assertNotIn("MRN-DEID-002", all_text)
        self.assertNotIn("555-9876", all_text)
        self.assertNotIn("42 Fantasy Lane", all_text)
        self.assertNotIn("1990-07-04", all_text)
        self.assertIn("HbA1c: 8.5%", all_text)
        self.assertIn("metformin", all_text)

    def test_mrn_pattern_in_text_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("MRN: 88213947 assigned today.", self.patient)
        self.assertNotIn("88213947", result)
        self.assertIn("[MRN]", result)

    def test_encounter_number_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("Encounter ENC-2025-114402 documented.", self.patient)
        self.assertNotIn("ENC-2025-114402", result)
        self.assertIn("[ENCOUNTER_NUM]", result)

    def test_email_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("Contact: patient@hospital.com for follow-up.", self.patient)
        self.assertNotIn("patient@hospital.com", result)
        self.assertIn("[EMAIL]", result)

    def test_zip_code_replaced(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("Located in Columbus, OH 43215.", self.patient)
        self.assertNotIn("43215", result)
        self.assertIn("[ZIP]", result)

    def test_blood_pressure_preserved(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("BP 148/92 mmHg. HR 78 bpm.", self.patient)
        self.assertIn("148/92", result)
        self.assertIn("78 bpm", result)

    def test_lab_values_preserved(self):
        from apps.ai.deidentify import deidentify

        text = "HbA1c: 9.2%. Glucose: 186 mg/dL. LDL: 142 mg/dL."
        result = deidentify(text, self.patient)
        self.assertIn("9.2%", result)
        self.assertIn("186 mg/dL", result)
        self.assertIn("142 mg/dL", result)

    def test_temperature_preserved(self):
        from apps.ai.deidentify import deidentify

        result = deidentify("Temp 98.6F, SpO2 97%.", self.patient)
        self.assertIn("98.6F", result)

    def test_other_person_names_replaced(self):
        from apps.ai.deidentify import deidentify

        text = "Dr. Priya Ramanathan reviewed the MRI results."
        result = deidentify(text, self.patient)
        self.assertNotIn("Priya Ramanathan", result)
        self.assertIn("[PERSON]", result)

    def test_detect_phi_and_anonymize_use_same_entities(self):
        from apps.ai.deidentify import detect_phi, _DETECT_ENTITIES

        text = "Call (555) 123-4567 or email test@example.com."
        entities = detect_phi(text)
        detected_types = {e["entity_type"] for e in entities}
        for etype in detected_types:
            self.assertIn(
                etype,
                _DETECT_ENTITIES,
                f"Entity {etype} detected but not in _DETECT_ENTITIES",
            )

class VectorStoreTests(TestCase):
    """Tests for apps.ai.vectorstore (pgvector-backed)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drvec", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. Vec")
        cls.patient = Patient.objects.create(
            doctor=cls.doctor,
            full_name="Vector Patient",
            date_of_birth=date(1990, 1, 1),
            sex="M",
            mrn="MRN-VEC-001",
        )

    def _create_doc(self, title="test"):
        return Document.objects.create(
            patient=self.patient,
            kind="uploaded",
            doc_type="lab",
            title=title,
            de_identified=True,
        )

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_upsert_creates_chunks_with_embeddings(self):
        from apps.ai.vectorstore import upsert

        document = self._create_doc("upsert test")
        fake_vectors = [[0.1] * 384, [0.2] * 384]
        chunk_texts = ["chunk one text", "chunk two text"]

        ids = upsert(
            document_id=document.pk,
            chunks=chunk_texts,
            vectors=fake_vectors,
        )

        self.assertEqual(len(ids), 2)
        chunks = DocumentChunk.objects.filter(
            document=document
        ).order_by("chunk_index")
        self.assertEqual(chunks.count(), 2)
        self.assertIsNotNone(chunks[0].embedding)
        self.assertEqual(chunks[0].chunk_text, "chunk one text")
        self.assertEqual(chunks[1].chunk_text, "chunk two text")

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_query_returns_similar_chunks(self):
        from unittest.mock import patch

        from apps.ai.vectorstore import query, upsert

        document = self._create_doc("query test")
        fake_vectors = [[0.1] * 384, [0.2] * 384, [0.3] * 384]
        chunk_texts = ["chest pain history", "diabetes medication", "headache report"]
        upsert(document_id=document.pk, chunks=chunk_texts, vectors=fake_vectors)

        with patch("apps.ai.vectorstore.embed_chunks", return_value=[[0.1] * 384]):
            results = query(
                document_id=document.pk, query_text="chest pain", k=2
            )
        self.assertTrue(0 < len(results) <= 2)

    @override_settings(RAG_EMBEDDINGS_ENABLED=False)
    def test_disabled_raises_error(self):
        from apps.ai.embeddings import EmbeddingUnavailableError
        from apps.ai.vectorstore import upsert, query

        with self.assertRaises(EmbeddingUnavailableError):
            upsert(document_id=1, chunks=["text"], vectors=[[0.0] * 384])
        with self.assertRaises(EmbeddingUnavailableError):
            query(document_id=1, query_text="query", k=3)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_document_chunk_has_embedding_field(self):
        from apps.ai.vectorstore import upsert

        document = self._create_doc("embedding field test")
        upsert(
            document_id=document.pk,
            chunks=["test chunk"],
            vectors=[[0.1] * 384],
        )
        chunk = DocumentChunk.objects.filter(document=document).first()
        self.assertIsNotNone(chunk)
        self.assertIsNotNone(chunk.embedding)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_upsert_is_deterministic(self):
        from apps.ai.vectorstore import upsert

        document = self._create_doc("deterministic test")
        vectors_a = [[0.5] * 384]
        vectors_b = [[0.9] * 384]

        upsert(document_id=document.pk, chunks=["first"], vectors=vectors_a)
        upsert(document_id=document.pk, chunks=["second"], vectors=vectors_b)

        chunks = DocumentChunk.objects.filter(
            document=document
        ).order_by("chunk_index")
        self.assertEqual(chunks.count(), 1)
        self.assertEqual(chunks[0].chunk_text, "second")


class EmbeddingIntegrationTests(TestCase):
    """End-to-end tests verifying the full upload → embed → retrieve pipeline."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drembed", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. Embed")
        cls.patient = Patient.objects.create(
            doctor=cls.doctor,
            full_name="Embed Patient",
            date_of_birth=date(1990, 5, 20),
            sex="M",
            mrn="MRN-EMB-001",
            phone_number="555-0199",
            address="99 Embed Street",
        )

    def _upload(self, filename, content_str):
        self.client.login(username="drembed", password="pass12345")
        url = reverse(
            "documents:document_upload",
            kwargs={"patient_pk": self.patient.pk},
        )
        self.client.post(
            url,
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(
                    filename, content_str.encode("utf-8")
                ),
            },
        )
        return Document.objects.get()

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_upload_computes_embeddings(self):
        doc = self._upload(
            "embed_test.txt",
            (
                "Patient has chest pain and shortness of breath.\n"
                "HbA1c: 9.2%. Blood pressure 150/95 mmHg.\n"
                "Plan: start metformin 500mg BD.\n"
                "Follow up in 2 weeks for repeat bloods."
            ),
        )
        chunks = doc.chunks.all()
        self.assertTrue(chunks.exists())
        embedded = chunks.exclude(embedding__isnull=True)
        self.assertEqual(embedded.count(), chunks.count())
        for chunk in embedded:
            self.assertEqual(len(chunk.embedding), 384)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_retrieve_context_uses_semantic_search(self):
        from apps.ai.retrieval import retrieve_context

        doc = self._upload(
            "retrieve_test.txt",
            (
                "Cardiology report: patient presented with acute chest pain.\n"
                "ECG shows ST-elevation in leads II, III, aVF.\n"
                "Troponin T elevated at 0.89 ng/mL.\n"
                "Diagnosis: acute inferior STEMI.\n"
                "Plan: emergency cardiac catheterization."
            ),
        )
        context = retrieve_context(doc, "heart attack diagnosis")
        self.assertIn("[SOURCE", context)
        self.assertNotEqual(
            context, "(No relevant content retrieved from the document.)"
        )

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_embedding_ids_populated(self):
        doc = self._upload(
            "embed_ids.txt",
            (
                "Lab Results:\n"
                "WBC: 12.5 x10^9/L (high)\n"
                "RBC: 4.8 x10^12/L\n"
                "Hemoglobin: 14.2 g/dL\n"
                "Platelets: 250 x10^9/L"
            ),
        )
        chunks = doc.chunks.all()
        for chunk in chunks:
            self.assertTrue(
                chunk.embedding_id.startswith(f"doc-{doc.pk}-chunk-")
            )


class RerankingTests(TestCase):
    """Phase 6: CrossEncoder reranking + rich retrieval metadata."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drerank", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. Rerank")
        cls.patient_a = Patient.objects.create(
            doctor=cls.doctor,
            full_name="Rerank Patient A",
            date_of_birth=date(1985, 7, 14),
            sex="F",
            mrn="MRN-RA-001",
            phone_number="555-0201",
            address="11 Rerank Ave",
        )
        cls.patient_b = Patient.objects.create(
            doctor=cls.doctor,
            full_name="Rerank Patient B",
            date_of_birth=date(1978, 3, 22),
            sex="M",
            mrn="MRN-RB-001",
            phone_number="555-0202",
            address="22 Rerank Blvd",
        )

    def _upload(self, patient, filename, content_str):
        self.client.login(username="drerank", password="pass12345")
        url = reverse(
            "documents:document_upload",
            kwargs={"patient_pk": patient.pk},
        )
        self.client.post(
            url,
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(
                    filename, content_str.encode("utf-8")
                ),
            },
        )
        return Document.objects.get(patient=patient)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_query_with_scores_returns_metadata(self):
        from apps.ai.vectorstore import query_with_scores

        doc = self._upload(
            self.patient_a,
            "meta_test.txt",
            (
                "Lab Results:\n"
                "HbA1c: 9.2%\n"
                "Fasting glucose: 186 mg/dL\n"
                "LDL cholesterol: 142 mg/dL\n"
                "eGFR: 78 mL/min/1.73m2"
            ),
        )
        results = query_with_scores(doc.pk, "HbA1c blood sugar", k=3)
        self.assertTrue(len(results) > 0)
        r = results[0]
        self.assertIn("chunk_text", r)
        self.assertIn("cosine_distance", r)
        self.assertIn("page_number", r)
        self.assertIn("section", r)
        self.assertIn("chunk_index", r)
        self.assertIn("embedding_id", r)
        self.assertIsInstance(r["cosine_distance"], float)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_rerank_adds_reranker_score(self):
        from apps.ai.retrieval import rerank

        candidates = [
            {"chunk_text": "HbA1c was 9.2 percent", "chunk_index": 0},
            {"chunk_text": "Patient likes blue color", "chunk_index": 1},
            {"chunk_text": "Fasting glucose elevated at 186", "chunk_index": 2},
        ]
        reranked = rerank("HbA1c blood sugar levels", candidates)
        self.assertEqual(len(reranked), 3)
        for c in reranked:
            self.assertIn("reranker_score", c)
            self.assertIsInstance(c["reranker_score"], float)
        self.assertEqual(reranked, sorted(reranked, key=lambda c: c["reranker_score"], reverse=True))

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_rerank_reorders_by_relevance(self):
        from apps.ai.retrieval import rerank

        candidates = [
            {"chunk_text": "Patient enjoys painting on weekends", "chunk_index": 0},
            {"chunk_text": "HbA1c: 8.2%. Glucose: 200 mg/dL. LDL: 160 mg/dL.", "chunk_index": 1},
            {"chunk_text": "Weather is sunny today in the city", "chunk_index": 2},
        ]
        reranked = rerank("What is the patient's HbA1c?", candidates)
        self.assertEqual(reranked[0]["chunk_index"], 1)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_rerank_empty_list(self):
        from apps.ai.retrieval import rerank

        result = rerank("anything", [])
        self.assertEqual(result, [])

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_retrieve_candidates_returns_reranked_metadata(self):
        from apps.ai.retrieval import retrieve_candidates

        doc = self._upload(
            self.patient_a,
            "candidates_test.txt",
            (
                "Cardiology report:\n"
                "Patient presented with acute chest pain.\n"
                "ECG shows ST-elevation in leads II, III, aVF.\n"
                "Troponin T elevated at 0.89 ng/mL.\n"
                "Diagnosis: acute inferior STEMI.\n"
                "Plan: emergency cardiac catheterization."
            ),
        )
        results = retrieve_candidates(doc.pk, "heart attack STEMI", candidate_k=10, final_k=3)
        self.assertTrue(len(results) > 0)
        self.assertLessEqual(len(results), 3)
        for r in results:
            self.assertIn("reranker_score", r)
            self.assertIn("cosine_distance", r)
            self.assertIn("chunk_text", r)
            self.assertIn("page_number", r)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_retrieve_context_still_returns_string(self):
        from apps.ai.retrieval import retrieve_context

        doc = self._upload(
            self.patient_a,
            "context_string_test.txt",
            (
                "Assessment:\n"
                "Type 2 diabetes mellitus, poorly controlled.\n"
                "HbA1c 9.2% above target.\n"
                "Continue metformin 500mg BD."
            ),
        )
        context = retrieve_context(doc, "diabetes HbA1c")
        self.assertIsInstance(context, str)
        self.assertIn("[SOURCE", context)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_retrieve_patient_scoped(self):
        from apps.ai.retrieval import retrieve_patient_scoped

        self._upload(
            self.patient_a,
            "scope_a.txt",
            (
                "Ophthalmology:\n"
                "Diabetic retinopathy grade 2.\n"
                "Visual acuity 6/9 bilateral.\n"
                "Refer to laser clinic."
            ),
        )
        self._upload(
            self.patient_b,
            "scope_b.txt",
            (
                "Dermatology:\n"
                "Eczema on bilateral forearms.\n"
                "Prescribed hydrocortisone 1% cream.\n"
                "Review in 2 weeks."
            ),
        )
        results = retrieve_patient_scoped(
            self.patient_a.pk, "diabetic retinopathy eye", final_k=3
        )
        self.assertTrue(len(results) > 0)
        for r in results:
            self.assertEqual(r["patient_id"], self.patient_a.pk)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_patient_isolation(self):
        from apps.ai.retrieval import retrieve_patient_scoped

        self._upload(
            self.patient_a,
            "isol_a.txt",
            (
                "Cardiology:\n"
                "Hypertension stage 2.\n"
                "BP 158/96 mmHg.\n"
                "Start amlodipine 5mg OD."
            ),
        )
        self._upload(
            self.patient_b,
            "isol_b.txt",
            (
                "Endocrinology:\n"
                "Hypothyroidism.\n"
                "TSH elevated at 12.5 mIU/L.\n"
                "Start levothyroxine 50mcg OD."
            ),
        )
        results = retrieve_patient_scoped(
            self.patient_a.pk, "blood pressure hypertension", final_k=5
        )
        for r in results:
            self.assertEqual(r["patient_id"], self.patient_a.pk)
            self.assertNotIn("thyroid", r["chunk_text"].lower())

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_final_k_limits_results(self):
        from apps.ai.retrieval import retrieve_candidates

        doc = self._upload(
            self.patient_a,
            "limit_test.txt",
            (
                "Multisystem review:\n"
                "1. Cardiovascular: normal.\n"
                "2. Respiratory: mild asthma.\n"
                "3. Gastrointestinal: GERD.\n"
                "4. Neurological: migraine.\n"
                "5. Musculoskeletal: low back pain.\n"
                "6. Dermatological: acne vulgaris.\n"
                "7. Psychiatric: anxiety.\n"
                "8. Endocrine: hypothyroidism.\n"
            ),
        )
        results = retrieve_candidates(doc.pk, "system review", candidate_k=10, final_k=3)
        self.assertLessEqual(len(results), 3)

    @override_settings(RAG_EMBEDDINGS_ENABLED=False)
    def test_disabled_embeddings_returns_empty(self):
        from apps.ai.retrieval import retrieve_candidates

        doc = self._upload(
            self.patient_a,
            "disabled_test.txt",
            "Simple text content."
        )
        results = retrieve_candidates(doc.pk, "simple text")
        self.assertEqual(results, [])


class ContextAssemblyTests(TestCase):
    """Phase 7: Context assembly — dedup, neighbor expansion, bounded formatting."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drctx", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. Ctx")
        cls.patient = Patient.objects.create(
            doctor=cls.doctor,
            full_name="Ctx Patient",
            date_of_birth=date(1988, 4, 10),
            sex="M",
            mrn="MRN-CTX-001",
            phone_number="555-0301",
            address="33 Ctx Lane",
        )

    def _upload(self, filename, content_str):
        self.client.login(username="drctx", password="pass12345")
        url = reverse(
            "documents:document_upload",
            kwargs={"patient_pk": self.patient.pk},
        )
        self.client.post(
            url,
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(
                    filename, content_str.encode("utf-8")
                ),
            },
        )
        return Document.objects.get(patient=self.patient)

    def test_build_context_returns_formatted_sources(self):
        from apps.ai.retrieval import build_context

        candidates = [
            {
                "chunk_text": "HbA1c: 9.2%.",
                "chunk_index": 0,
                "page_number": 1,
                "section": "Lab Results",
                "document_id": 1,
                "cosine_distance": 0.3,
                "reranker_score": 5.0,
            },
            {
                "chunk_text": "Plan: start metformin.",
                "chunk_index": 1,
                "page_number": 2,
                "section": "Assessment",
                "document_id": 1,
                "cosine_distance": 0.5,
                "reranker_score": 3.0,
            },
        ]
        result = build_context(candidates, document_id=1)
        ctx = result["context_text"]
        self.assertIn("[SOURCE 1]", ctx)
        self.assertIn("[SOURCE 2]", ctx)
        self.assertIn("Page: 1", ctx)
        self.assertIn("Section: Lab Results", ctx)
        self.assertIn("HbA1c: 9.2%", ctx)
        self.assertIn("Plan: start metformin.", ctx)

    def test_build_context_deduplicates(self):
        from apps.ai.retrieval import build_context

        candidates = [
            {
                "chunk_text": "HbA1c: 9.2%.",
                "chunk_index": 0,
                "page_number": 1,
                "section": "Lab Results",
                "document_id": 1,
                "cosine_distance": 0.3,
                "reranker_score": 5.0,
            },
            {
                "chunk_text": "HbA1c: 9.2%.",
                "chunk_index": 3,
                "page_number": 2,
                "section": "Summary",
                "document_id": 1,
                "cosine_distance": 0.4,
                "reranker_score": 4.0,
            },
        ]
        result = build_context(candidates, document_id=1)
        self.assertEqual(result["pipeline"]["final_sources"], 1)
        self.assertEqual(result["pipeline"]["after_dedup"], 1)

    def test_build_context_empty_returns_empty(self):
        from apps.ai.retrieval import build_context

        result = build_context([])
        self.assertEqual(result["context_text"], "")
        self.assertEqual(result["sources"], [])

    def test_build_context_respects_max_chars(self):
        from apps.ai.retrieval import build_context

        long_text = "x" * 4000
        candidates = [
            {
                "chunk_text": long_text,
                "chunk_index": i,
                "page_number": 1,
                "section": f"Section {i}",
                "document_id": 1,
                "cosine_distance": 0.1 * i,
                "reranker_score": 10.0 - i,
            }
            for i in range(5)
        ]
        result = build_context(candidates, document_id=1, max_chars=5000)
        self.assertLessEqual(result["total_chars"], 5000)

    def test_build_context_source_numbering(self):
        from apps.ai.retrieval import build_context

        candidates = [
            {
                "chunk_text": f"Chunk {i} text.",
                "chunk_index": i,
                "page_number": 1,
                "section": f"Section {i}",
                "document_id": 1,
                "cosine_distance": 0.1,
                "reranker_score": 10.0 - i,
            }
            for i in range(3)
        ]
        result = build_context(candidates, document_id=1)
        for i, src in enumerate(result["sources"], 1):
            self.assertEqual(src["source_num"], i)
        self.assertIn("[SOURCE 1]", result["context_text"])
        self.assertIn("[SOURCE 2]", result["context_text"])
        self.assertIn("[SOURCE 3]", result["context_text"])

    def test_retrieve_with_context_returns_full_pipeline(self):
        from apps.ai.retrieval import retrieve_with_context

        doc = self._upload(
            "pipeline_test.txt",
            (
                "Cardiology report:\n"
                "Patient presented with acute chest pain.\n"
                "ECG shows ST-elevation.\n"
                "Troponin T elevated at 0.89 ng/mL.\n"
                "Diagnosis: STEMI.\n"
                "Plan: cardiac catheterization."
            ),
        )
        result = retrieve_with_context(doc.pk, "heart attack STEMI")
        self.assertIn("candidates", result)
        self.assertIn("context", result)
        ctx = result["context"]
        self.assertIn("context_text", ctx)
        self.assertIn("sources", ctx)
        self.assertIn("pipeline", ctx)
        self.assertIsInstance(ctx["context_text"], str)

    def test_retrieve_context_backward_compatible(self):
        from apps.ai.retrieval import retrieve_context

        doc = self._upload(
            "compat_test.txt",
            (
                "Lab Results:\n"
                "HbA1c: 9.2%\n"
                "Glucose: 186 mg/dL\n"
                "LDL: 142 mg/dL"
            ),
        )
        context = retrieve_context(doc, "HbA1c glucose")
        self.assertIsInstance(context, str)
        self.assertTrue(len(context) > 0)
        self.assertIn("[SOURCE", context)

    def test_context_is_fully_deidentified(self):
        from apps.ai.retrieval import build_context

        candidates = [
            {
                "chunk_text": "[PATIENT_NAME] presented with chest pain.",
                "chunk_index": 0,
                "page_number": 1,
                "section": "Chief Complaint",
                "document_id": 1,
                "cosine_distance": 0.2,
                "reranker_score": 8.0,
            },
            {
                "chunk_text": "HbA1c: 9.2%. Glucose: [ADDRESS].",
                "chunk_index": 1,
                "page_number": 2,
                "section": "Lab Results",
                "document_id": 1,
                "cosine_distance": 0.3,
                "reranker_score": 6.0,
            },
        ]
        result = build_context(candidates, document_id=1)
        self.assertNotIn("John Smith", result["context_text"])
        self.assertNotIn("90493093431", result["context_text"])
        self.assertIn("[PATIENT_NAME]", result["context_text"])

    def test_pipeline_dict_tracks_stages(self):
        from apps.ai.retrieval import build_context

        candidates = [
            {
                "chunk_text": "Chunk A.",
                "chunk_index": 0,
                "page_number": 1,
                "section": "A",
                "document_id": 1,
                "cosine_distance": 0.1,
                "reranker_score": 5.0,
            },
        ]
        result = build_context(candidates, document_id=1)
        p = result["pipeline"]
        self.assertEqual(p["input_candidates"], 1)
        self.assertEqual(p["after_dedup"], 1)
        self.assertGreaterEqual(p["after_expansion"], 1)
        self.assertEqual(p["final_sources"], 1)
        self.assertGreater(p["total_chars"], 0)

    def test_context_bounded_by_max_chars(self):
        from apps.ai.retrieval import build_context

        candidates = [
            {
                "chunk_text": "A" * 1000,
                "chunk_index": i,
                "page_number": 1,
                "section": f"S{i}",
                "document_id": 1,
                "cosine_distance": 0.1,
                "reranker_score": 10.0 - i,
            }
            for i in range(10)
        ]
        result = build_context(candidates, document_id=1, max_chars=2500)
        self.assertLessEqual(result["total_chars"], 2500)


class AnswerabilityTests(TestCase):
    """Phase 8: Answerability assessment — gate LLM calls on retrieval quality."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drans", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. Ans")
        cls.patient = Patient.objects.create(
            doctor=cls.doctor,
            full_name="Ans Patient",
            date_of_birth=date(1992, 1, 5),
            sex="F",
            mrn="MRN-ANS-001",
            phone_number="555-0401",
            address="44 Ans Road",
        )

    def _upload(self, filename, content_str):
        self.client.login(username="drans", password="pass12345")
        url = reverse(
            "documents:document_upload",
            kwargs={"patient_pk": self.patient.pk},
        )
        self.client.post(
            url,
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(
                    filename, content_str.encode("utf-8")
                ),
            },
        )
        return Document.objects.get(patient=self.patient)

    def test_assess_answerable_with_good_scores(self):
        from apps.ai.retrieval import assess_answerability

        candidates = [
            {
                "chunk_text": "HbA1c: 9.2%.",
                "reranker_score": 3.0,
                "cosine_distance": 0.3,
            },
        ]
        result = assess_answerability(candidates)
        self.assertTrue(result["is_answerable"])

    def test_assess_unanswerable_low_reranker_safety_net(self):
        from apps.ai.retrieval import assess_answerability

        candidates = [
            {
                "chunk_text": "Patient likes painting.",
                "reranker_score": -20.0,
                "cosine_distance": 0.5,
            },
        ]
        result = assess_answerability(candidates)
        self.assertFalse(result["is_answerable"])

    def test_assess_unanswerable_high_cosine(self):
        from apps.ai.retrieval import assess_answerability

        candidates = [
            {
                "chunk_text": "Unrelated content.",
                "reranker_score": 2.0,
                "cosine_distance": 0.95,
            },
        ]
        result = assess_answerability(candidates)
        self.assertFalse(result["is_answerable"])

    def test_assess_unanswerable_no_candidates(self):
        from apps.ai.retrieval import assess_answerability

        result = assess_answerability([])
        self.assertFalse(result["is_answerable"])
        self.assertEqual(result["candidate_count"], 0)

    def test_assess_returns_metadata(self):
        from apps.ai.retrieval import assess_answerability

        candidates = [
            {
                "chunk_text": "Lab results.",
                "reranker_score": 5.0,
                "cosine_distance": 0.2,
            },
        ]
        result = assess_answerability(candidates)
        self.assertEqual(result["top_reranker_score"], 5.0)
        self.assertEqual(result["top_cosine_distance"], 0.2)
        self.assertEqual(result["candidate_count"], 1)
        self.assertIn("reason", result)

    def test_assess_custom_thresholds(self):
        from apps.ai.retrieval import assess_answerability

        candidates = [
            {
                "chunk_text": "Content.",
                "reranker_score": 0.5,
                "cosine_distance": 0.6,
            },
        ]
        strict = assess_answerability(
            candidates, rerank_threshold=2.0, cosine_threshold=0.3
        )
        self.assertFalse(strict["is_answerable"])

        loose = assess_answerability(
            candidates, rerank_threshold=-5.0, cosine_threshold=0.9
        )
        self.assertTrue(loose["is_answerable"])

    def test_assess_both_thresholds_fail(self):
        from apps.ai.retrieval import assess_answerability

        candidates = [
            {
                "chunk_text": "Bad content.",
                "reranker_score": -8.0,
                "cosine_distance": 0.9,
            },
        ]
        result = assess_answerability(candidates)
        self.assertFalse(result["is_answerable"])

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_end_to_end_answerable(self):
        from apps.ai.retrieval import retrieve_with_context

        doc = self._upload(
            "ans_test.txt",
            (
                "Lab Results:\n"
                "HbA1c: 9.2%\n"
                "Fasting glucose: 186 mg/dL\n"
                "LDL cholesterol: 142 mg/dL"
            ),
        )
        result = retrieve_with_context(doc.pk, "HbA1c blood sugar")
        self.assertTrue(result["answerability"]["is_answerable"])
        self.assertTrue(len(result["context"]["context_text"]) > 0)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_end_to_end_retrieve_with_context_has_answerability(self):
        from apps.ai.retrieval import retrieve_with_context

        doc = self._upload(
            "ans_pipeline.txt",
            (
                "Cardiology:\n"
                "Acute STEMI diagnosed.\n"
                "Troponin T: 0.89 ng/mL.\n"
                "Plan: cardiac catheterization."
            ),
        )
        result = retrieve_with_context(doc.pk, "heart attack STEMI")
        self.assertIn("answerability", result)
        self.assertIn("is_answerable", result["answerability"])
        self.assertIn("reason", result["answerability"])


class LLMPipelineTests(TestCase):
    """Phase 9: Full LLM integration — answerable, unanswerable, de-id, isolation."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("drllm", password="pass12345")
        cls.doctor = Doctor.objects.create(user=cls.user, full_name="Dr. LLM")
        cls.patient_a = Patient.objects.create(
            doctor=cls.doctor,
            full_name="LLM Patient Alice",
            date_of_birth=date(1990, 6, 15),
            sex="F",
            mrn="MRN-LLM-001",
            phone_number="555-0501",
            address="55 LLM Street",
        )
        cls.patient_b = Patient.objects.create(
            doctor=cls.doctor,
            full_name="LLM Patient Bob",
            date_of_birth=date(1982, 11, 3),
            sex="M",
            mrn="MRN-LLM-002",
            phone_number="555-0502",
            address="66 LLM Avenue",
        )

    def _upload(self, patient, filename, content_str):
        self.client.login(username="drllm", password="pass12345")
        url = reverse(
            "documents:document_upload",
            kwargs={"patient_pk": patient.pk},
        )
        self.client.post(
            url,
            {
                "doc_type": "lab",
                "file": SimpleUploadedFile(
                    filename, content_str.encode("utf-8")
                ),
            },
        )
        return Document.objects.get(patient=patient)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_answerable_query_calls_llm(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator

        doc = self._upload(
            self.patient_a,
            "llm_ans.txt",
            (
                "Lab Results:\n"
                "HbA1c: 9.2%\n"
                "Fasting glucose: 186 mg/dL\n"
                "LDL cholesterol: 142 mg/dL\n"
                "eGFR: 78 mL/min/1.73m2"
            ),
        )
        mock_response = '{"summary": "Lab report with elevated HbA1c.", "key_points": ["HbA1c 9.2%"], "query_answer": "HbA1c is 9.2%.", "sources_cited": ["SOURCE 1"]}'

        with patch("apps.ai.llm.call_llm", return_value=mock_response) as mock_llm:
            result = AIOrchestrator.analyze_document(doc, "What is the HbA1c?")
            mock_llm.assert_called_once()

        self.assertTrue(result["answerability"]["is_answerable"])
        self.assertIn("prompt_used", result)
        self.assertTrue(len(result["prompt_used"]) > 0)
        self.assertEqual(result["llm_response_json"]["query_answer"], "HbA1c is 9.2%.")

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_unanswerable_query_skips_llm(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator

        doc = self._upload(
            self.patient_a,
            "llm_unans.txt",
            (
                "Lab Results:\n"
                "HbA1c: 9.2%\n"
                "Glucose: 186 mg/dL"
            ),
        )
        with patch("apps.ai.llm.call_llm") as mock_llm:
            result = AIOrchestrator.analyze_document(
                doc, "What is the patient's allergy to penicillin?"
            )
            mock_llm.assert_not_called()

        self.assertFalse(result["answerability"]["is_answerable"])
        self.assertEqual(result["prompt_used"], "")
        self.assertIn("insufficient", result["llm_response_json"]["summary"].lower())

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_deidentification_not_in_prompt(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator

        doc = self._upload(
            self.patient_a,
            "llm_deid.txt",
            (
                "Cardiology:\n"
                "Patient presented with chest pain.\n"
                "BP 158/96 mmHg.\n"
                "Start amlodipine 5mg OD."
            ),
        )
        mock_response = '{"summary": "Cardiology report.", "key_points": ["Chest pain"], "query_answer": "Patient had chest pain.", "sources_cited": ["SOURCE 1"]}'

        with patch("apps.ai.llm.call_llm", return_value=mock_response):
            result = AIOrchestrator.analyze_document(doc, "What was the blood pressure?")

        prompt = result["prompt_used"]
        self.assertNotIn("LLM Patient Alice", prompt)
        self.assertNotIn("MRN-LLM-001", prompt)
        self.assertNotIn("555-0501", prompt)
        self.assertNotIn("55 LLM Street", prompt)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_deidentification_flag_in_response(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator

        doc = self._upload(
            self.patient_a,
            "llm_deid_flag.txt",
            "Lab Results:\nHbA1c: 8.5%\nPlan: metformin."
        )
        mock_response = '{"summary": "Lab report.", "key_points": [], "query_answer": "HbA1c 8.5%.", "sources_cited": ["SOURCE 1"]}'

        with patch("apps.ai.llm.call_llm", return_value=mock_response):
            result = AIOrchestrator.analyze_document(doc, "What is HbA1c?")

        self.assertIn("deidentification", result)
        self.assertTrue(result["deidentification"]["document_deidentified"])
        self.assertFalse(result["deidentification"]["context_contains_patient_identity"])

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_patient_isolation_in_context(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator

        self._upload(
            self.patient_a,
            "isol_a_llm.txt",
            (
                "Cardiology:\n"
                "Hypertension stage 2.\n"
                "BP 158/96 mmHg.\n"
                "Start amlodipine 5mg."
            ),
        )
        self._upload(
            self.patient_b,
            "isol_b_llm.txt",
            (
                "Endocrinology:\n"
                "Hypothyroidism.\n"
                "TSH 12.5 mIU/L.\n"
                "Start levothyroxine."
            ),
        )
        mock_response = '{"summary": "Cardiology report.", "key_points": ["Hypertension"], "query_answer": "BP 158/96.", "sources_cited": ["SOURCE 1"]}'

        with patch("apps.ai.llm.call_llm", return_value=mock_response) as mock_llm:
            doc_a = Document.objects.get(patient=self.patient_a)
            AIOrchestrator.analyze_document(doc_a, "blood pressure hypertension")

            prompt_used = mock_llm.call_args[0][0]
            self.assertNotIn("hypothyroidism", prompt_used.lower())
            self.assertNotIn("levothyroxine", prompt_used.lower())
            self.assertNotIn("TSH", prompt_used)

    @override_settings(RAG_EMBEDDINGS_ENABLED=True)
    def test_facade_returns_all_pipeline_keys(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator

        doc = self._upload(
            self.patient_a,
            "llm_keys.txt",
            "Lab Results:\nHbA1c: 8.5%."
        )
        mock_response = '{"summary": "Lab report.", "key_points": [], "query_answer": "HbA1c 8.5%.", "sources_cited": ["SOURCE 1"]}'

        with patch("apps.ai.llm.call_llm", return_value=mock_response):
            result = AIOrchestrator.analyze_document(doc, "HbA1c")

        self.assertIn("prompt_used", result)
        self.assertIn("llm_response_json", result)
        self.assertIn("answerability", result)
        self.assertIn("retrieval_pipeline", result)
        self.assertIn("deidentification", result)

    def test_llm_failure_returns_graceful_error(self):
        from unittest.mock import patch

        from apps.ai.facade import AIOrchestrator
        from apps.ai.llm import LLMAvailabilityError

        doc = self._upload(
            self.patient_a,
            "llm_fail.txt",
            (
                "Lab Results:\n"
                "HbA1c: 9.2%"
            ),
        )

        with patch(
            "apps.ai.llm.call_llm",
            side_effect=LLMAvailabilityError("Connection refused"),
        ):
            result = AIOrchestrator.analyze_document(doc, "HbA1c?")

        self.assertIn("AI UNAVAILABLE", result["llm_response_json"]["summary"])
        self.assertIn("prompt_used", result)

    def test_empty_prompt_not_called_with(self):
        from unittest.mock import patch

        from apps.ai.llm import LLMAvailabilityError, call_llm

        with patch("apps.ai.llm._get_client") as mock_client:
            with self.assertRaises(LLMAvailabilityError):
                call_llm("")
