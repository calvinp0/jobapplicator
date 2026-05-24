# Task 045: Backend API for revision-feedback-driven runs

Task ID: `045-backend-revision-feedback-api`

## Goal

Add the backend HTTP endpoint(s) that let the frontend submit revision
feedback against a prior draft and trigger a follow-up tailoring run.
The endpoint must persist the feedback (using task 044's model), create
a new `Run` linked to the prior draft, and write the feedback file into
the run's input directory per the run-directory contract.

## Background

Read first:

- `docs/adr/008-revision-feedback-flow.md`
- `docs/contracts/claude_run_directory.md` (post task 043)
- `backend/app/routers/runs.py`
- `backend/app/routers/resume_versions.py`
- `backend/app/run_directory.py`
- `backend/app/claude_worker.py`
- `backend/app/models.py` and `backend/app/schemas.py` (post task 044)
- `backend/tests/`

## Scope

- Add the API surface sketched in ADR-008 (typically a POST on the
  resume-version resource that creates a feedback record + a follow-up
  Run). The full URL and request body must match ADR-008's sketch.
- Persist the revision-feedback record using the storage from task 044.
- Create a new `Run` with the FK from task 044 pointing at the prior
  `ResumeVersion`.
- Extend the run-directory writer so the feedback file (filename per
  ADR-008 and contract from task 043) is written into
  `runs/<run_id>/input/` alongside the existing inputs.
- Return enough information in the response that the frontend can route
  to the new run (run id, paths).
- Add tests covering: happy path, prior-draft not found, feedback
  payload validation, follow-up run created with the FK populated, and
  the feedback file written into the input directory.

## Allowed files

```
backend/app/routers/**
backend/app/run_directory.py
backend/app/claude_worker.py
backend/app/run_import.py
backend/app/main.py
backend/app/schemas.py
backend/tests/**
agent_tasks/045-backend-revision-feedback-api.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/app/models.py
backend/app/db.py
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/**
```

Note: `backend/app/models.py` and `backend/app/db.py` are owned by task
044. If a change there is needed, raise it as a follow-up; do not edit
in this task.

## Out of scope

- Adding new columns / tables (task 044 owns persistence shape).
- Editing the runtime prompt (task 046).
- Frontend wiring (task 039).
- Changing existing tailoring-run behavior for first-draft runs.

## Acceptance criteria

- A `POST` endpoint matching the ADR-008 sketch exists and is reachable
  from the FastAPI app.
- Submitting feedback against an existing draft creates exactly one
  feedback record and exactly one new `Run` linked to that draft.
- The new run's input directory contains the feedback file with the
  filename from ADR-008 / task 043.
- Submitting feedback against a missing draft returns a 404.
- Invalid feedback payloads return 422 via schema validation.
- All existing tests still pass; new tests cover the cases above.

## Verification

```bash
pytest
```

## Git instructions

Commit locally on the task branch with the message:

```
Add backend API for revision-feedback-driven runs
```

Do not push.
