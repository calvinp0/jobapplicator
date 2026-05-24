# Task 048: Fix Tailoring Progress and Import Failure UX

## Goal

Make the "Generate draft" experience honest, visible, and user-friendly.

Currently the UI can say "Draft ready to review" while import is failing because expected output files are missing. The frontend also repeatedly calls `/runs/{id}/import` after a 400 error, spamming the backend.

This task fixes the tailoring progress UX and import failure behavior.

Do not implement new product features.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Current Problems

Observed behavior:

```text
POST /runs
POST /runs/{id}/invoke
GET /runs/{id}
POST /runs/{id}/import → 400
POST /runs/{id}/import → 400
POST /runs/{id}/import → 400
...
```

The UI shows:

```text
Draft ready to review
```

while the backend says:

```text
expected output file missing: output/tailored_resume.docx
```

This is incorrect. A run is not ready for review until outputs have been successfully imported into a ResumeVersion.

## Scope

Update:

```text
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/styles.css
frontend/src/test/**
```

Optional backend update if small and useful:

```text
backend/app/routers/runs.py
backend/app/schemas.py
backend/tests/**
```

Do not edit unrelated backend behavior.

## Required Behavior

### 1. Correct run status language

Update user-facing status logic:

```text
created   → Queued
running   → Tailoring in progress
completed → Tailoring finished — loading draft
imported  → Draft ready to review
failed    → Tailoring failed
```

A run with status `completed` must not be shown as `Draft ready to review` unless a ResumeVersion exists for that run.

If status is `completed` and import fails, show:

```text
Draft could not be loaded
```

with the parsed backend detail.

### 2. Add visible progress while generating

In the JobDetailPage "Generate a draft" step, show a progress panel while a run is active.

The panel should include:

```text
current status label
spinner or animated indicator
elapsed time or last updated time
clear explanatory copy
link to run details
```

Example copy:

```text
Tailoring in progress...
The app is generating a draft using your selected resume and evidence bank.
This can take a little while.
```

When the run becomes completed:

```text
Tailoring finished. Loading the generated draft...
```

When imported:

```text
Draft ready to review.
```

When import fails:

```text
The tailoring run finished, but the draft could not be loaded.
expected output file missing: output/tailored_resume.docx
```

### 3. Stop infinite import retries

The frontend must call `importRun(runId)` at most once per completed run transition unless the user explicitly clicks retry.

If import fails:

```text
- stop automatic import attempts
- store/display the error
- show "Retry loading draft"
- do not keep POSTing /import every poll interval
```

### 4. Improve RunDetailPage

RunDetailPage should show:

```text
Tailoring progress
Current status
Useful error message
Retry loading draft button when import failed
Advanced details
```

Default UI must not show raw request paths.

Raw status, run id, path, hashes, and operator controls stay under Advanced details.

### 5. Optional run log preview

If straightforward, expose recent `run.log` contents in the UI.

Acceptable minimal implementation:

```text
Show a "Recent activity" block that displays the last N lines from run.log.
```

If this requires too much backend work, leave it as a future task and only show status/elapsed-time feedback in this task.

## Acceptance Criteria

- The UI never says `Draft ready to review` for a run whose outputs failed to import.
- A completed-but-not-imported run says `Tailoring finished — loading draft`.
- Import failure says `Draft could not be loaded` plus parsed backend detail.
- Automatic import is attempted only once per completed run transition.
- After import failure, the user sees a `Retry loading draft` button.
- The backend is not spammed with repeated `/runs/{id}/import` POSTs after a 400.
- JobDetailPage shows visible progress while tailoring is running.
- RunDetailPage shows useful progress/error state.
- Raw request-path errors are not shown in default UI.
- Frontend tests pass.
- Frontend build passes.

## Verification

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Manually verify:

1. Open a job.
2. Click Generate draft.
3. Confirm progress UI appears immediately.
4. Confirm status changes while polling.
5. Simulate or observe an import failure.
6. Confirm only one automatic import attempt occurs.
7. Confirm the UI shows a friendly error and a manual retry button.

## Git

Commit with:

```text
Fix tailoring progress and import failure UX
```

Do not push.
