from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Doctor


class RegisterViewTests(TestCase):
    def test_register_creates_user_and_doctor(self):
        data = {
            "username": "dr_smith",
            "password1": "Str0ng!Pass",
            "password2": "Str0ng!Pass",
            "full_name": "Dr. Smith",
            "specialization": "Cardiology",
            "license_number": "LIC-001",
            "phone_number": "1234567890",
        }
        response = self.client.post(reverse("accounts:register"), data)
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Doctor.objects.count(), 1)
        doctor = Doctor.objects.first()
        self.assertEqual(doctor.full_name, "Dr. Smith")
        self.assertEqual(doctor.specialization, "Cardiology")
        self.assertEqual(doctor.license_number, "LIC-001")
        self.assertEqual(doctor.phone_number, "1234567890")
        self.assertEqual(doctor.user.username, "dr_smith")

    def test_register_duplicate_license_rejected(self):
        user = User.objects.create_user(username="existing", password="pass123")
        Doctor.objects.create(
            user=user,
            full_name="Existing",
            license_number="LIC-001",
        )
        data = {
            "username": "new_doc",
            "password1": "Str0ng!Pass",
            "password2": "Str0ng!Pass",
            "full_name": "New Doc",
            "license_number": "LIC-001",
        }
        response = self.client.post(reverse("accounts:register"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Doctor.objects.count(), 1)

    def test_register_get_returns_form(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Register")


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dr_smith", password="correct-password"
        )
        Doctor.objects.create(user=self.user, full_name="Dr. Smith")

    def test_login_with_correct_credentials(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "dr_smith", "password": "correct-password"},
        )
        self.assertRedirects(response, "/accounts/profile/")

    def test_login_with_incorrect_credentials(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "dr_smith", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct")


class ProfileViewTests(TestCase):
    def test_unauthenticated_redirect_to_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('accounts:profile')}"
        )

    def test_profile_view_shows_doctor_data(self):
        user = User.objects.create_user(username="dr_smith", password="pass123")
        Doctor.objects.create(
            user=user,
            full_name="Dr. Smith",
            specialization="Cardiology",
            phone_number="1234567890",
        )
        self.client.login(username="dr_smith", password="pass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Smith")
        self.assertContains(response, "Cardiology")

    def test_profile_edit_updates_doctor(self):
        user = User.objects.create_user(username="dr_smith", password="pass123")
        Doctor.objects.create(
            user=user,
            full_name="Dr. Smith",
            specialization="Cardiology",
        )
        self.client.login(username="dr_smith", password="pass123")
        response = self.client.post(
            reverse("accounts:profile"),
            {"full_name": "Dr. Updated", "specialization": "Neurology", "phone_number": "555-0100"},
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        doctor = Doctor.objects.get(user=user)
        self.assertEqual(doctor.full_name, "Dr. Updated")
        self.assertEqual(doctor.specialization, "Neurology")

    def test_profile_edit_cannot_change_another_doctors_record(self):
        user1 = User.objects.create_user(username="doc1", password="pass123")
        doc1 = Doctor.objects.create(user=user1, full_name="Doctor One")
        user2 = User.objects.create_user(username="doc2", password="pass123")
        doc2 = Doctor.objects.create(user=user2, full_name="Doctor Two")

        self.client.login(username="doc1", password="pass123")
        response = self.client.post(
            reverse("accounts:profile"),
            {"full_name": "Hacked Name", "specialization": "", "phone_number": ""},
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        doc1.refresh_from_db()
        doc2.refresh_from_db()
        self.assertEqual(doc1.full_name, "Hacked Name")
        self.assertEqual(doc2.full_name, "Doctor Two")


class PasswordResetTests(TestCase):
    def test_password_reset_sends_email(self):
        user = User.objects.create_user(
            username="dr_smith",
            email="doctor@example.com",
            password="old-password",
        )
        Doctor.objects.create(user=user, full_name="Dr. Smith")
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "doctor@example.com"},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(self.client.session.get("password_reset_email_contexts", [])), 0)

    def test_password_reset_email_sent_count(self):
        user = User.objects.create_user(
            username="dr_smith",
            email="doctor@example.com",
            password="old-password",
        )
        Doctor.objects.create(user=user, full_name="Dr. Smith")
        from django.core import mail
        self.client.post(
            reverse("accounts:password_reset"),
            {"email": "doctor@example.com"},
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("doctor@example.com", mail.outbox[0].to)
