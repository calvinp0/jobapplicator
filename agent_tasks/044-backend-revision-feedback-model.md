# Task 044: Backend model and schema for revision feedback

Task ID: `044-backend-revision-feedback-model`

## Goal

Add the backend persistence layer for revision feedback as decided in
ADR-008: the storage table/columns, the foreign-key linking a follow-up
run/draft to its prior draft, and the matching Pydantic schemas. This
task adds no new HTTP endpoints — task 045 wires those.

## Background

Read first:

- `docs/adr/008-revision-feedback-flow.md` (lands in task 042)
- `docs/contracts/claude_run_directory.md` (after task 043 lands)
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/db.py`
- `backend/tests/` (existing model/integration patterns)

## Scope

- Implement the storage choice from ADR-008 (new table vs new columns).
- Add the foreign-key column(s) named in ADR-008 that point a follow-up
  `Run` (and the `ResumeVersion` it produces) at the prior `ResumeVersion`.
  Nullable; only set for follow-up runs.
- Add Pydantic schemas in `backend/app/schemas.py` for revision-feedback
  create / read shapes, matching the ADR's API sketch.
- Update `backend/app/db.py` table-creation logic so a fresh local
  database includes the new column(s)/table without manual migration.
- Add unit/integration tests under `backend/tests/` covering:
  - the new column(s) exist on a fresh DB
  - the FK constraint behaves correctly when set vs null
  - the new schemas validate a representative payload
- Do not add any new HTTP route in this task; that is task 045.

## Allowed files

```
backend/app/models.py
backend/app/schemas.py
backend/app/db.py
backend/tests/**
agent_tasks/044-backend-revision-feedback-model.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/app/routers/**
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/run_import.py
backend/app/main.py
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/**
```

## Out of scope

- HTTP routes / API endpoints (task 045).
- Writing the new feedback file into `runs/<run_id>/input/` (task 045).
- Runtime prompt changes (task 046).
- Frontend (task 039).

## Acceptance criteria

- A fresh SQLite database initialized via `backend/app/db.py` contains
  the new revision-feedback storage from ADR-008.
- The follow-up FK column(s) named in ADR-008 exist and are nullable
  where ADR-008 says they should be.
- Pydantic schemas for the create/read shapes are exported from
  `backend/app/schemas.py`.
- All new tests pass and existing `pytest` runs remain green.
- No file under `backend/app/routers/`, `frontend/`, `runtime_prompts/`,
  or `docs/` is modified.

## Verification

```bash
pytest
```

## Git instructions

Commit locally on the task branch with the message:

```
Add backend model and schemas for revision feedback
```

Do not push.
