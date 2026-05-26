# Task 103: Redesign Frontend Design System and App Shell

## Goal

Redesign the JobApplicator frontend so it feels like a coherent, polished product instead of a collection of feature cards.

The current UI feels visually inconsistent and under-designed. Pages such as Applications, Settings, Gmail tracking, Captures, Runs, and Job Detail have accumulated features without a strong design system.

This task should introduce a proper app shell, theme, reusable components, spacing system, typography, and a cleaner dashboard-oriented layout.

Do not change backend behavior unless a small API shape fix is required.  
Do not change Gmail backend behavior.  
Do not change Claude tailoring behavior.  
Do not change database behavior.  
Do not implement LinkedIn automation.

## Background

The current UI has several issues:

```text
- Pages feel visually flat and inconsistent.
- Buttons and controls do not share a clear hierarchy.
- Gmail sync/actions feel bolted on.
- Applications page feels too card-heavy and not dashboard-like.
- Settings has many technical controls but weak grouping.
- Statuses are hard to scan.
- Feature density is increasing without a product-level layout.
```

The goal is to make JobApplicator feel like a serious local cockpit for:

```text
job discovery
resume tailoring
application tracking
Gmail evidence
prompt/harness management
candidate context
```

## Design Direction

Use a clean, dense, professional dashboard aesthetic.

Suggested style:

```text
Modern developer/productivity cockpit
Light background
Subtle borders
Compact cards
Strong table layouts
Clear status badges
Consistent toolbar actions
Less visual noise
Better hierarchy
```

Avoid:

```text
oversized cards everywhere
raw/default buttons
large empty whitespace
inconsistent badges
floating action buttons with no context
unstructured vertical stacks
```

## Required App Shell

Implement or improve a consistent app shell.

The shell should include:

```text
left sidebar or top navigation
page title area
page description
primary page actions
secondary toolbar area
main content area
consistent max-width / full-width behavior
```

Navigation should group areas logically:

```text
Dashboard
Jobs
Applications
Runs
Captures
Candidate Context
Prompts
Settings
```

If some pages do not exist yet, do not add dead links unless the project already has routes.

## Theme Requirements

Create or consolidate a design theme.

Define consistent values for:

```text
background colors
surface colors
border colors
text colors
muted text
status colors
spacing
border radius
shadow
font sizes
button sizes
table density
```

If Tailwind is used, consolidate theme conventions in existing Tailwind config/classes.

If plain CSS is used, create a central CSS variables file.

Suggested CSS variables:

```css
:root {
  --bg: #f8fafc;
  --surface: #ffffff;
  --surface-muted: #f1f5f9;
  --border: #e2e8f0;
  --text: #0f172a;
  --text-muted: #64748b;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --success: #15803d;
  --warning: #b45309;
  --danger: #b91c1c;
  --info: #0369a1;
}
```

Use actual project styling conventions.

## Reusable Components

Create or refactor reusable components for:

```text
PageShell
PageHeader
Toolbar
Button
IconButton
StatusBadge
MetricCard
DataTable
EmptyState
InlineAlert
SectionCard
FormField
SelectField
TextAreaField
Tabs
ActionMenu
LoadingState
```

Only add components that are actually used in this task.

Do not over-engineer a full component library if the project is small.

## Page Redesign Scope

Redesign the following high-impact pages:

```text
Applications
Settings
Job Detail / Generate Draft area
Runs or Run Detail
Captures, if existing
```

If this is too large, prioritize:

```text
1. Applications
2. Settings
3. Job Detail
```

## Applications Page Requirements

The Applications page should become a table/dashboard.

Toolbar:

```text
Applications                                      [Sync Gmail] [New/Import if applicable]
Track drafts, submissions, email evidence, and outcomes.
```

Include filters:

```text
All
Drafts
Ready
Submitted
Needs review
Interviews
Rejected
```

Table columns:

```text
Job
Company
Status
Submission
Email
Latest run
Updated
Next action
Actions
```

Gmail sync should be integrated in the toolbar, not floating awkwardly.

Rows should be compact and scannable.

Use badges for:

```text
Draft
Ready
Submitted
Pending
Waiting email
Needs review
Interview
Approved
Rejected
Error
```

Email states should be compact:

```text
Not connected
Not checked
No match
Possible match
Needs review
Confirmation
Rejection
Interview
Assessment
Offer
```

## Settings Page Requirements

Settings should be grouped into sections:

```text
General
Gmail integration
Claude / LLM providers
Document tooling
Browser extension
Prompt harnesses
Danger zone
```

Gmail config should feel like an integration card:

```text
Gmail integration
Read-only application tracking
Status: connected / not connected / not configured
Actions: Connect, Test, Save config
```

Database reset should eventually live in a Danger Zone style section if exposed in UI.

## Job Detail Page Requirements

The Job Detail page should clearly separate:

```text
Job description
Primary resume
Evidence sources
Tailoring method
Generate actions
Runs/drafts
```

The evidence selector should look intentional, especially after multiple evidence sources are added.

Suggested layout:

```text
left: job details
right: tailoring setup panel
bottom: runs/drafts table
```

or responsive equivalent.

## Runs / Run Detail Requirements

Run detail should show:

```text
status timeline
input context
artifacts
logs
prompt snapshot
ATS audit
claim audit
change log
download final resume
```

Use tabs:

```text
Overview
Artifacts
Logs
Prompt
Audits
```

If full run detail redesign is too large, add structure but avoid breaking current behavior.

## Visual Quality Requirements

The final UI should have:

```text
consistent button hierarchy
primary/secondary/ghost/destructive buttons
consistent badge styling
consistent card padding
consistent table styling
clear empty states
clear loading states
clear error states
no raw browser-default buttons
no unstyled controls
no visually orphaned actions
```

## Accessibility Requirements

Preserve or improve:

```text
keyboard navigation
visible focus states
labelled form fields
button text clarity
non-color-only status indicators
reasonable contrast
```

Do not rely only on color for status.

## Frontend Architecture Requirements

Do not scatter styling randomly across pages.

Prefer:

```text
frontend/src/components/ui/
frontend/src/components/layout/
frontend/src/styles/
```

or the existing project convention.

Avoid duplicating status badge logic across pages.

Create central mappings for:

```text
application statuses
email statuses
run statuses
submission statuses
```

## Tests

Add/update frontend tests if infrastructure exists.

Tests should prove:

1. App shell renders navigation.
2. Applications page renders table/dashboard layout.
3. Applications toolbar contains Sync Gmail.
4. Applications page renders status badges.
5. Applications page renders email status.
6. Applications page renders next action.
7. Settings page groups Gmail integration clearly.
8. Job Detail page still supports generate draft.
9. Existing critical workflows still render.
10. Build passes.

Backend tests are not required unless API shape changes.

## Acceptance Criteria

- Frontend has a coherent app shell.
- Design tokens or centralized styling exist.
- Reusable UI components exist for common patterns.
- Applications page is table/dashboard-style.
- Gmail Sync is visually integrated into Applications toolbar.
- Settings page is grouped and polished.
- Job Detail page is clearer and less cluttered.
- Existing workflows still work.
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

If API shape changed:

```bash
pytest
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Open Dashboard/Applications.
4. Confirm UI feels like one cohesive product.
5. Confirm Applications are table-style and scannable.
6. Confirm Sync Gmail is in the toolbar and styled consistently.
7. Open Settings.
8. Confirm Gmail/settings sections are grouped and polished.
9. Open a Job Detail page.
10. Confirm tailoring setup is clear.
11. Generate a draft.
12. Confirm no existing core workflow broke.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Redesign frontend design system and app shell
```

Do not push.
