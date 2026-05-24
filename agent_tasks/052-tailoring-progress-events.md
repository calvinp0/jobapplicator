# Task 052: Add Tailoring Progress Events

## Goal

Make tailored-resume generation show meaningful user-facing progress events while Claude Code is running.

Task 050 exposed run logs in the frontend, but the current log only shows backend process milestones:

```text
preparing tailoring inputs
launching Claude Code
Claude Code process started
```

After that, the UI goes quiet because Claude Code may not emit useful stdout/stderr while it works.

The user should see one-line progress updates like:

```text
Reading the job description
Comparing the job against your master resume
Selecting relevant evidence
Drafting tailored resume bullets
Checking claims against evidence bank
Writing tailored_resume.md
Creating tailored_resume.docx
Writing claim audit
Finalizing output files
```

Do not implement Gmail.
Do not implement LinkedIn automation.
Do not change the core resume-tailoring evidence policy.

## Background

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/routers/runs.py
backend/app/schemas.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
runtime_prompts/resume_tailoring.md
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/styles.css
frontend/src/test/**
docs/contracts/claude_run_directory.md
```

## Current Problem

The UI currently shows recent activity, but the activity is mostly technical process state:

```text
preparing tailoring inputs
launching Claude Code
permission mode=acceptEdits
output directory=...
Claude Code process started
```

This confirms the process started, but it does not tell the user what is happening during tailoring.

## Required Behavior

### 1. Add a progress event file

Add a user-facing progress log file to each run directory.

Preferred path:

```text
progress/progress.log
```

Alternative acceptable path:

```text
run_progress.log
```

Document the chosen path in:

```text
docs/contracts/claude_run_directory.md
```

The file should contain one user-facing event per line.

Example:

```text
Reading job description
Comparing job requirements against master resume
Selecting evidence from evidence bank
Drafting tailored resume
Writing tailored_resume.md
Creating tailored_resume.docx
Writing change log
Writing claim audit
Validating output files
```

### 2. Update the runtime prompt

Update:

```text
runtime_prompts/resume_tailoring.md
```

so Claude is instructed to append progress events while working.

The prompt should say:

```text
As you work, append short user-facing progress lines to progress/progress.log.
Each line should describe the current phase in plain language.
Do not include secrets, raw prompts, hashes, or internal file paths.
Keep each progress line under 120 characters.
```

Required progress phases:

```text
Reading job description
Reviewing master resume
Reviewing evidence bank
Planning tailored resume changes
Drafting tailored resume markdown
Creating DOCX
Writing change log
Writing claim audit
Validating required outputs
```

Do not let progress updates replace the required output files.

### 3. Worker fallback heartbeat

Update the worker so that even if Claude emits no progress events, the run still gets periodic heartbeat lines.

Example:

```text
Claude Code is running — 15 seconds elapsed
Claude Code is running — 30 seconds elapsed
Claude Code is running — 45 seconds elapsed
```

This heartbeat should stop when Claude exits.

Do not spam too aggressively. A 10–15 second interval is enough.

### 4. Progress endpoint

Update the existing run log endpoint or add a new endpoint.

Preferred:

```http
GET /runs/{run_id}/progress
```

Response shape:

```json
{
  "run_id": "...",
  "lines": [
    "Reading job description",
    "Reviewing master resume",
    "Drafting tailored resume markdown"
  ],
  "truncated": false
}
```

If adding a new endpoint is too much, extend the existing `/runs/{run_id}/log` response with:

```json
{
  "progress_lines": [...]
}
```

### 5. Frontend display

Update `JobDetailPage` and `RunDetailPage` so the progress panel prefers user-facing progress events.

Default UI should show:

```text
Recent activity
• Reading job description
• Reviewing master resume
• Drafting tailored resume markdown
```

Do not show technical lines like these in the default progress panel unless no user-facing progress exists:

```text
permission mode=acceptEdits
output directory=/...
cwd=/...
```

Technical lines can remain under Advanced details.

### 6. Failure state

If tailoring fails, keep showing the final progress events above the error.

Example:

```text
Tailoring failed

Recent activity
• Reading job description
• Reviewing master resume
• Drafting tailored resume markdown
• Validating required outputs

Error
Missing required output files: tailored_resume.docx
```

## Acceptance Criteria

- While tailoring runs, the UI shows user-facing progress lines, not only a spinner.
- Progress lines continue to update while Claude is running.
- If Claude emits no progress, worker heartbeat prevents the UI from appearing frozen.
- Technical process details are hidden from default UI when user-facing progress exists.
- Failed runs show final progress lines plus a useful error message.
- Required output files are still validated by task 049 behavior.
- Backend tests pass.
- Frontend tests pass.
- Frontend build passes.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py backend/tests/test_run_directory.py
pytest backend/tests
cd frontend && npm test
cd frontend && npm run build
```

Manual verification:

1. Start backend and frontend.
2. Open a job.
3. Click Generate draft.
4. Confirm progress changes over time.
5. Confirm the panel does not only show `Claude Code process started`.
6. Confirm technical command/cwd/permission lines are not the main default UI.
7. Confirm failed runs still show final progress and the error.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add tailoring progress events
```

Do not push.
