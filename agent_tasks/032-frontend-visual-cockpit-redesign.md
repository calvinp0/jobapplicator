# Task 032: Frontend Visual Cockpit Redesign

## Goal

Make the frontend feel like a modern, connected job-application cockpit rather than a backend entity browser.

The current UI technically connects jobs, runs, resume versions, and applications, but visually it still looks like plain CRUD lists. This task is a visual and UX pass only.

Do not change backend behavior.
Do not add new product capabilities.
Do not implement Gmail or LinkedIn automation.

## Background

Read:

```text
frontend/src/App.tsx
frontend/src/layout/
frontend/src/pages/
frontend/src/styles.css
frontend/src/api/
docs/product_requirements.md
docs/architecture.md
docs/adr/
```

## Scope

Update:

```text
frontend/src/App.tsx
frontend/src/layout/**
frontend/src/pages/**
frontend/src/styles.css
frontend/src/test/**
```

Do not edit backend, extension, runtime prompts, candidate context, or database code.

## Design Direction

The UI should feel like:

```text
a job application cockpit
```

not:

```text
a database admin panel
```

Default UI language should be user workflow language:

```text
Capture job
Tailor resume
Review resume
Ready to apply
Application submitted
Waiting for response
```

Backend/provenance language should be hidden by default:

```text
capture id
run id
source
content hash
prompt hash
docx path
raw status
```

These details may appear only under:

```text
Advanced details
Provenance
Debug info
```

## Required UX Changes

### 1. Redesign Home as a dashboard

The home page should include:

- A page title like `Application cockpit`
- A short subtitle explaining the current state
- Summary cards for:
  - active jobs
  - resumes ready
  - applications submitted
  - in-flight runs
- A “Next action” section showing what the user should do next
- Active job/application cards with stage badges
- Recent activity or timeline-style section

Do not show only plain list rows.

### 2. Make cards feel connected

Use visually distinct cards for:

- job
- tailored resume
- application
- run/activity

Cards should include clear primary actions such as:

```text
Review job
Open resume
Continue application
View timeline
```

### 3. Improve navigation

Keep routes working, but make the sidebar feel less like raw backend tables.

Suggested primary nav:

```text
Home
Jobs
Applications
Settings
```

Secondary/advanced nav can include:

```text
Captures
Runs
```

If keeping Captures/Runs in the sidebar, visually de-emphasize them or group them under an “Advanced” label.

### 4. Improve visual style

Update CSS to make the app feel more polished:

- better spacing
- softer cards
- status badges
- clearer typography hierarchy
- less full-width thin list-row feel
- more compact readable content width
- better empty states
- clear primary/secondary buttons

Keep it simple. Do not add a component library.

### 5. Preserve existing behavior

All existing routes should still work.

Existing tests should pass, updated where necessary for copy/layout changes.

## Acceptance Criteria

- Home page no longer looks like a plain entity list.
- Home page shows summary cards and next-action workflow cards.
- Job/application/resume/run relationships are visually connected.
- Hashes, raw paths, and provenance fields are hidden behind Advanced details on detail pages where applicable.
- Existing core routes still render:
  - `/`
  - `/jobs`
  - `/jobs/:id`
  - `/applications`
  - `/applications/:id`
  - `/runs`
  - `/runs/:id`
  - `/resume-versions/:id`
  - `/settings`
- Frontend tests pass.
- Frontend build passes.

## Verification

Run:

```bash
cd frontend && npm install
cd frontend && npm test
cd frontend && npm run build
```

Also run the local app manually and inspect:

```text
http://localhost:5173
```

The first screen should clearly look like an application cockpit, not a database table browser.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Redesign frontend as application cockpit
```

Do not push.
