# Task 050: Show Live Tailoring Progress Log

## Goal

Show meaningful one-line progress feedback while a tailored resume is being generated.

Currently the frontend shows a spinner or generic status while Claude Code is running. The user cannot tell whether anything is happening, what stage the tailoring process is in, or why it failed.

The app should show recent progress lines during generation, such as:

```text
Preparing tailoring inputs
Launching Claude Code
Claude is reading the job description
Claude is comparing the job against the master resume
Claude is drafting the tailored resume
Claude is writing output files
Validating generated output files
```

This task should surface existing run activity and add worker-owned progress milestones where Claude output is too sparse.

Do not implement Gmail.
Do not implement LinkedIn automation.
Do not change the tailoring prompt content except if needed to improve progress logging.

## Current Problem

A run can now correctly fail when required output files are missing:

```text
Tailoring failed
expected output file missing: output/tailored_resume.docx, output/tailored_resume.md, output/change_log.md, output/claim_audit.md
```

But the user still does not see what happened during generation.

The UI should show recent activity while the run is active and after it fails, so the user can tell whether Claude started, whether it wrote anything, and where the failure happened.

## Background

Inspect:

```text
backend/app/claude_worker.py
backend/app/routers/runs.py
backend/app/schemas.py
backend/app/run_directory.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/lib/workflow.ts
frontend/src/styles.css
frontend/src/test/**
docs/contracts/claude_run_directory.md
```

The worker already writes subprocess stdout/stderr to the run directory log file. The frontend should be able to display recent log lines while the run is active.

If Claude Code itself emits sparse or unhelpful output, the worker should also write its own progress milestones to the same log.

## Scope

Update:

```text
backend/app/claude_worker.py
backend/app/routers/runs.py
backend/app/schemas.py
backend/tests/**
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/styles.css
frontend/src/test/**
docs/contracts/claude_run_directory.md
```

Do not edit unrelated backend or frontend behavior.

## Required Backend Behavior

Add an endpoint:

```http
GET /runs/{run_id}/log
```

It should return recent log lines from:

```text
<run_dir>/run.log
```

Suggested response shape:

```json
{
  "run_id": "df0490fe-db05-419f-8eff-88d990143d22",
  "lines": [
    "jobapply: preparing tailoring inputs",
    "jobapply: launching Claude Code",
    "claude: reading job description",
    "jobapply: validating output files",
    "jobapply: missing expected output file: output/tailored_resume.docx"
  ],
  "truncated": false
}
```

Requirements:

- Return `404` if the run does not exist.
- Return an empty `lines` list if the run exists but `run.log` does not exist yet.
- Limit output to recent lines only, for example the last 40 lines.
- Strip ANSI escape codes if practical.
- Do not return huge logs.
- Do not expose files outside the run directory.
- Do not require the run to be completed.
- Add backend tests.

## Worker Progress Milestones

Update the worker so it writes clear progress milestones into `run.log`.

At minimum, write lines like:

```text
jobapply: preparing tailoring inputs
jobapply: launching Claude Code
jobapply: Claude Code process started
jobapply: Claude Code process exited with code <code>
jobapply: validating output files
jobapply: output contract satisfied
jobapply: missing expected output file: output/tailored_resume.docx
jobapply: marking run failed
```

If multiple output files are missing, write each missing file or one clear comma-separated line.

These lines should appear even if Claude Code itself emits no useful stdout.

Do not fake progress like "writing DOCX" unless the worker actually knows that step happened.

## Required Frontend Behavior

Add API client support:

```ts
getRunLog(runId): Promise<RunLog>
```

While a run is active, completed-but-loading, or failed, JobDetailPage and RunDetailPage should poll the log endpoint.

Display a progress panel with:

```text
Tailoring in progress
Claude is working on your draft.

Recent activity:
- preparing tailoring inputs
- launching Claude Code
- validating output files
```

Behavior:

- Show newest useful lines.
- Keep the default UI compact: last 5 to 8 non-empty lines.
- If no log lines exist yet, show:

```text
Waiting for the tailoring agent to start...
```

- Do not show huge raw stack traces in the default UI.
- Keep full/raw log details, if shown at all, under Advanced details.
- Stop polling when the run reaches a terminal state: `imported` or `failed`.
- Continue showing final recent activity after completion or failure.

## Useful Line Filtering

Implement a small helper if needed.

Default UI may:

- remove blank lines
- strip ANSI color/control characters
- collapse repeated adjacent lines
- show the last N non-empty lines

Do not overbuild semantic parsing in this task.

## RunDetailPage Requirements

RunDetailPage should show:

```text
Tailoring progress
Current status
Recent activity
Useful error message if failed
Advanced details
```

For a failed run with missing outputs, the page should make the situation clear:

```text
Tailoring failed

The tailoring process finished without producing the required output files.

Recent activity:
- Claude Code process exited with code 0
- validating output files
- missing expected output file: output/tailored_resume.docx
- marking run failed
```

Raw run id, run directory, hashes, backend status enum, and full technical log should remain in Advanced details.

## JobDetailPage Requirements

In the "Generate draft" step, show recent activity for the current run.

When the user clicks Generate draft, the UI should quickly transition from:

```text
Ready to generate
```

to:

```text
Tailoring in progress
```

and then show recent activity lines as they appear.

If the run fails, show the friendly failure state and recent activity.

Do not show only a spinner.

## Acceptance Criteria

- While a draft is generating, the user sees recent activity lines instead of only a spinner.
- RunDetailPage shows recent run activity.
- JobDetailPage Generate Draft step shows recent run activity.
- Missing `run.log` is handled gracefully.
- Large logs are truncated.
- Backend does not expose arbitrary files.
- Worker writes useful `jobapply:` progress milestones into `run.log`.
- Failed missing-output runs show the validation/missing-file lines in recent activity.
- Frontend tests pass.
- Backend tests pass.
- Frontend build passes.

## Verification

Run:

```bash
pytest backend/tests
cd frontend && npm test
cd frontend && npm run build
```

Manual verification:

1. Open a job.
2. Click Generate draft.
3. Confirm progress panel appears immediately.
4. Confirm recent activity updates while the run is active.
5. Confirm the UI does not only show a spinner or generic "Generating..." message.
6. Confirm a failed run shows final recent activity and the missing-output explanation.
7. Confirm Advanced details still contains raw technical details if present.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Show live tailoring progress log
```

Do not push.
