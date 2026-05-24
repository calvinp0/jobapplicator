# Task 036: Resume draft review and approval language

Task ID: `036-frontend-resume-draft-review`

## Goal

Make resume version pages and application references use draft/review language instead of
backend version language.

## Background

`ResumeVersionDetailPage` currently calls generated resumes `Version N`, uses backend status
strings (`pending`, `approved`), and renders approve/open-file errors raw. The UX spec
requires `Draft N`, `Awaiting review` / `Approved`, and friendly errors. See
[`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md), "Resume
draft/review/approval behavior".

Read before starting:

```text
docs/product/frontend_cockpit_ux.md
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/lib/workflow.ts                  (after task 033)
frontend/src/lib/api-errors.ts                (after task 033)
frontend/src/api/index.ts
```

Depends on task 034 (workspace stepper exists so step 4 can route to this page with
draft language consistently).

## Scope

Rename "Version" to "Draft" in user-facing surfaces on `ResumeVersionDetailPage` and on
references in `ApplicationDetailPage`. Move approve/open-file error rendering to
`extractApiDetail`. Do not change backend types or endpoints.

### Allowed files

```text
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/styles.css
frontend/src/test/resumeVersionDetailPage.test.tsx
frontend/src/test/applicationDetailPage.test.tsx
agent_tasks/036-frontend-resume-draft-review.md
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
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/api/types.ts
docs/**
```

### Out of scope

- Application submit verb changes (`Mark Submitted` → `I've sent it`) — see task 037.
- ApplicationsPage list copy — see task 037.
- Settings cards — see task 038.
- Revision feedback flow — see task 039.
- Renaming backend fields or API types.

## Required behavior

- Replace every user-facing `Version N` reference with `Draft N` via `draftLabel`. This
  includes:
  - `ResumeVersionDetailPage` heading: `Draft N for <job title> — <company>`.
  - `ApplicationDetailPage`'s reference to the linked resume version.
- Use `draftStatusLabel` to render `Awaiting review` for pending and `Approved` for
  approved.
- The approve button becomes `Approve draft`.
- Once approved, replace the active approve button with a read-only `Approved ✓`
  indicator. The button must not remain clickable after approval.
- Route approve and open-file error rendering through `extractApiDetail`. No raw
  `Request to /...` strings may reach the user.
- Update tests:
  - `resumeVersionDetailPage.test.tsx`: heading uses `Draft N`, approve button text,
    transition to `Approved ✓`, parsed error messages.
  - `applicationDetailPage.test.tsx`: references to the resume version use `Draft N`.

## Acceptance criteria

- No `Version N` (where N is a number) appears in any user-facing string on these pages.
- `Approve draft` is present pre-approval and absent post-approval; `Approved ✓` appears
  post-approval.
- All approve/open-file errors render parsed detail strings.
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
   Rename resume versions to drafts in review UI
   ```

Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.
