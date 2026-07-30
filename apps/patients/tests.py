from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Doctor
from apps.patients.models import Patient


class PatientCRUDTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dr_a", password="pass123")
        self.doctor = Doctor.objects.create(
            user=self.user, full_name="Dr. A"
        )
        self.client.login(username="dr_a", password="pass123")

    def test_create_patient_sets_doctor_from_logged_in_user(self):
        data = {
            "full_name": "John Doe",
            "date_of_birth": "1990-01-15",
            "sex": "M",
            "mrn": "MRN-001",
            "phone_number": "555-0100",
            "address": "123 Main St",
        }
        response = self.client.post(reverse("patients:patient_create"), data)
        self.assertEqual(Patient.objects.count(), 1)
        patient = Patient.objects.first()
        self.assertEqual(patient.full_name, "John Doe")
        self.assertEqual(patient.doctor, self.doctor)

    def test_create_patient_does_not_accept_doctor_from_form(self):
        data = {
            "full_name": "Jane Doe",
            "date_of_birth": "1992-05-20",
            "sex": "F",
            "mrn": "MRN-002",
        }
        response = self.client.post(reverse("patients:patient_create"), data)
        self.assertEqual(Patient.objects.count(), 1)
        patient = Patient.objects.first()
        self.assertEqual(patient.doctor, self.doctor)

    def test_list_shows_only_own_patients(self):
        user_b = User.objects.create_user(username="dr_b", password="pass123")
        doctor_b = Doctor.objects.create(user=user_b, full_name="Dr. B")
        Patient.objects.create(
            doctor=self.doctor, full_name="Patient A", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-A"
        )
        Patient.objects.create(
            doctor=doctor_b, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        response = self.client.get(reverse("patients:patient_list"))
        self.assertContains(response, "Patient A")
        self.assertNotContains(response, "Patient B")

    def test_detail_of_other_doctors_patient_returns_404(self):
        user_b = User.objects.create_user(username="dr_b", password="pass123")
        doctor_b = Doctor.objects.create(user=user_b, full_name="Dr. B")
        patient_b = Patient.objects.create(
            doctor=doctor_b, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        response = self.client.get(
            reverse("patients:patient_detail", kwargs={"pk": patient_b.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_update_of_other_doctors_patient_returns_404(self):
        user_b = User.objects.create_user(username="dr_b", password="pass123")
        doctor_b = Doctor.objects.create(user=user_b, full_name="Dr. B")
        patient_b = Patient.objects.create(
            doctor=doctor_b, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        response = self.client.get(
            reverse("patients:patient_update", kwargs={"pk": patient_b.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_own_patient_succeeds(self):
        patient = Patient.objects.create(
            doctor=self.doctor, full_name="My Patient", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-OWN"
        )
        response = self.client.get(
            reverse("patients:patient_detail", kwargs={"pk": patient.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Patient")

    def test_update_own_patient_succeeds(self):
        patient = Patient.objects.create(
            doctor=self.doctor, full_name="Old Name", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-UPD"
        )
        response = self.client.post(
            reverse("patients:patient_update", kwargs={"pk": patient.pk}),
            {"full_name": "Updated Name", "date_of_birth": "2000-01-01", "sex": "M", "mrn": "MRN-UPD"},
        )
        self.assertRedirects(
            response, reverse("patients:patient_detail", kwargs={"pk": patient.pk})
        )
        patient.refresh_from_db()
        self.assertEqual(patient.full_name, "Updated Name")

    def test_duplicate_mrn_rejected(self):
        Patient.objects.create(
            doctor=self.doctor, full_name="First", date_of_birth="2000-01-01",
            sex="O", mrn="MRN-DUP"
        )
        data = {
            "full_name": "Second",
            "date_of_birth": "1995-06-15",
            "sex": "F",
            "mrn": "MRN-DUP",
        }
        response = self.client.post(reverse("patients:patient_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(Patient.objects.count(), 1)

    def test_update_same_mrn_allowed(self):
        patient = Patient.objects.create(
            doctor=self.doctor, full_name="Original", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-SAME"
        )
        response = self.client.post(
            reverse("patients:patient_update", kwargs={"pk": patient.pk}),
            {"full_name": "Updated", "date_of_birth": "2000-01-01", "sex": "M", "mrn": "MRN-SAME"},
        )
        self.assertRedirects(
            response, reverse("patients:patient_detail", kwargs={"pk": patient.pk})
        )


class AuthRedirectTests(TestCase):
    def test_list_redirects_unauthenticated(self):
        response = self.client.get(reverse("patients:patient_list"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('patients:patient_list')}")

    def test_create_redirects_unauthenticated(self):
        response = self.client.get(reverse("patients:patient_create"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('patients:patient_create')}")

    def test_detail_redirects_unauthenticated(self):
        response = self.client.get(reverse("patients:patient_detail", kwargs={"pk": 1}))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('patients:patient_detail', kwargs={'pk': 1})}"
        )

    def test_update_redirects_unauthenticated(self):
        response = self.client.get(reverse("patients:patient_update", kwargs={"pk": 1}))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('patients:patient_update', kwargs={'pk': 1})}"
        )
