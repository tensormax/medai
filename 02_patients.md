# App 2: `patients` — Build Instructions

## Context

Project: `clinic_ai` (Django). The `accounts` app is already fully built —
doctors can register, log in, and log out. This app is the master patient
record: every other app in the project (visits, documents, tasks)
references `Patient` by ForeignKey. Do not modify `models.py`.

**Existing model contract** (`apps/patients/models.py`):
- `Patient`: `doctor` (FK → `Doctor`), `full_name`, `date_of_birth`, `sex`
  (choices), `mrn` (unique), `phone_number`, `address`, `created_at`,
  `updated_at`.

## Dependencies

Requires `accounts` to be complete (a logged-in `Doctor` must exist for any
of this app's views to make sense). Do not add any import of `visits`,
`documents`, or `tasks` into this app — `patients` must stay independent of
everything built after it.

## Step 1 — Explore

- Read `apps/patients/models.py` and `apps/accounts/models.py`.
- Read `apps/accounts/views.py` and `urls.py` to match the existing
  conventions (how auth is enforced, how templates extend `base.html`,
  naming style for URL names).
- Confirm how `request.user.doctor_profile` is accessed (the
  `related_name` on `Doctor.user` — use this, don't re-query `Doctor`
  by hand in every view).

## Step 2 — Plan (propose before coding)

Cover:
- The views you'll build and their URL names (list, detail, create,
  update — decide if delete is in scope; recommend soft-disable instead
  of hard delete for a medical record, but flag this decision rather than
  assuming).
- How every queryset will be scoped to `request.user.doctor_profile` so a
  doctor can never see another doctor's patients — this is the most
  important correctness property of this app and needs to be explicit in
  the plan, not just "implied" by the FK existing.
- Form fields and validation (e.g. `date_of_birth` sanity check, `mrn`
  uniqueness message).

## Step 3 — Code

Build in this order:
1. `forms.py` — `PatientForm` (all fields except `doctor`, which is set
   from `request.user` in the view, never from form input — a doctor
   should never be able to submit a form claiming a patient belongs to a
   different doctor).
2. `services.py` — a `get_patients_for(doctor)` helper and similar
   scoped-query helpers. Keep query-scoping logic here rather than
   repeated inline in every view, so later apps (tasks, visits) can reuse
   the same pattern for consistency.
3. `views.py` — `patient_list`, `patient_detail`, `patient_create`,
   `patient_update`. Every view must call `login_required` and must scope
   by the logged-in doctor — a detail/update view for a patient outside
   the logged-in doctor's list should 404, not error out or leak data.
4. `urls.py` — register under a `patients/` prefix.
5. `templates/patients/` — `patient_list.html`, `patient_detail.html`
   (leave a clearly marked placeholder section for the visit timeline —
   the `visits` app will fill this in later, don't build it now),
   `patient_form.html` (shared by create/update). Plain HTML, extend
   `base.html`.
6. `admin.py` — register `Patient` with `list_display` showing
   `full_name`, `mrn`, `doctor`, and `search_fields` on `full_name`/`mrn`.

## Step 4 — Test

Write `tests.py` covering:
- A doctor can create a patient; the patient's `doctor` field is correctly
  set from the logged-in user, not from form input.
- **Doctor isolation (critical):** create two doctors, each with a
  patient. Log in as doctor A — confirm `patient_list` shows only their
  patient, and that requesting doctor B's patient detail/update URL
  directly returns 404, not their data.
- `mrn` uniqueness is enforced at the form level with a clear error.
- Unauthenticated requests to any view redirect to login.

No outside services required.

## Definition of Done

- [ ] A logged-in doctor can create, list, view, and edit only their own
      patients — manually verified with two separate doctor accounts.
- [ ] All tests pass with `python manage.py test apps.patients`.
- [ ] `patient_detail.html` has a clearly marked, empty placeholder for
      the visit timeline (do not implement it here).
- [ ] `python manage.py check` reports no issues.

## Commit

`feat(patients): CRUD scoped to logged-in doctor`
