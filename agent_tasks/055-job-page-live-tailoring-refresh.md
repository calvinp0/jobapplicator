# Task 055: Make Job Page Tailoring Refresh Live

## Goal

Make the Job Detail page update live while a tailored resume is being generated.

Current behavior is still too static:

```text
User clicks Generate draft
→ run starts
→ Job page may show an initial status
→ user has to refresh or click into the run page to see real progress / new draft
```

The Job page should behave like a live workspace:

```text
Generate draft
→ immediately show tailoring progress
→ poll run status and progress events
→ show recent activity
→ stop auto-import retry spam
→ when import succeeds, refresh resume drafts automatically
→ when import fails, show a clear error and Retry loading draft
```

Do not implement Gmail.
Do not implement LinkedIn automation.
Do not change backend output-generation behavior in this task.

## Background

Inspect:

```text
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/styles.css
frontend/src/test/**
backend/app/routers/runs.py
docs/contracts/claude_run_directory.md
```

Related prior tasks:

```text
048-tailoring-progress-and-import-failure-ux
049-enforce-tailoring-output-contract
050-tailoring-live-progress-log
051-fix-claude-runtime-write-permissions
052-tailoring-progress-events
```

## Current Problems

### 1. Job page does not feel live

The user wants to see progress inside the `Generate a draft` section without refreshing.

The page should poll active runs and progress events while tailoring is active.

### 2. New drafts may not appear automatically

When a run imports successfully into a new resume draft, the Job page should refresh the resume versions list automatically and show the new draft.

### 3. Elapsed time can be wrong

A newly started run can show a bogus elapsed time like:

```text
3h 0m elapsed
```

This should instead show:

```text
just now
12s elapsed
1m 04s elapsed
```

Use timestamp parsing consistently and avoid timezone mistakes.

### 4. Import retry behavior must stay controlled

If a completed run fails to import, the page should not repeatedly POST `/runs/{id}/import`.

It should show a clear error and a manual retry button.

## Scope

Update:

```text
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/styles.css
frontend/src/test/**
```

Do not edit backend unless strictly necessary to consume existing progress/log endpoints.

## Required Behavior

### 1. Live polling on JobDetailPage

When the Job page has a current run that is:

```text
created
running
completed but not imported
```

the page should poll the relevant endpoints every few seconds.

Suggested polling targets:

```text
GET /runs/{run_id}
GET /runs/{run_id}/progress
GET /resume-versions
```

If `/runs/{run_id}/progress` does not exist in the current implementation but `/runs/{run_id}/log` does, use the existing endpoint.

Polling should stop when the run is:

```text
imported
failed
```

unless the user manually starts another draft.

### 2. Show progress events in the Generate Draft step

In the `Generate a draft` step, show a visible progress panel while the run is active or completed-but-loading.

Default UI should show user-facing progress events, for example:

```text
Tailoring in progress
Recent activity
• Reading job description
• Reviewing master resume
• Drafting tailored resume markdown
```

If no progress lines exist yet, show:

```text
Waiting for the tailoring agent to start...
```

Do not show only a spinner.

Technical command/cwd/permission lines should not dominate the default UI if user-facing progress lines exist.

### 3. Refresh drafts after successful import

When auto-import succeeds:

```text
- refresh resume versions
- show the new draft in the Resume drafts step
- update the job stage/status
- stop polling that run
```

The user should not have to refresh to see Draft 2, Draft 3, etc.

### 4. Manual retry after import failure

If import fails:

```text
- show parsed backend detail using extractApiDetail
- stop automatic import attempts for that run
- show Retry loading draft
```

Clicking `Retry loading draft` may call `importRun(runId)` again once.

After retry succeeds, refresh drafts.

After retry fails, keep the friendly error visible.

### 5. Fix elapsed-time display

Add or fix a helper for elapsed time display.

Requirements:

```text
- newly created/started runs should not show 3h elapsed immediately
- use started_at if present, otherwise created_at
- parse timestamps consistently
- display compact human time
```

Examples:

```text
just now
12s elapsed
1m 04s elapsed
5m elapsed
```

If timestamp is missing or invalid, show:

```text
elapsed time unavailable
```

### 6. Avoid duplicate import attempts

Track import attempts per run ID in component state or a ref.

Automatic import should happen at most once per run completion transition.

Manual retry should be explicit.

## Acceptance Criteria

- JobDetailPage updates run status without browser refresh.
- JobDetailPage shows progress events during tailoring.
- JobDetailPage refreshes resume drafts after import succeeds.
- New Draft N appears automatically after successful import.
- Import failure does not spam repeated `/import` calls.
- Import failure displays friendly parsed detail and a retry button.
- Elapsed time does not show bogus multi-hour values for new runs.
- RunDetailPage still works with the same progress/error behavior.
- Frontend tests pass.
- Frontend build passes.

## Verification

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Manual verification:

1. Start backend and frontend.
2. Open a job page.
3. Click Generate draft.
4. Confirm the Generate Draft section updates without refresh.
5. Confirm progress lines appear and change over time.
6. Confirm elapsed time starts near zero.
7. Confirm successful import shows a new draft automatically.
8. Force or observe an import failure.
9. Confirm only one automatic import attempt occurs.
10. Confirm Retry loading draft is manual.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Make job page tailoring refresh live
```

Do not push.
