# App 1: `accounts` — Build Instructions

## Context

Project: `clinic_ai` (Django). Apps live under `apps/<name>/`, imported as
`apps.<name>` in `INSTALLED_APPS`. This is the **first app** — nothing else
in the project exists yet except this app's `models.py`, which is already
written and frozen. Do not modify `models.py` unless you find a genuine bug;
if you think a field is missing, stop and flag it instead of changing the
model silently.

**Existing model contract** (`apps/accounts/models.py`):
- `Doctor`: `user` (OneToOne → `auth.User`), `full_name`, `specialization`,
  `license_number` (unique, nullable), `phone_number`, `created_at`.

Only doctors authenticate in this system. There is no separate patient-facing
login anywhere in the project.

## Dependencies

None. This app must be fully working before any other app is started —
every other app's views will require a logged-in `Doctor`.

## Step 1 — Explore (do this before writing any code)

- Read `apps/accounts/models.py` in full.
- Read `config/settings.py` to confirm `AUTH_USER_MODEL`, `LOGIN_URL`,
  `LOGIN_REDIRECT_URL`, `TEMPLATES` dirs, and installed apps.
- Check whether `templates/base.html` exists yet. If not, you will need to
  create a minimal one (nav bar placeholder, `{% block content %}`).

## Step 2 — Plan (propose this before coding, wait for confirmation)

Produce a short plan covering:
- The exact views you'll build and their URL names.
- The exact forms you'll build (fields, validation rules).
- Which parts of Django's built-in auth views/forms you're reusing vs.
  writing from scratch (prefer reusing `django.contrib.auth` views for
  login/logout/password reset — do not reinvent password hashing or
  session handling).
- How `Doctor` gets created relative to `User` — recommended: a single
  registration form that creates both in one transaction.

## Step 3 — Code (after plan is approved)

Build in this order:
1. `forms.py` — `DoctorRegistrationForm` (wraps `User` creation +
   `Doctor` fields), `DoctorProfileForm` (edit `full_name`,
   `specialization`, `phone_number` only — never let a doctor edit
   `license_number` or `user` after creation without extra confirmation).
2. `views.py` — `register`, `profile` (view + edit). Use Django's built-in
   `LoginView` / `LogoutView` / password-reset views wired through
   `urls.py` rather than custom ones.
3. `urls.py` — register all of the above under an `accounts/` prefix.
4. `templates/accounts/` — `register.html`, `login.html`, `profile.html`,
   password-reset templates. Plain HTML, extend `base.html`, no CSS
   framework needed yet — functionality over styling at this stage.
5. `admin.py` — register `Doctor` with `list_display` showing
   `full_name`, `specialization`, `user`.
6. `signals.py` — only if you find you need one (e.g. auto-creating a
   blank `Doctor` on `User` creation). Prefer doing this explicitly in
   the registration view instead of a signal unless there's a clear
   reason a signal is better — signals make the creation flow harder to
   trace for whoever debugs this next.

## Step 4 — Test

Write `tests.py` covering:
- Registering a doctor creates exactly one `User` and one `Doctor`,
  correctly linked.
- Registering with a duplicate `license_number` is rejected.
- An unauthenticated request to `profile` redirects to login.
- Logging in with correct/incorrect credentials behaves as expected.
- Password reset flow sends an email (use Django's test `EmailBackend`,
  don't hit a real SMTP server).
- Editing a profile does not allow changing another doctor's record
  (test with two `Doctor` accounts).

No outside services are required for this app — everything is testable
with Django's local test database and test client.

## Definition of Done

- [ ] A doctor can register, log in, view/edit their profile, log out,
      and reset their password — end to end, manually verified.
- [ ] All tests above pass with `python manage.py test apps.accounts`.
- [ ] `python manage.py check` reports no issues.
- [ ] No other app is referenced from this app's code.

## Commit

One commit per logical step is fine, but the final state should be a
single clean commit (or squashed set) with message:
`feat(accounts): registration, login, profile, password reset`
