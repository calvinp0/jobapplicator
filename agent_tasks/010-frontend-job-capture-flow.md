# Task 010: Frontend Job Capture Flow

## Goal

Implement the frontend flow that lets the user review a pending job
capture, confirm it (creating a Job), and trigger a Claude run from the
confirmed job.

This task fills in the `/captures` and `/jobs` routes scaffolded by task
009. It consumes the capture endpoints from task 002 and the run-creation
endpoint from task 006.

## Background

Read:

- `docs/product_requirements.md` (MMVP workflow steps 6–9)
- `docs/architecture.md` (capture provider architecture, human-in-the-loop)
- `docs/adr/003-human-in-the-loop-submission.md`
- `agent_tasks/002-backend-models-and-capture-api.md` (capture/confirm
  endpoints)
- `agent_tasks/005-extension-capture.md` (payload shape from the
  extension)
- `agent_tasks/006-run-directory-writer.md` (POST /runs contract)
- `agent_tasks/009-frontend-shell.md` (existing shell)

## Scope

Within `frontend/src/`:

- `/captures` page that:
  - lists pending captures (`user_confirmed=false`) from `GET /captures`
  - shows each capture's extracted fields (company, title, location, URL,
    description excerpt, application method) in an editable form
  - "Confirm" button calls `POST /captures/{id}/confirm` and navigates to
    the resulting Job
- `/jobs/:id` page that:
  - shows the confirmed job
  - lets the user pick a master resume + evidence bank
  - "Generate resume" button calls `POST /runs` and navigates to the
    resulting run
- a small "pending captures" badge in the layout sidebar showing the
  count of unconfirmed captures
- vitest tests covering: confirm flow happy path with a mocked API,
  validation when required fields are missing, and generate-resume flow

## Allowed files

- `frontend/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed)

## Forbidden files

- `backend/**`
- `extension/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/**`
- Other `agent_tasks/*.md`

## Out of scope

- Resume version review/approval UI (later task).
- Application status timeline UI beyond what's needed to navigate from
  Job → existing applications.
- Direct file uploads or DOCX preview.
- Real-time updates / websockets.
- Any backend, extension, or contract changes.

## Acceptance criteria

- The user can: see a pending capture → edit fields → confirm → land on
  the new Job page → pick a resume + evidence bank → trigger a run.
- All HTTP calls are mocked in tests; tests do not require a running
  backend.
- Validation errors from the confirm endpoint surface clearly in the UI.
- `npm test` and `npm run build` pass.
- The capture payload shape consumed matches `backend/app/schemas.py`.

## Verification

Run from `frontend/`:

```bash
npm test
npm run build
```

## Git commit message

```text
Add frontend job capture flow
```

Do not push.
