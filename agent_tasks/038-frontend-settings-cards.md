# Task 038: Settings page as cards

Task ID: `038-frontend-settings-cards`

## Goal

Redesign `SettingsPage` so master resumes and evidence banks appear as cards with collapsed
add forms.

## Background

`SettingsPage` is currently a flat admin form: forms render alongside lists, there is no
clear separation between resume management and evidence bank management, and there is no
useful empty state. The UX spec
([`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md)) makes
both groups distinct cards with collapsed add forms.

Read before starting:

```text
docs/product/frontend_cockpit_ux.md
frontend/src/pages/SettingsPage.tsx           (already uses extractApiDetail after task 033)
frontend/src/lib/api-errors.ts                (after task 033)
frontend/src/api/index.ts
frontend/src/styles.css
```

Depends on task 033 (`extractApiDetail` is in use on this page).

## Scope

Layout/UX changes only. Do not change API or types. Tests must cover the collapse/expand
and submit-collapses-and-updates flows.

### Allowed files

```text
frontend/src/pages/SettingsPage.tsx
frontend/src/styles.css
frontend/src/test/settingsPage.test.tsx
agent_tasks/038-frontend-settings-cards.md
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
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/lib/workflow.ts
frontend/src/lib/api-errors.ts
frontend/src/api/index.ts
frontend/src/api/types.ts
docs/**
```

### Out of scope

- Backend changes to master resume / evidence bank endpoints.
- Card design language across other pages (this task only touches Settings).

## Required behavior

- Render master resumes and evidence banks as two visually distinct cards on the page.
- Existing entries appear as list rows inside the appropriate card.
- Each card's add form is **hidden by default**.
- Each card has a clear button:
  - `+ Add master resume`
  - `+ Add evidence bank`
- Clicking the button reveals the form. Clicking `Cancel` collapses it.
- On a successful submit the form collapses and the entry list updates.
- Empty-state copy is exact:
  - Master resumes empty: `No master resumes yet — add one to enable tailoring.`
  - Evidence banks empty: `No evidence banks yet — optional, but useful for grounded tailoring.`
- Error rendering continues to use `extractApiDetail`.
- Add `.settings-card`, `.settings-card-header`, and any related styles needed; keep
  styling minimal.
- Update `settingsPage.test.tsx` to cover:
  - The two cards render with their headers.
  - Add forms are hidden by default.
  - Clicking `+ Add master resume` / `+ Add evidence bank` reveals the appropriate form.
  - `Cancel` collapses the form.
  - A successful submit collapses the form and the new row appears.
  - Empty-state strings render exactly as specified.

## Acceptance criteria

- Both cards exist with the canonical headers and add buttons.
- Add forms are not in the DOM by default (or are clearly hidden) until reveal.
- Empty-state strings match the spec exactly.
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
   Redesign Settings as cards with collapsed forms
   ```

Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.
