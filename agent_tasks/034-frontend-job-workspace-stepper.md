# Task 034: Job workspace as a five-step stepper

Task ID: `034-frontend-job-workspace-stepper`

## Goal

Redesign `JobDetailPage` into a guided five-step job workspace.

## Background

`JobDetailPage` currently renders a flat stack of H3 sections ("Tailored resumes",
"In-flight runs", "Submit this job", "Tailor a new resume"). There is no sense of order or
workflow. The page also uses an invented run status (`completed-not-imported`) and a job
description disclosure that does not look clickable. See the UX spec
([`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md)) for the
canonical five-step model.

Read before starting:

```text
docs/product/frontend_cockpit_ux.md
frontend/src/pages/JobDetailPage.tsx
frontend/src/lib/workflow.ts            (added by task 033)
frontend/src/lib/api-errors.ts          (added by task 033)
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/styles.css
```

Depends on task 033 being merged so `workflow.ts` and `api-errors.ts` are available.

## Scope

Restructure `JobDetailPage` into five workflow step cards, fix the job description
disclosure, and replace the in-flight run logic with shared helpers. Polling, auto-import,
RunDetailPage and ResumeVersionDetailPage changes are explicitly out of scope and belong to
later tasks.

### Allowed files

```text
frontend/src/pages/JobDetailPage.tsx
frontend/src/styles.css
frontend/src/test/jobDetailApply.test.tsx
frontend/src/test/jobDetailResumeVersions.test.tsx
frontend/src/test/generateResume.test.tsx
frontend/src/test/jobDetailWorkspace.test.tsx
agent_tasks/034-frontend-job-workspace-stepper.md
agent_tasks/queue.yaml
```

### Forbidden files

```text
backend/**
extension/**
runtime_prompts/**
candidate_context/**
frontend/src/pages/RunDetailPage.tsx
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

- Polling and auto-import in step 3 / RunDetailPage (see task 035).
- Draft language and approve UI on ResumeVersionDetailPage (see task 036).
- ApplicationDetailPage / ApplicationsPage wording (see task 037).
- SettingsPage card layout (see task 038).
- Any backend or extension change.

## Required behavior

- Replace the flat H3 sections with five workflow step cards, in this order:
  1. `Read the job description`
  2. `Choose resume source`
  3. `Generate a draft`
  4. `Review and approve drafts`
  5. `Send your application`
- Step 1: the job description toggle must be a clearly clickable button/section toggle
  (not a bare disclosure that looks like a text field). The body of step 1 must expand
  on click.
- Step 2: shows current master resume and evidence bank selectors; provides a link to
  Settings if there are none. (Selector logic may already exist — keep it; just move it
  into step 2 with workflow framing.)
- Step 3:
  - One primary action `Generate draft` (or `Generate another draft` when prior runs
    exist). Clicking it must create a run and invoke it client-side as one user action.
  - Display the most recent run's status using `runStatusLabel`, including the derived
    "needs import" case via `runIsActive(status) || runNeedsImport(run, versions)`. Do not
    inline a `completed-not-imported` literal anywhere.
- Step 4: list resume drafts using `draftLabel` and `draftStatusLabel`. Each row links to
  the existing `ResumeVersionDetailPage`. (Renaming inside that page is task 036's job.)
- Step 5:
  - Fold the existing "Submit this job" / application-creation flow into this card.
  - Gate the start action on having an approved draft, using workflow-language copy from
    the spec.
- Use `workflow.ts` helpers exclusively for status and draft labels; do not inline label
  strings.
- Add `.workspace-step`, `.workspace-step-header`, `.workspace-step-body`, and any related
  styles needed in `frontend/src/styles.css` to make the step cards visually distinct from
  each other. Keep styling minimal — no component library.
- Update existing tests (`jobDetailApply.test.tsx`, `jobDetailResumeVersions.test.tsx`,
  `generateResume.test.tsx`) for the new structure and labels. Add
  `jobDetailWorkspace.test.tsx` covering:
  - All five step headings render in order.
  - The description toggle is reachable as a button.
  - `Generate draft` triggers both create and invoke in a single user action.
  - `completed`-status runs with no matching ResumeVersion render the "needs import"
    state via the helper.

## Acceptance criteria

- `JobDetailPage` renders five step cards in the required order with the canonical
  headings.
- No `completed-not-imported` literal exists in `JobDetailPage`.
- No backend-leaking labels (e.g. `Tailored resumes`, `Tailor a new resume`, `Submit this
  job`, `Version N`, `Invoke`, `Import outputs`) appear in the page's default UI.
- Generating a draft is a single click that produces an active run.
- Existing routes still work; existing core tests still pass.
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
   Redesign JobDetailPage as five-step workspace
   ```

Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.
