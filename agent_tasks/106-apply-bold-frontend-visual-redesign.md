# Task 106: Apply Bold Frontend Visual Redesign

## Goal

Make the JobApplicator frontend look and feel substantially different from the current UI.

The previous redesign task added components and CSS, but the product still looks largely the same to the user. This task should perform a stronger visual redesign with a clearly different layout, stronger hierarchy, better spacing, better navigation, and more polished dashboard styling.

Do not change backend behavior unless absolutely necessary.  
Do not change Gmail backend behavior.  
Do not change Claude tailoring behavior.  
Do not change database behavior.  
Do not implement LinkedIn automation.

## Background

Task 103 merged changes including:

```text
frontend/src/components/ui/EmptyState.tsx
frontend/src/components/ui/PageHeader.tsx
frontend/src/components/ui/SectionCard.tsx
frontend/src/components/ui/SettingsGroup.tsx
frontend/src/components/ui/StatusBadge.tsx
frontend/src/layout/Layout.tsx
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/styles.css
```

But the result still looks too similar.

The review notes also said:

```text
Job Detail page got only ~17 lines of change.
Captures and Runs pages were not touched.
Several larger reusable components were not extracted.
```

This task should be a visible redesign, not incremental cleanup.

## Design Direction

Adopt a polished “local command center” design.

The UI should feel like:

```text
Linear / Vercel / GitHub Projects / modern admin dashboard
```

Not like:

```text
unstyled forms
stacked plain cards
raw buttons
generic default app layout
```

Target aesthetic:

```text
dense but readable
dashboard-like
clear navigation
strong page headers
subtle surfaces
compact tables
high-quality status badges
consistent toolbars
clear primary actions
```

## Non-Negotiable Visual Requirements

The redesign must be obvious at first glance.

Implement:

```text
1. A redesigned sidebar/nav with stronger visual identity.
2. A dashboard-style top page header.
3. A consistent toolbar pattern.
4. A compact table design for Applications.
5. Redesigned Settings cards.
6. Redesigned Job Detail tailoring workspace.
7. Improved spacing, typography, and status badges across pages.
8. No raw/default-looking buttons or controls.
```

If the page still looks substantially the same, the task is not complete.

## App Shell Requirements

Redesign the app shell.

The shell should include:

```text
- fixed or sticky sidebar
- app name / product mark area
- grouped navigation
- active route highlight
- compact secondary info such as local backend status if available
- consistent content width and padding
```

Suggested nav groups:

```text
Track
  Dashboard
  Jobs
  Applications

Create
  Captures
  Runs
  Candidate Context

Configure
  Prompts
  Settings
```

Use actual existing routes only. Do not add dead links unless route exists.

## Visual Theme Requirements

Update `frontend/src/styles.css` or equivalent so the app has a stronger design language.

Use:

```text
soft app background
white/elevated panels
subtle shadows
clear borders
rounded cards
compact table rows
consistent hover states
consistent focus states
modern button hierarchy
```

Buttons should have variants:

```text
primary
secondary
ghost
danger
```

Status badges should look intentional, not like plain text.

## Applications Page Requirements

The Applications page should be visibly redesigned.

Implement:

```text
- full-width table/dashboard layout
- sticky/clear table header
- top toolbar with Sync Gmail integrated
- filter chips
- compact row actions
- email/status summaries condensed into one or two readable columns
```

The page should not look like the previous card/list layout.

Suggested columns:

```text
Application
Pipeline
Email
Activity
Next action
```

Where:

```text
Application = job title, company, source
Pipeline = status + submission
Email = email status + latest evidence
Activity = updated time + latest run
Next action = primary action + compact menu
```

## Settings Page Requirements

Settings should be redesigned into a proper settings hub.

Use grouped panels:

```text
Gmail integration
Document tooling
Claude / LLM
Browser extension
Prompt harnesses
Danger zone
```

Each panel should have:

```text
title
description
status
actions
```

Gmail integration should not look like a raw form.

## Job Detail Page Requirements

This page must receive a real layout pass.

Redesign it as a workspace:

```text
left/main: job description and captured job info
right/sidebar: tailoring setup
bottom/tabs: runs, drafts, artifacts
```

The tailoring setup should clearly show:

```text
primary resume
evidence sources
tailoring method
ATS/DOCX options if available
generate action
```

This page should not just get small style edits.

## Runs / Run Detail Requirements

If routes exist, improve them enough to match the new shell.

At minimum:

```text
- use PageHeader
- use SectionCard
- use StatusBadge
- improve artifact/log layout
```

If full redesign is too large, leave TODO notes but ensure it does not visually clash.

## Captures Page Requirements

If Captures page exists, give it a basic redesign:

```text
capture list/table
source URL
captured title
status
action to create job/application
```

If too large, at least apply the new page shell/components.

## Component Requirements

Create/reuse components that are actually used:

```text
Button
Toolbar
DataTable
Badge
PageShell
PageHeader
SectionCard
FilterChips
ActionMenu or compact action group
```

Avoid creating unused components.

## Before/After Requirement

Add a short developer note in docs:

```text
docs/frontend_redesign.md
```

Include:

```text
What changed visually
Design principles
Key components
Pages redesigned
Known remaining rough edges
```

## Tests

Update frontend tests if infrastructure exists.

Tests should prove:

1. App shell renders grouped navigation.
2. Active nav item is indicated.
3. Applications page renders redesigned table columns:
   - Application
   - Pipeline
   - Email
   - Activity
   - Next action
4. Applications toolbar contains Sync Gmail.
5. Filter chips render.
6. Settings page renders grouped panels.
7. Job Detail page renders tailoring setup panel.
8. Existing generate draft workflow still renders.
9. Frontend build passes.

## Acceptance Criteria

- The frontend looks substantially different from before.
- Applications page is clearly table/dashboard-based.
- Sync Gmail is visually integrated in the toolbar.
- Settings page looks like a proper settings hub.
- Job Detail has a real workspace layout.
- Buttons, badges, cards, and tables are visually consistent.
- Existing workflows still function.
- Frontend build/tests pass.

## Verification

Run:

```bash
cd frontend
npm run build
```

If frontend tests exist:

```bash
cd frontend
npm test -- --run
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Open Dashboard.
4. Confirm app shell looks redesigned.
5. Open Applications.
6. Confirm it no longer resembles the old card/list page.
7. Confirm Sync Gmail is in a polished toolbar.
8. Open Settings.
9. Confirm settings are grouped into polished panels.
10. Open Job Detail.
11. Confirm tailoring setup is visually distinct and usable.
12. Generate a draft and confirm workflow still works.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Apply bold frontend visual redesign
```

Do not push.
