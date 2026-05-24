# Task 035: Tailoring progress polling and friendly errors

Task ID: `035-frontend-tailoring-progress`

## Goal

Make tailoring progress understandable by polling runs, auto-importing completed runs, and
replacing raw import errors with useful messages.

## Background

`RunDetailPage` does not poll, so users have to refresh to see whether tailoring finished.
It also exposes raw verbs (`Invoke`, `Import outputs`) and renders import failures as raw
`Request to /runs/... failed with status 400` strings. See the UX spec
([`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md)),
"Tailoring progress behavior" and "Error-message principles".

Read before starting:

```text
docs/product/frontend_cockpit_ux.md
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/JobDetailPage.tsx          (now stepper, after task 034)
frontend/src/lib/workflow.ts                  (after task 033)
frontend/src/lib/api-errors.ts                (after task 033)
frontend/src/api/index.ts
```

Depends on task 034 (the stepper exists) and transitively on task 033.

## Scope

Add polling on `RunDetailPage` and inside step 3 of `JobDetailPage`, wire automatic import
on `completed`, hide operator verbs by default, and route import errors through
`extractApiDetail`.

### Allowed files

```text
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/JobDetailPage.tsx
frontend/src/styles.css
frontend/src/test/runDetailPage.test.tsx
frontend/src/test/runDetailPolling.test.tsx
frontend/src/test/jobDetailWorkspace.test.tsx
agent_tasks/035-frontend-tailoring-progress.md
agent_tasks/queue.yaml
```

### Forbidden files

```text
backend/**
extension/**
runtime_prompts/**
candidate_context/**
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
docs/**
```

### Out of scope

- Renaming `Version N` → `Draft N` on ResumeVersionDetailPage (see task 036).
- Application submit wording (see task 037).
- Settings cards (see task 038).
- Any backend change to run/import endpoints.

## Required behavior

- Poll `getRun(runId)` every 5 seconds while the run is active (`runIsActive`) or needs
  import (`runNeedsImport`). Stop polling on terminal states (`imported`, `failed`).
- On a state transition into `completed` (from a non-`completed` previous status), call
  `importRun(runId)` exactly once automatically.
- If `importRun` fails, render `extractApiDetail(err)` to the user. Never render the raw
  request path or status code in default UI.
- Hide `Invoke` and `Import outputs` from default `RunDetailPage`. Move the operator
  controls into the existing `Advanced details` disclosure, renamed:
  - `Invoke` → `Start tailoring`
  - `Import outputs` → `Retry import`
- Display run status using `runStatusLabel` from `workflow.ts`. Do not inline status
  strings.
- The same polling/auto-import behavior must apply when the user is on `JobDetailPage`
  watching an in-flight run from step 3 — i.e. step 3 must reflect the new status without
  a manual refresh. Reuse the same polling helper if possible; do not duplicate logic.
- Update tests:
  - `runDetailPage.test.tsx`: verify operator verbs are not in default UI; verify advanced
    block contains the renamed controls; verify error rendering uses parsed detail.
  - `runDetailPolling.test.tsx` (new): use fake timers (or vitest equivalent) to verify
    polling interval, that polling stops on `imported`/`failed`, and that auto-import is
    called exactly once on transition to `completed`.
  - `jobDetailWorkspace.test.tsx`: verify step 3 updates from `Tailoring in progress` to
    `Draft ready to review` after the poller observes `completed → imported`.

## Acceptance criteria

- No raw `Invoke` or `Import outputs` strings remain in default UI on `RunDetailPage`.
- No raw `Request to /... failed with status N` strings can reach the user from
  `importRun` failures.
- Polling stops on terminal states and on unmount; no setInterval leaks in tests.
- A `completed` run results in exactly one automatic `importRun` call.
- All frontend tests pass.

## Verification

```bash
cd frontend && npm test
cd frontend && npm run build
```

## Git instructions

After verification passes:

1. Stage only the allowed files.
2. Commit locally with message:

   ```text
   Poll runs and parse import errors
   ```

Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.
