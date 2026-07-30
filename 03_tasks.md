# App 3: `tasks` — Build Instructions

## Context

Project: `clinic_ai` (Django). `accounts` and `patients` are already fully
built. This app is the doctor's own dashboard: today's tasks, upcoming
follow-ups, completed items. It is deliberately independent of the clinical
timeline (`visits`) — a `Task` is administrative/future-facing, not a
clinical record. Do not modify `models.py`.

**Existing model contract** (`apps/tasks/models.py`):
- `Task`: `doctor` (FK → `Doctor`), `patient` (FK → `Patient`),
  `linked_visit` (FK → `Visit`, nullable — **leave this field alone for
  now**, `visits` doesn't exist yet so it will always be null in this
  app's build), `title`, `notes`, `due_at`, `status` (pending/completed),
  `created_at`.

## Dependencies

Requires `accounts` and `patients` to be complete. Do not import or
reference `visits` or `documents` — they don't exist yet. The
`linked_visit` field exists on the model already but should not be
exposed in any form or view built in this pass; leave it untouched
(always null) until the `visits` app exists.

## Step 1 — Explore

- Read `apps/tasks/models.py`, and re-read `apps/patients/services.py`
  for the query-scoping pattern already established there — reuse the
  same approach (a `services.py` helper scoped to `doctor`) rather than
  inventing a new convention.
- Confirm how `patients` app scopes querysets to the logged-in doctor;
  `tasks` must follow an equivalent rule scoped to both `doctor` and,
  transitively, only patients that belong to that doctor.

## Step 2 — Plan (propose before coding)

Cover:
- Views and URL names — this app is primarily one dashboard view with
  three sections (today / upcoming / completed) plus create/update for a
  single task.
- How the "today" / "upcoming" / "completed" split will be queried
  (date filtering on `due_at`, plus `status`).
- Whether task creation should be reachable from the patient detail page
  as well as its own form (recommend yes — flag this in the plan since it
  touches the `patients` app's templates, not just `tasks`).

## Step 3 — Code

Build in this order:
1. `forms.py` — `TaskForm` (`patient`, `title`, `notes`, `due_at`,
   `status`; `doctor` set from `request.user`, never from form input).
   The `patient` field's queryset must be restricted to the logged-in
   doctor's patients only — this is the same isolation rule as in
   `patients`, and it's easy to forget on a dropdown field specifically,
   so double check the form field's queryset, not just the view.
2. `views.py` — `dashboard` (today/upcoming/completed sections),
   `task_create`, `task_update` (including a quick "mark completed"
   action).
3. `urls.py` — register under a `tasks/` prefix.
4. `templates/tasks/` — `dashboard.html`, `task_form.html`. Plain HTML,
   extend `base.html`. If you're adding a "new task" link on
   `patient_detail.html` (from the `patients` app), make that a small,
   clearly-labeled addition — don't restructure that template.
5. `admin.py` — register `Task` with `list_display` showing `title`,
   `patient`, `doctor`, `due_at`, `status`.

## Step 4 — Test

Write `tests.py` covering:
- A doctor can create a task only for their own patients — attempting to
  submit a task with another doctor's patient ID (bypassing the dropdown,
  e.g. via a raw POST) must fail validation, not silently succeed.
- Dashboard sections correctly bucket tasks into today / upcoming /
  completed.
- Doctor isolation: doctor A cannot see or edit doctor B's tasks (same
  pattern as the `patients` app tests — reuse that structure).
- Marking a task completed updates `status` and moves it out of the
  pending sections on next dashboard load.

No outside services required.

## Definition of Done

- [ ] Dashboard correctly shows today's / upcoming / completed tasks for
      the logged-in doctor only.
- [ ] A task cannot be created against a patient outside the logged-in
      doctor's own list, even via a crafted request.
- [ ] All tests pass with `python manage.py test apps.tasks`.
- [ ] `linked_visit` is untouched (always null) — confirm no form or view
      in this app references it.
- [ ] `python manage.py check` reports no issues.

## Commit

`feat(tasks): dashboard with today/upcoming/completed, scoped to doctor`
