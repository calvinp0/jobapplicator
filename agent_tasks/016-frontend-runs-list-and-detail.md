# Task 016: Frontend runs list and run detail enhancements

## Goal

Make the `/runs` route useful and complete the run detail page so the
operator can invoke a Claude Code run, see its status, import its
outputs into a `ResumeVersion`, and surface errors. The existing
`/runs` route is a placeholder, and `/runs/:id` only shows id and
status — the operator currently has no way to drive an invocation
from the UI.

## Background

Read:

- `docs/product_requirements.md` (MMVP steps 7–10)
- `docs/contracts/claude_run_directory.md` (expected outputs and
  write boundary)
- `backend/app/routers/runs.py` (existing `POST /runs/{id}/invoke`
  and `POST /runs/{id}/import`)
- `backend/app/claude_worker.py` (status transitions used by invoke)
- `backend/app/run_import.py` (status transition used by import)
- `agent_tasks/007-claude-code-worker.md`
- `agent_tasks/008-resume-version-import.md`
- `frontend/src/pages/RunDetailPage.tsx` (current placeholder-ish
  detail page)
- `frontend/src/pages/RunsPage.tsx` (current placeholder)

## Scope

Within `frontend/src/`:

- Add API client functions in `frontend/src/api/index.ts`:
  - `invokeRun(runId)` → `POST /runs/{id}/invoke`
  - `importRun(runId)` → `POST /runs/{id}/import` returning a
    `ResumeVersion`
  - `listResumeVersions()` and `getResumeVersion(id)` (read-only) so
    the run detail can find the version created from a given run
- Extend `frontend/src/api/types.ts` with a `ResumeVersion` type
  matching `backend/app/schemas.py:ResumeVersionRead`.
- Replace `frontend/src/pages/RunsPage.tsx`:
  - List runs from `listRuns()` with id, status, created_at, and a
    link to `/runs/:id`. Sort by `created_at desc`. Empty-state
    message when no runs exist.
- Replace `frontend/src/pages/RunDetailPage.tsx`:
  - Show id, status, run_dir, created_at, started_at, completed_at,
    error_message, and the prompt/input/output hashes (truncated for
    display).
  - Show an **Invoke** button when status is `"created"`; disable
    otherwise. Calling it should call `invokeRun` and refresh the
    run.
  - Show an **Import outputs** button when status is `"completed"`;
    disable otherwise. Calling it should call `importRun` and, on
    success, navigate to the resulting resume version (or display a
    link to it on the same page — your call, but make the link
    obvious).
  - If a `ResumeVersion` already exists for this run (i.e.
    `status == "imported"`), surface it as a link without re-importing.
  - Surface backend errors via the `ApiError.message` / body
    pattern used elsewhere.
- Tests in `frontend/src/test/`:
  - Smoke test that `/runs` renders the list with a mocked API.
  - Run detail: invoke transitions the displayed status and disables
    the Invoke button.
  - Run detail: import on a completed run calls `importRun` and the
    new resume version becomes visible.
  - Run detail: import on a non-completed run does not call
    `importRun`.

## Allowed files

- `frontend/src/pages/RunsPage.tsx`
- `frontend/src/pages/RunDetailPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly
  instructed)

## Forbidden files

- `backend/**`
- `extension/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/**`
- Other `agent_tasks/*.md`
- Frontend files outside the allowed list (in particular,
  `frontend/src/App.tsx`, `frontend/src/layout/**`, and other pages)

## Out of scope

- Resume-version approval UI (task 017).
- Opening the generated DOCX (task 017).
- Applications submit flow (task 018).
- Long-polling or websocket status updates — refreshing on action is
  enough.
- Cancelling / retrying runs.

## Acceptance criteria

- `/runs` lists existing Claude runs with their status and a link to
  the detail page.
- `/runs/:id` shows the full run record and exposes Invoke and
  Import actions gated on status.
- After invoke, the page reflects the updated status.
- After import, the resulting resume version is reachable from the
  run detail page (link or navigation).
- `npm test` and `npm run build` pass from `frontend/`.
- No backend, extension, or doc files are touched.

## Verification

Run from `frontend/`:

```bash
npm test
npm run build
```

## Git instructions

Commit message:

```text
Add frontend runs list and run detail actions
```

Do not push.
