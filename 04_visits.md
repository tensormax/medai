# App 4: `visits` — Build Instructions

## Context

Project: `clinic_ai` (Django). `accounts`, `patients`, and `tasks` are
already fully built. This app is the clinical timeline — a `Patient` has
many `Visit`s, a `Visit` has many `VisitMessage`s. This is also where the
project's first AI integration point gets wired in, via a **stub** service
layer. Real LLM calls, RAG, and document processing are explicitly **out of
scope for this app** and will be built later in `apps/ai` + `documents`. Do
not modify `models.py`.

**Existing model contract** (`apps/visits/models.py`):
- `Visit`: `patient` (FK), `doctor` (FK), `started_at`, `closed_at`
  (nullable), `status` (open/closed), `summary`.
- `VisitMessage`: `visit` (FK), `role` (doctor/ai), `content`,
  `created_at`.

## Dependencies

Requires `accounts` and `patients` to be complete. `tasks` does not need to
be referenced here. This app introduces the **first version** of
`apps/ai/facade.py` — that module does not exist yet; you are creating it
as part of this app's work, but it must be built as a standalone,
independently importable service, not tangled into `visits`' views.

## Step 1 — Explore

- Read `apps/visits/models.py`.
- Re-read `apps/patients/services.py` and `apps/tasks/services.py` for the
  established query-scoping pattern; follow the same convention here.
- Confirm the placeholder section left in `patient_detail.html` (from the
  `patients` app) — this is where the visit timeline gets rendered. Do
  not restructure the rest of that template.

## Step 2 — Plan (propose before coding)

Cover:
- Views/URL names: creating a visit, viewing a visit thread, posting a
  message within a visit.
- The exact interface for the AI facade — function signature, input,
  output — before writing its implementation. This contract matters more
  than the stub's internal logic, since real AI wiring will replace the
  internals later without (ideally) touching any calling code in
  `visits`.
- How the timeline partial will be included into `patient_detail.html`
  without that template needing to know `visits`' internal template
  structure.

## Step 3 — Code

### 3a. AI facade stub (`apps/ai/`)

Create `apps/ai/__init__.py` and `apps/ai/facade.py` with a single public
class, e.g.:

```python
class AIOrchestrator:
    @staticmethod
    def generate_visit_reply(visit, message_content: str) -> str:
        """
        Stub implementation. Real version will call an LLM via
        apps/ai/llm.py + apps/ai/prompts.py. For now, return a fixed,
        clearly-labeled placeholder so the rest of the system can be
        built and tested against a stable interface.
        """
        return (
            "[AI STUB] This is a placeholder response. "
            "Real LLM integration is not yet wired in."
        )
```

Do **not** build `llm.py`, `prompts.py`, `embeddings.py`, `retrieval.py`,
`chunking.py`, `deidentify.py`, or `vectorstore.py` in this pass — those
belong to a later phase. The only file that should exist in `apps/ai/`
right now is `facade.py` (plus `__init__.py`). `visits` must only ever
import `AIOrchestrator` from `apps.ai.facade` — never anything more
granular — so that swapping the stub for a real implementation later
requires zero changes in `visits`.

### 3b. `visits` app

1. `forms.py` — `VisitMessageForm` (just `content` — `role` is always
   `"doctor"` for anything a doctor submits, set in the view, not the
   form).
2. `services.py` — `create_visit(patient, doctor)`,
   `post_message(visit, content)` which saves the doctor's
   `VisitMessage`, then calls `AIOrchestrator.generate_visit_reply(...)`
   and saves the AI's reply as a second `VisitMessage` with
   `role="ai"`. Keep this orchestration here, not in `views.py`.
3. `views.py` — `visit_create` (from a patient detail page),
   `visit_detail` (full thread), `message_send`. Every view scoped to the
   logged-in doctor's own patients — same isolation rule as `patients`
   and `tasks`.
4. `urls.py` — register under a `visits/` prefix.
5. `templates/visits/` — `visit_detail.html` (full thread with a simple
   message form at the bottom), `_visit_card.html` (a short partial:
   date, status, summary — this is what gets included into
   `patient_detail.html`'s timeline placeholder). Plain HTML, extend
   `base.html`.
6. Update `patients/templates/patients/patient_detail.html` **only** to
   replace its visit-timeline placeholder with a loop over the patient's
   visits, including `visits/_visit_card.html` for each — this is the one
   sanctioned cross-app template edit.
7. `admin.py` — register `Visit` and `VisitMessage`.

## Step 4 — Test

Write `tests.py` covering:
- Creating a visit correctly links `patient` and `doctor`.
- Posting a message as a doctor creates a `VisitMessage` with
  `role="doctor"`, and a second `VisitMessage` with `role="ai"` is
  created automatically containing the stub's placeholder text.
- Doctor isolation: doctor A cannot view or post into doctor B's
  patient's visit, even via a crafted URL/POST (same pattern as prior
  apps).
- `AIOrchestrator.generate_visit_reply` is tested independently (call it
  directly, not through a view) to confirm it returns a string and never
  raises — this test will still be valid once the stub is replaced by a
  real LLM call, so keep the test focused on the contract (returns a
  non-empty string) rather than the stub's exact wording.

No outside services required — the AI facade being a stub means this
entire app is testable offline, with no API keys and no network calls.

## Definition of Done

- [ ] A doctor can open a patient, start a visit, post a message, and see
      both their message and a stub AI reply appear in the thread.
- [ ] Patient detail page renders the visit timeline via
      `_visit_card.html`, most recent visit first.
- [ ] `apps/ai/facade.py` exists with exactly the `AIOrchestrator`
      interface above (or your planned equivalent) — no real LLM calls,
      no API keys required to run tests.
- [ ] All tests pass with `python manage.py test apps.visits`.
- [ ] `python manage.py check` reports no issues.

## Commit

`feat(visits): visit timeline + messaging, AI facade stub`

## Note for later (do not act on this now)

Once this app is merged, the next phase replaces the stub's internals
(`AIOrchestrator.generate_visit_reply`) with a real LLM call, and adds
`documents` (report generation + RAG) as a separate later app, calling the
same `AIOrchestrator` facade rather than a new entry point. Nothing in
`visits` should need to change when that happens — that's the point of the
facade boundary built here.
