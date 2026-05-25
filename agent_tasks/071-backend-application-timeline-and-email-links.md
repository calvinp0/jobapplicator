# Task 071: Backend application timeline stage and email-link endpoints

Task ID: `071-backend-application-timeline-and-email-links`

## Goal

Implement the backend surface described in
`docs/contracts/application_status.md`: extend `ApplicationRead` with
`timeline_stage`, `last_email_link`, and `email_link_count`; add
schemas and endpoints for `EmailLink` (create + list); and apply the
per-classification side effects on `Application.status` and
`ApplicationEvent`.

## Background

Read first:

- `docs/adr/010-application-status-timeline.md` (lands in task 069)
- `docs/contracts/application_status.md` (lands in task 070) — this
  is the source of truth for field names, endpoint shapes, and rules
- `backend/app/models.py` (`Application`, `ApplicationEvent`,
  `EmailLink`, `APPLICATION_STATUSES`)
- `backend/app/schemas.py` (existing `ApplicationRead`,
  `ApplicationEventRead`)
- `backend/app/routers/applications.py` (the existing
  router; this task extends it rather than splitting it)
- `backend/app/main.py` (router registration)
- `backend/tests/test_application_submit.py` (or the analogous
  existing test file for applications, whichever covers
  `/applications/*` endpoints)

## Scope

Implement strictly to the contract. Notable concrete steps:

- **Vocabulary**: define a module-level tuple
  `EMAIL_CLASSIFIED_STATUSES = ("confirmation", "rejection",
  "next_step", "offer", "other")` (mirroring the existing pattern for
  `APPLICATION_STATUSES`). Validate inputs against it on the create
  endpoint.

- **Schemas** in `backend/app/schemas.py`:
  - Add `EmailLinkRead` with the fields listed in the contract.
  - Add `EmailLinkCreate` with the request body listed in the
    contract.
  - Extend `ApplicationRead` with `timeline_stage: str`,
    `last_email_link: EmailLinkRead | None`,
    `email_link_count: int`.

- **Derivation**: add a pure helper (e.g. `compute_timeline_stage` in
  `backend/app/routers/applications.py` or a small new module —
  whichever keeps the diff smaller) that takes
  `(application, email_links)` and returns one of the contract stage
  strings. Use it consistently in both list and detail responses.

- **Endpoints** under the existing `applications` router prefix:
  - `POST /applications/{application_id}/email-links` —
    create an `EmailLink`, validate `classified_status`, apply the
    per-classification side effects (`Application.status` update and
    `ApplicationEvent` append) defined in the contract, and return the
    new `EmailLinkRead` with 201.
  - `GET /applications/{application_id}/email-links` — list email
    links ordered by `received_at` desc then `created_at` desc.

- **Response wiring**: `list_applications`, `get_application`, and
  `submit_application` must populate the new `ApplicationRead` fields
  (`timeline_stage`, `last_email_link`, `email_link_count`). Make sure
  N+1 queries are avoided in the list case — eager-load
  `Application.email_links` or batch-load once.

- **Idempotency / dedupe**: if a create request arrives with a
  `gmail_message_id` that already exists for the same application,
  return 200 with the existing row (and do not append a duplicate
  event or re-apply the status change). The contract treats
  `gmail_message_id` as a logical unique key per application.

- **Tests** under `backend/tests/`:
  - Cover each `classified_status` value's side effects on
    `Application.status` and `ApplicationEvent`.
  - Cover the precedence rules (e.g. `rejection` should not move a
    `withdrawn` application).
  - Cover the derived `timeline_stage` for each ADR-010 stage.
  - Cover idempotent re-create with the same `gmail_message_id`.
  - Cover 404 on unknown `application_id`.
  - Cover 422 on invalid `classified_status`.

## Allowed files

```
backend/app/models.py
backend/app/schemas.py
backend/app/db.py
backend/app/main.py
backend/app/routers/applications.py
backend/app/routers/email_links.py
backend/tests/**
agent_tasks/071-backend-application-timeline-and-email-links.md
agent_tasks/queue.yaml
```

A new file `backend/app/routers/email_links.py` is allowed but only
if it keeps the application-scoped endpoints; otherwise extend
`backend/app/routers/applications.py`. Pick one approach and stick
with it.

## Forbidden files

```
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/adr/**
docs/contracts/**
docs/product_requirements.md
docs/architecture.md
```

Do not edit `backend/app/claude_worker.py`, `run_directory.py`,
`run_import.py`, or `word_handoff.py` — this task is application-
tracking only.

## Out of scope

- Any Gmail API, MCP, OAuth, or polling code (no network calls to
  Google services).
- Automated classification logic (the create endpoint trusts the
  caller's `classified_status`).
- Frontend changes.
- Schema migrations for new database columns (none are needed; the
  `EmailLink` table already exists).
- Renaming or removing existing `APPLICATION_STATUSES` values.

## Acceptance criteria

- `pytest` passes.
- New tests exist for each `classified_status` side effect, for the
  derivation of each timeline stage, for idempotent re-create, and
  for the 404/422 error cases.
- `ApplicationRead` returns `timeline_stage`, `last_email_link`, and
  `email_link_count` on every endpoint that returns it
  (`list_applications`, `get_application`, `submit_application`,
  `create_application`).
- The list endpoint does not produce N+1 queries (verified with a
  test that creates ≥3 applications with email links and asserts
  query count or — simpler — eager-loads with `joinedload`).
- `EMAIL_CLASSIFIED_STATUSES` is defined as a module-level tuple and
  reused as the validation source.
- The create endpoint is idempotent on `(application_id,
  gmail_message_id)`.
- No file outside `Allowed files` is modified.

## Verification

```bash
pytest
```

## Git instructions

Commit locally on the task branch with the message:

```
Add application timeline stage and email-link endpoints
```

Do not push.
