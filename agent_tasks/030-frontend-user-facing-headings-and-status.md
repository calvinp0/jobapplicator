# 030 — User-facing headings and status badges

## Goal

Replace entity-style headings (e.g. "Resume version 1", "Run
{uuid}", "Application") with user-facing labels that read like a job
applicant would describe them, and add small status badges that
communicate progress at a glance. This is the polish layer of the
cockpit redesign — the data and structure are unchanged; only the
visible language and progress cues are updated.

## Background

Read first:

- `docs/product_requirements.md` — the user-facing framing.
- `docs/adr/003-human-in-the-loop-submission.md` — submission states.
- `agent_tasks/027-frontend-dashboard-home.md`,
  `agent_tasks/028-frontend-job-detail-hub.md`,
  `agent_tasks/029-frontend-advanced-details-disclosure.md` — the
  preceding cockpit work this task completes.
- Current pages:
  `frontend/src/pages/RunDetailPage.tsx`,
  `frontend/src/pages/ResumeVersionDetailPage.tsx`,
  `frontend/src/pages/ApplicationDetailPage.tsx`,
  `frontend/src/pages/RunsPage.tsx`,
  `frontend/src/pages/ApplicationsPage.tsx`,
  `frontend/src/pages/JobsPage.tsx`.
- Existing tests:
  `frontend/src/test/runDetailPage.test.tsx`,
  `frontend/src/test/resumeVersionDetailPage.test.tsx`,
  `frontend/src/test/applicationDetailPage.test.tsx`,
  `frontend/src/test/applicationsPage.test.tsx`,
  `frontend/src/test/runsPage.test.tsx`.

## Scope

### Renamed headings

- `ResumeVersionDetailPage` `<h2>` becomes
  `"Resume draft {version.version_number} for {job.title} — {job.company}"`
  when the job has loaded, and falls back to
  `"Resume draft {version.version_number}"` while the job is loading
  or unavailable. Use the word "draft" consistently for resume
  versions in the user-facing copy.
- `RunDetailPage` `<h2>` becomes
  `"Resume tailoring run — {job.title} — {job.company}"` when the
  parent job can be resolved, and `"Resume tailoring run"` otherwise.
  The page must fetch the run's job (via the existing run → job_id
  relation and `getJob`) for this label; do not add new API
  endpoints.
- `ApplicationDetailPage` `<h2>` becomes
  `"Application — {job.title} — {job.company}"` when the job has
  loaded, and `"Application"` otherwise.

### Status badges

Introduce a small inline status badge component used across these
pages. Implement it as a local helper inside one of the page files
already in this task's allowed paths (do **not** create a new
shared-component file or directory). Apply it in:

- `RunDetailPage`: render the badge next to the heading, mapping the
  raw `status` string to badge labels:
  - `created` → "Pending"
  - `running` → "Running"
  - `completed` → "Completed"
  - `failed` → "Failed"
  - other values → the raw string, capitalized.
- `ResumeVersionDetailPage`: badge with "Approved" if
  `approved_at` is set, otherwise "Draft".
- `ApplicationDetailPage`: badge with the application status,
  capitalized. Always show "Submitted" when `status === "submitted"`.
- `RunsPage`, `ApplicationsPage`: render a badge column or inline
  badge per row using the same mapping.

The badge must be a small styled `<span>` (no buttons, no
interactivity); style it via classes in `frontend/src/styles.css`
(e.g. `.status-badge`, `.status-badge-pending`,
`.status-badge-running`, `.status-badge-approved`,
`.status-badge-submitted`, `.status-badge-failed`).

### List page labels

- `JobsPage`: keep the row format but ensure each row label reads
  `"{title} — {company}"`. If the page already does this, no change
  is required; do not refactor unrelated code.
- `RunsPage` and `ApplicationsPage`: rows must include the linked
  job's `title — company` if not already present. Use existing API
  helpers; do not add new endpoints.

### Tests

Update or extend:

- `frontend/src/test/runDetailPage.test.tsx`
- `frontend/src/test/resumeVersionDetailPage.test.tsx`
- `frontend/src/test/applicationDetailPage.test.tsx`
- `frontend/src/test/runsPage.test.tsx`
- `frontend/src/test/applicationsPage.test.tsx`

Each test that previously asserted an entity-style heading must be
updated to the new user-facing heading without weakening the
assertion. Add assertions covering badge rendering for at least one
status value per page.

## Allowed files

- `frontend/src/pages/RunDetailPage.tsx`
- `frontend/src/pages/ResumeVersionDetailPage.tsx`
- `frontend/src/pages/ApplicationDetailPage.tsx`
- `frontend/src/pages/RunsPage.tsx`
- `frontend/src/pages/ApplicationsPage.tsx`
- `frontend/src/pages/JobsPage.tsx`
- `frontend/src/test/runDetailPage.test.tsx`
- `frontend/src/test/resumeVersionDetailPage.test.tsx`
- `frontend/src/test/applicationDetailPage.test.tsx`
- `frontend/src/test/runsPage.test.tsx`
- `frontend/src/test/applicationsPage.test.tsx`
- `frontend/src/styles.css`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `extension/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `runs/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- `frontend/src/api/**`
- `frontend/src/pages/JobDetailPage.tsx`,
  `frontend/src/pages/DashboardPage.tsx`,
  `frontend/src/pages/CapturesPage.tsx`,
  `frontend/src/pages/CaptureDetailPage.tsx`,
  `frontend/src/pages/SettingsPage.tsx`,
  `frontend/src/pages/Placeholder.tsx`,
  `frontend/src/App.tsx`,
  `frontend/src/layout/Layout.tsx` — not edited by this task.

## Out of scope

- Creating a new shared `components/` directory for the badge — keep
  the helper local to a page file in scope.
- Touching `JobDetailPage` (it was reshaped in task 028).
- Any backend or API change, and any change to existing API
  signatures.
- Adding new routes or moving routes between paths.

## Acceptance criteria

- Each detail page's `<h2>` reads the user-facing string described
  above when the parent job has loaded, with the documented fallback
  while loading.
- Status badges render on the three detail pages and on the two list
  pages, mapped per the table above. Labels are human-readable, not
  raw enum values, where the mapping is defined.
- Existing tests still pass; updated tests assert both the new
  headings and at least one badge state per page.
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` succeeds.

## Verification

- `cd frontend && npm test`
- `cd frontend && npm run build`

## Git instructions

Commit locally with the message:

```
Add user-facing headings and status badges to detail and list pages
```

Do not push.
