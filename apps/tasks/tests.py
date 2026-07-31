from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Doctor
from apps.patients.models import Patient

from apps.tasks.models import Task


def _due_str(days_offset):
    return (timezone.now() + timedelta(days=days_offset)).strftime("%Y-%m-%dT%H:%M")


class TaskIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="dr_a", password="pass123")
        self.doctor_a = Doctor.objects.create(user=self.user_a, full_name="Dr. A")
        self.user_b = User.objects.create_user(username="dr_b", password="pass123")
        self.doctor_b = Doctor.objects.create(user=self.user_b, full_name="Dr. B")
        self.patient_a = Patient.objects.create(
            doctor=self.doctor_a, full_name="Patient A", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-A"
        )
        self.patient_b = Patient.objects.create(
            doctor=self.doctor_b, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        self.client.login(username="dr_a", password="pass123")

    def test_create_task_for_own_patient(self):
        data = {
            "patient": self.patient_a.pk,
            "title": "Follow up",
            "notes": "Check blood pressure",
            "due_at": _due_str(1),
            "status": "pending",
        }
        response = self.client.post(reverse("tasks:task_create"), data)
        self.assertRedirects(response, reverse("tasks:dashboard"))
        self.assertEqual(Task.objects.count(), 1)
        task = Task.objects.first()
        self.assertEqual(task.doctor, self.doctor_a)
        self.assertEqual(task.patient, self.patient_a)

    def test_create_task_with_other_doctors_patient_fails(self):
        data = {
            "patient": self.patient_b.pk,
            "title": "Should not create",
            "notes": "",
            "due_at": _due_str(1),
            "status": "pending",
        }
        response = self.client.post(reverse("tasks:task_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not one of the available choices")
        self.assertEqual(Task.objects.count(), 0)

    def test_create_form_patient_dropdown_scoped_to_doctor(self):
        response = self.client.get(reverse("tasks:task_create"))
        self.assertEqual(response.status_code, 200)
        patient_field = response.context["form"].fields["patient"]
        self.assertEqual(
            list(patient_field.queryset), [self.patient_a]
        )

    def test_doctor_cannot_update_other_doctors_task(self):
        task_b = Task.objects.create(
            doctor=self.doctor_b, patient=self.patient_b,
            title="Doctor B task", due_at=timezone.now(),
        )
        response = self.client.get(
            reverse("tasks:task_update", kwargs={"pk": task_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.post(
            reverse("tasks:task_update", kwargs={"pk": task_b.pk}),
            {"patient": self.patient_a.pk, "title": "Hacked", "notes": "",
             "due_at": _due_str(1), "status": "pending"},
        )
        self.assertEqual(response.status_code, 404)
        task_b.refresh_from_db()
        self.assertEqual(task_b.title, "Doctor B task")

    def test_doctor_cannot_complete_other_doctors_task(self):
        task_b = Task.objects.create(
            doctor=self.doctor_b, patient=self.patient_b,
            title="Doctor B task", due_at=timezone.now(),
        )
        response = self.client.post(
            reverse("tasks:task_complete", kwargs={"pk": task_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        task_b.refresh_from_db()
        self.assertEqual(task_b.status, "pending")


class DashboardSectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dr_a", password="pass123")
        self.doctor = Doctor.objects.create(user=self.user, full_name="Dr. A")
        self.patient = Patient.objects.create(
            doctor=self.doctor, full_name="Patient A", date_of_birth="2000-01-01",
            sex="M", mrn="MRN-A"
        )
        self.client.login(username="dr_a", password="pass123")

    def _create_task(self, title, days_offset=0, status="pending"):
        return Task.objects.create(
            doctor=self.doctor, patient=self.patient, title=title,
            due_at=timezone.now() + timedelta(days=days_offset), status=status,
        )

    def test_dashboard_buckets_tasks_correctly(self):
        today = self._create_task("Today task", days_offset=0)
        upcoming = self._create_task("Upcoming task", days_offset=2)
        completed = self._create_task("Completed task", days_offset=-1, status="completed")
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["today_tasks"]), [today])
        self.assertEqual(list(response.context["upcoming_tasks"]), [upcoming])
        self.assertEqual(list(response.context["completed_tasks"]), [completed])

    def test_mark_completed_moves_task_out_of_pending_sections(self):
        task = self._create_task("Today task", days_offset=0)
        response = self.client.post(
            reverse("tasks:task_complete", kwargs={"pk": task.pk})
        )
        self.assertRedirects(response, reverse("tasks:dashboard"))
        task.refresh_from_db()
        self.assertEqual(task.status, "completed")
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertEqual(list(response.context["today_tasks"]), [])
        self.assertEqual(list(response.context["completed_tasks"]), [task])

    def test_dashboard_only_shows_own_doctors_tasks(self):
        self._create_task("My task", days_offset=1)
        other_user = User.objects.create_user(username="dr_b", password="pass123")
        other_doctor = Doctor.objects.create(user=other_user, full_name="Dr. B")
        other_patient = Patient.objects.create(
            doctor=other_doctor, full_name="Patient B", date_of_birth="2000-01-01",
            sex="F", mrn="MRN-B"
        )
        Task.objects.create(
            doctor=other_doctor, patient=other_patient,
            title="Other doctor task", due_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertContains(response, "My task")
        self.assertNotContains(response, "Other doctor task")


class AuthRedirectTests(TestCase):
    def test_dashboard_redirects_unauthenticated(self):
        response = self.client.get(reverse("tasks:dashboard"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('tasks:dashboard')}")

    def test_create_redirects_unauthenticated(self):
        response = self.client.get(reverse("tasks:task_create"))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('tasks:task_create')}")

    def test_update_redirects_unauthenticated(self):
        response = self.client.get(reverse("tasks:task_update", kwargs={"pk": 1}))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('tasks:task_update', kwargs={'pk': 1})}"
        )
