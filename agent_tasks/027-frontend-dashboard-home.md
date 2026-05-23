# 027 — Frontend dashboard home page

## Goal

Replace the `/captures` default landing page with a dedicated dashboard/home
page that summarizes the user's active jobs, in-flight runs, and applications.
This is the first step in turning the frontend from a table/entity browser
into a connected job-application cockpit. The user should be able to land on
the app and immediately see "what is happening across my pipeline today"
without first knowing the underlying entity vocabulary.

## Background

Read first:

- `docs/product_requirements.md` — MMVP workflow and non-goals.
- `docs/architecture.md` — component boundaries; the frontend is a thin SPA
  that calls the existing FastAPI surface.
- `docs/adr/001-local-first-mvp.md` — local-first scope.
- `docs/adr/003-human-in-the-loop-submission.md` — submission is human-driven;
  the dashboard surfaces *progress*, never auto-actions.
- `agent_tasks/009-frontend-shell.md`, `agent_tasks/010-frontend-job-capture-flow.md`,
  `agent_tasks/016-frontend-runs-list-and-detail.md`,
  `agent_tasks/018-frontend-applications-and-submit-flow.md` — the existing
  frontend shape this task builds on.
- `frontend/src/App.tsx`, `frontend/src/layout/Layout.tsx`,
  `frontend/src/api/index.ts`, `frontend/src/api/types.ts` — current routing
  and API surface.

## Scope

- Add `frontend/src/pages/DashboardPage.tsx` rendered at the `/` route.
  - Fetch jobs, applications, runs, and resume versions in parallel via the
    existing `listJobs`, `listApplications`, `listRuns`, and
    `listResumeVersions` helpers. Do not add new API endpoints.
  - Render three workflow-oriented sections, each linking into the existing
    detail pages:
    1. **Active jobs** — jobs with no submitted application yet. Show
       company, title, and the most-advanced state for that job
       (e.g. "Awaiting tailoring", "Resume ready to approve",
       "Approved — ready to submit"). Link each row to `/jobs/:jobId`.
    2. **In-flight runs** — Claude runs whose status is `created`,
       `running`, or `completed` but not yet imported. Link to
       `/runs/:runId`.
    3. **Recent applications** — the most recent 5 applications, each
       showing status, job title, and submitted-at timestamp. Link to
       `/applications/:applicationId`.
  - Show a header strip with at-a-glance counts:
    "{n} active jobs · {n} in-flight runs · {n} applications submitted".
  - Handle loading and error states the same way existing pages do
    (loading paragraph, `role="alert"` error paragraph).
  - Show a clear empty-state message in each section when there is no
    matching data, with a sentence pointing the user at the next step
    (e.g. "No active jobs yet — capture a job from the extension").
- Update `frontend/src/App.tsx`:
  - Mount `DashboardPage` at `/`.
  - Keep `/captures`, `/captures/:captureId`, `/jobs`, `/jobs/:jobId`,
    `/runs`, `/runs/:runId`, `/resume-versions/:versionId`,
    `/applications`, `/applications/:applicationId`, `/settings` as they
    are.
  - Change the catch-all `<Route path="*">` to redirect to `/` rather
    than `/captures`. The bare `/captures` URL must keep working
    (already mounted explicitly) so existing bookmarks survive.
- Update `frontend/src/layout/Layout.tsx`:
  - Add a "Home" nav item at the top of `NAV_ITEMS`, pointing at `/`.
  - The existing "Captures" badge logic for pending captures must stay
    intact and continue to read from `listCaptures`.
- Update `frontend/src/styles.css`:
  - Add styles scoped to the dashboard (e.g. `.dashboard`,
    `.dashboard-section`, `.dashboard-summary`, `.dashboard-empty`).
  - Do not refactor unrelated existing styles.
- Add `frontend/src/test/dashboardPage.test.tsx`:
  - Render `DashboardPage` with mocked API responses.
  - Cover at least: loading state, populated state with one job / one
    run / one application, empty state, error state when one fetch
    rejects.
- Update `frontend/src/test/routes.test.tsx` if it currently asserts the
  root redirects to `/captures`; the new expectation is that `/`
  renders the dashboard. Other route assertions must remain
  unchanged.

## Allowed files

- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/App.tsx`
- `frontend/src/layout/Layout.tsx`
- `frontend/src/styles.css`
- `frontend/src/test/dashboardPage.test.tsx`
- `frontend/src/test/routes.test.tsx`
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
- `frontend/src/api/**` — no new API endpoints in this task.
- `frontend/src/pages/JobDetailPage.tsx`,
  `frontend/src/pages/RunDetailPage.tsx`,
  `frontend/src/pages/ResumeVersionDetailPage.tsx`,
  `frontend/src/pages/ApplicationDetailPage.tsx` — out of scope here.

## Out of scope

- Reshaping `JobDetailPage` into a workflow hub — that is task 028.
- Hiding provenance behind "Advanced details" disclosures — task 029.
- Renaming entity-style headings on detail pages or adding status
  badges — task 030.
- Adding new API endpoints, new database fields, or any backend work.
- Adding charts or data visualization libraries.

## Acceptance criteria

- Navigating to `/` renders the dashboard with the three sections and
  the summary header.
- The "Home" nav item is visible in the sidebar and is the active
  link on `/`.
- `/captures` still resolves to the captures page; the captures badge
  on the sidebar still reflects unconfirmed captures.
- Each dashboard row links to the matching detail route.
- Loading and error states are rendered (no blank screen).
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` succeeds.

## Verification

- `cd frontend && npm test`
- `cd frontend && npm run build`

## Git instructions

Commit locally with the message:

```
Add frontend dashboard home page
```

Do not push.
