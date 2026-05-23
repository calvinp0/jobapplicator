# Task 014: Backend application submit, events, and open-file endpoint

## Goal

Round out the backend surface area the cockpit needs to drive the
MMVP workflow end-to-end before Gmail integration. Add an
application-submit transition with timeline events, a read endpoint
for application events, and a small "open generated file" endpoint
that the frontend can call to open a resume DOCX in the user's
default application (PRD step 10 and step 12).

These are the last backend pieces needed to make the cockpit usable
end-to-end. Frontend tasks 015–018 depend on this.

## Background

Read:

- `docs/product_requirements.md` (MMVP steps 10–12, application
  tracking, human-in-the-loop)
- `docs/architecture.md` (Claude Code worker boundary,
  human-in-the-loop rule)
- `docs/adr/003-human-in-the-loop-submission.md`
- `docs/adr/002-claude-code-worker-boundary.md`
- `backend/app/models.py` (existing `Application`,
  `ApplicationEvent`, `ResumeVersion`)
- `backend/app/routers/applications.py` (current applications router)
- `backend/app/routers/resume_versions.py` (current resume-versions
  router)
- `agent_tasks/008-resume-version-import.md`

## Scope

Within `backend/`:

- Add a Pydantic schema for `ApplicationEventRead` and (optionally)
  `ApplicationEventCreate` mirroring the `ApplicationEvent` model.
- Extend `backend/app/routers/applications.py`:
  - `POST /applications/{id}/submit` — transitions an application to
    `status="submitted"`, sets `submitted_at=now()`, and inserts an
    `ApplicationEvent` row with `event_type="submitted"`. Idempotent:
    a second call on a submitted application returns the existing row
    without creating a duplicate event. Returns the updated
    application.
  - `POST /applications/{id}/events` — records a manual event with a
    user-supplied `event_type` and optional `notes`. Returns the
    created event.
  - `GET /applications/{id}/events` — returns the events for the
    application, ordered by `event_time` ascending.
- Add a small "open file" endpoint. Place it under a new
  `backend/app/routers/files.py` and wire it in `backend/app/main.py`:
  - `POST /files/open` with body `{ "path": "..." }` (or
    `{ "resume_version_id": "..." }`) that asks the host OS to open
    the file using `xdg-open` / `open` / `start` as appropriate.
  - The endpoint must reject any path that is not inside the run
    directory tree or the resume-versions tree (resolve symlinks and
    check `Path.resolve().is_relative_to(...)`).
  - The OS-level "open" invocation should be wrapped in a function
    that pytest can monkeypatch — tests must not actually launch a GUI
    app. Use `subprocess.Popen` with a clearly-named indirection like
    `_spawn_open_command(path)`.
  - Returns `204 No Content` on success, `404` if the resume version
    or path is unknown, `400` if the path is outside the allowed
    roots.
- Add pytest coverage for:
  - submit happy path (sets status, sets `submitted_at`, creates one
    event)
  - submit idempotency (second submit is a no-op for events)
  - event creation + listing in order
  - open-file rejects paths outside the allowed roots
  - open-file invokes the spawn helper exactly once with the resolved
    path (monkeypatch)
  - open-file via resume_version_id resolves to the version's
    `docx_path`

## Allowed files

- `backend/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly
  instructed by the operator)

## Forbidden files

- `extension/**`
- `frontend/**`
- `runs/**` at commit time
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/contracts/**`
- Other `agent_tasks/*.md`

## Out of scope

- Frontend changes (handled in tasks 015–018).
- New ADRs or contract changes.
- Gmail / `EmailLink` flows.
- Cancel / withdraw / status transitions other than `submitted` (the
  existing `POST /applications` already lets the operator pick any
  valid status when creating; further transitions are a later task).
- Auditing or persisting which app actually opened the file.
- Changing existing endpoints' shapes.

## Acceptance criteria

- `POST /applications/{id}/submit` transitions the row exactly once,
  sets a UTC `submitted_at`, and creates one
  `event_type="submitted"` row.
- `POST /applications/{id}/events` and
  `GET /applications/{id}/events` work and return events ordered
  ascending by `event_time`.
- `POST /files/open` refuses paths outside `runs/` and the resume
  version directory tree.
- The OS-launch call is isolated behind a helper that pytest
  monkeypatches; tests do not spawn a real GUI app.
- All existing pytest tests still pass; new tests cover the rules
  above.

## Verification

```bash
pytest
```

## Git instructions

Commit message:

```text
Add application submit, events, and open-file endpoint
```

Do not push.
