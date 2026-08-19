from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import Doctor
from apps.ai.facade import AIOrchestrator
from apps.patients.models import Patient

from apps.visits.models import Visit, VisitMessage

from apps.visits.services import create_visit, post_message


class AIContractTests(SimpleTestCase):
    @patch("apps.ai.llm.call_llm", return_value="Mocked AI reply")
    def test_generate_visit_reply_returns_non_empty_string(self, mock_llm):
        reply = AIOrchestrator.generate_visit_reply(None, "Hello doctor")
        self.assertEqual(reply, "Mocked AI reply")
        mock_llm.assert_called_once()

    @patch("apps.ai.llm.call_llm", side_effect=ConnectionError("LLM down"))
    def test_generate_visit_reply_never_raises(self, mock_llm):
        try:
            reply = AIOrchestrator.generate_visit_reply(None, "Test")
        except Exception:
            self.fail("generate_visit_reply raised an exception")
        self.assertIsInstance(reply, str)
        self.assertIn("[AI UNAVAILABLE]", reply)


class VisitServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dr_a", password="pass123")
        self.doctor = Doctor.objects.create(user=self.user, full_name="Dr. A")
        self.patient = Patient.objects.create(
            doctor=self.doctor, full_name="Patient A", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-A"
        )

    def test_create_visit_links_patient_and_doctor(self):
        visit = create_visit(self.patient, self.doctor)
        self.assertEqual(visit.patient, self.patient)
        self.assertEqual(visit.doctor, self.doctor)
        self.assertEqual(visit.status, "open")

    @patch("apps.ai.llm.call_llm", return_value="Mocked AI reply")
    def test_post_message_creates_doctor_and_ai_messages(self, mock_llm):
        visit = create_visit(self.patient, self.doctor)
        doctor_msg, ai_msg = post_message(visit, "Patient reports chest pain")
        self.assertEqual(doctor_msg.role, "doctor")
        self.assertEqual(doctor_msg.content, "Patient reports chest pain")
        self.assertEqual(ai_msg.role, "ai")
        self.assertEqual(ai_msg.content, "Mocked AI reply")
        self.assertEqual(VisitMessage.objects.filter(visit=visit).count(), 2)


class VisitViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dr_a", password="pass123")
        self.doctor = Doctor.objects.create(user=self.user, full_name="Dr. A")
        self.patient = Patient.objects.create(
            doctor=self.doctor, full_name="Patient A", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-A"
        )
        self.client.login(username="dr_a", password="pass123")

    def test_visit_create_links_patient_and_doctor(self):
        response = self.client.post(
            reverse("visits:visit_create", kwargs={"patient_pk": self.patient.pk})
        )
        self.assertEqual(Visit.objects.count(), 1)
        visit = Visit.objects.first()
        self.assertEqual(visit.patient, self.patient)
        self.assertEqual(visit.doctor, self.doctor)
        self.assertRedirects(response, reverse("visits:visit_detail", kwargs={"pk": visit.pk}))

    @patch("apps.ai.llm.call_llm", return_value="Mocked AI reply")
    def test_message_send_creates_doctor_and_ai_messages(self, mock_llm):
        visit = create_visit(self.patient, self.doctor)
        response = self.client.post(
            reverse("visits:message_send", kwargs={"pk": visit.pk}),
            {"content": "Checking blood pressure"},
        )
        self.assertRedirects(response, reverse("visits:visit_detail", kwargs={"pk": visit.pk}))
        messages = VisitMessage.objects.filter(visit=visit).order_by("created_at")
        self.assertEqual(messages.count(), 2)
        self.assertEqual(messages[0].role, "doctor")
        self.assertEqual(messages[1].role, "ai")
        self.assertEqual(messages[1].content, "Mocked AI reply")

    @patch("apps.ai.llm.call_llm", return_value="Mocked AI reply")
    def test_visit_detail_shows_thread(self, mock_llm):
        visit = create_visit(self.patient, self.doctor)
        post_message(visit, "Initial consultation")
        response = self.client.get(
            reverse("visits:visit_detail", kwargs={"pk": visit.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Initial consultation")
        self.assertContains(response, "Mocked AI reply")

    def test_visit_detail_renders_timeline_on_patient_page(self):
        visit = create_visit(self.patient, self.doctor)
        response = self.client.get(
            reverse("patients:patient_detail", kwargs={"pk": self.patient.pk})
        )
        self.assertContains(response, "Clinical Timeline")
        self.assertContains(
            response, reverse("visits:visit_detail", kwargs={"pk": visit.pk})
        )

    def test_doctor_cannot_view_other_doctors_visit(self):
        other_user = User.objects.create_user(username="dr_b", password="pass123")
        other_doctor = Doctor.objects.create(user=other_user, full_name="Dr. B")
        other_patient = Patient.objects.create(
            doctor=other_doctor, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        other_visit = create_visit(other_patient, other_doctor)
        response = self.client.get(
            reverse("visits:visit_detail", kwargs={"pk": other_visit.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_doctor_cannot_post_into_other_doctors_visit(self):
        other_user = User.objects.create_user(username="dr_b", password="pass123")
        other_doctor = Doctor.objects.create(user=other_user, full_name="Dr. B")
        other_patient = Patient.objects.create(
            doctor=other_doctor, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        other_visit = create_visit(other_patient, other_doctor)
        response = self.client.post(
            reverse("visits:message_send", kwargs={"pk": other_visit.pk}),
            {"content": "Intruding"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(VisitMessage.objects.filter(visit=other_visit).count(), 0)

    def test_doctor_cannot_start_visit_for_other_doctors_patient(self):
        other_user = User.objects.create_user(username="dr_b", password="pass123")
        other_doctor = Doctor.objects.create(user=other_user, full_name="Dr. B")
        other_patient = Patient.objects.create(
            doctor=other_doctor, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        response = self.client.post(
            reverse("visits:visit_create", kwargs={"patient_pk": other_patient.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Visit.objects.count(), 0)


class AuthRedirectTests(TestCase):
    def test_visit_create_redirects_unauthenticated(self):
        response = self.client.get(
            reverse("visits:visit_create", kwargs={"patient_pk": 1})
        )
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next="
            f"{reverse('visits:visit_create', kwargs={'patient_pk': 1})}",
        )

    def test_visit_detail_redirects_unauthenticated(self):
        response = self.client.get(reverse("visits:visit_detail", kwargs={"pk": 1}))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next="
            f"{reverse('visits:visit_detail', kwargs={'pk': 1})}",
        )
