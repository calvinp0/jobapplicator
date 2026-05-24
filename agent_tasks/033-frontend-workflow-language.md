# Task 033: Frontend workflow language helpers

Task ID: `033-frontend-workflow-language`

## Goal

Create shared frontend workflow language/status helpers so UI pages stop inlining
inconsistent backend-facing labels.

## Background

The current frontend duplicates status-to-label mappings and error-parsing logic across
pages, and it sometimes uses an invented status string (`completed-not-imported`) that the
backend never writes. The UX spec
([`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md)) makes the
mapping canonical and requires a single shared module.

Read before starting:

```text
docs/product/frontend_cockpit_ux.md
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/api/index.ts
frontend/src/api/types.ts
```

## Scope

Create the shared workflow and error helpers, route `DashboardPage` and `SettingsPage` to
use them, and add unit tests. This is a refactor + label change only; do not redesign any
page in this task. Downstream cockpit changes (job workspace stepper, tailoring polling,
draft review, settings cards) live in tasks 034–038 and depend on this one.

### Allowed files

```text
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/test/workflow.test.ts
frontend/src/test/apiErrors.test.ts
frontend/src/test/dashboardPage.test.tsx
frontend/src/test/settingsPage.test.tsx
agent_tasks/033-frontend-workflow-language.md
agent_tasks/queue.yaml
```

### Forbidden files

```text
backend/**
extension/**
runtime_prompts/**
candidate_context/**
docs/** (other than this task's references — do not modify the spec)
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/RunsPage.tsx
frontend/src/pages/JobsPage.tsx
```

### Out of scope

- Redesigning JobDetailPage as a stepper (see task 034).
- Polling, auto-import, or RunDetailPage changes (see task 035).
- Resume version draft language on ResumeVersionDetailPage (see task 036).
- Application submission wording (see task 037).
- Settings cards/collapsed forms layout (see task 038).
- Any backend or extension change.
- Visual restyling beyond the label swap on DashboardPage.

## Required behavior

- Create `frontend/src/lib/workflow.ts` exporting:
  - `runStatusLabel(status)` mapping per the spec:
    `created → Queued`, `running → Tailoring in progress`, `completed → Draft ready to
    review`, `imported → Draft imported`, `failed → Tailoring failed`.
  - `runIsActive(status)` — true for `created` or `running`.
  - `runIsComplete(status)` — true for `completed` or `imported`.
  - `runNeedsImport(run, versions)` — true when `run.status === "completed"` and no
    `ResumeVersion` in `versions` references that run.
  - `draftLabel(versionIndex)` — returns `Draft N` (1-based).
  - `draftStatusLabel(approval)` — `Awaiting review` for pending, `Approved` for approved.
  - `jobStageLabel(stage)` — workflow stage label used on the dashboard.
  - `computeJobStage(job, runs, versions, application)` — returns the workflow stage a job
    is currently in (suggested values: `captured`, `tailoring`, `draft_ready`, `approved`,
    `sent`). Pick a small, finite set and document it in JSDoc.
- Create `frontend/src/lib/api-errors.ts` exporting `extractApiDetail(err: unknown): string`.
  It must:
  - If `err` has a JSON `detail` field on its response, return that string.
  - Otherwise return a short friendly fallback (no `Request to /... failed with status N`
    strings).
- Move the dashboard's existing stage/status logic into `workflow.ts` and call it from
  `DashboardPage`.
- Replace labels on `DashboardPage`:
  - `Resumes ready` → `Drafts approved`
  - `Ready to apply` → `Approved — ready to send`
- Refactor `SettingsPage` to call `extractApiDetail` everywhere it currently parses errors
  locally. Do not change its layout in this task.
- Add unit tests:
  - `frontend/src/test/workflow.test.ts` covering every exported helper, including the
    `runNeedsImport` derivation.
  - `frontend/src/test/apiErrors.test.ts` covering: response with `detail`, response
    without `detail`, plain `Error`, and unknown value.
- Update `dashboardPage.test.tsx` and `settingsPage.test.tsx` for the new labels and
  error rendering. Do not introduce snapshots of unrelated UI.

## Acceptance criteria

- `frontend/src/lib/workflow.ts` and `frontend/src/lib/api-errors.ts` exist and are the
  only sources of those mappings/helpers.
- `DashboardPage` renders `Drafts approved` and `Approved — ready to send`; the old labels
  do not appear anywhere on it.
- `SettingsPage` does not contain inline error-string parsing.
- No backend status value `completed-not-imported` is introduced or assumed by any new
  code; `runNeedsImport` does the derivation.
- All new and existing frontend tests pass.

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
   Add shared workflow language and error helpers
   ```

Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.
