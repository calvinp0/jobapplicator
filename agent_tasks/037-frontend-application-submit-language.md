# Task 037: Application submit wording

Task ID: `037-frontend-application-submit-language`

## Goal

Polish application submission wording so it matches manual job application behavior.

## Background

`ApplicationDetailPage` and `ApplicationsPage` still use backend-shaped verbs and status
strings (`Mark Submitted`, `submitted`), and gating messages talk about "resume versions"
instead of approved drafts. The UX spec requires workflow-language wording. See
[`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md),
"Application creation/submission behavior".

Read before starting:

```text
docs/product/frontend_cockpit_ux.md
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/lib/workflow.ts                  (after task 033)
frontend/src/lib/api-errors.ts                (after task 033)
```

Depends on task 036 so draft language exists on the application detail page.

## Scope

Wording-only changes on the two application pages, plus updated tests. No layout changes
beyond what the wording requires.

### Allowed files

```text
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/test/applicationDetailPage.test.tsx
frontend/src/test/applicationsPage.test.tsx
agent_tasks/037-frontend-application-submit-language.md
agent_tasks/queue.yaml
```

### Forbidden files

```text
backend/**
extension/**
runtime_prompts/**
candidate_context/**
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/styles.css
docs/**
```

### Out of scope

- Backend status enum changes.
- Layout/redesign work beyond the wording swap.
- Revision feedback flow — see task 039.

## Required behavior

- Replace `Mark Submitted` with `I've sent it`.
- Replace user-facing `submitted` status text with `Sent` (do not change backend values;
  map at the UI layer).
- Ensure draft / in-progress application states have user-facing labels (e.g. `Draft`,
  `In progress`) rather than raw backend enum strings.
- Rewrite gating messages exactly:
  - `Link an approved resume version first` → `Pick an approved draft on the job page first.`
  - `Linked resume version is not yet approved` → `This draft has not been approved yet. Approve it on the job page first.`
- Update tests:
  - `applicationDetailPage.test.tsx`: button text, gating messages, `Sent` status.
  - `applicationsPage.test.tsx`: status column / chip uses `Sent`, not `submitted`.

## Acceptance criteria

- No `Mark Submitted` text remains in default UI on either page.
- Both gating messages match the spec exactly.
- No raw backend status enum strings appear in default UI on either page.
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
   Polish application submit wording
   ```

Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.
