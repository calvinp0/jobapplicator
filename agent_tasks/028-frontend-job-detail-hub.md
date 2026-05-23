# 028 — Make JobDetailPage the central workflow hub

## Goal

Reshape `JobDetailPage` from a stack of separately-labelled sub-sections
("Resume versions", "Apply", "Generate tailored resume") into a single
workflow hub. The page should make the user's next concrete step obvious
("tailor a resume", "approve the latest draft", "submit your
application") and surface the runs and applications that already exist
for this job inline so the user does not have to navigate to `/runs` or
`/applications` to see the state of *this* job.

## Background

Read first:

- `docs/product_requirements.md` — the human-in-the-loop submission
  flow this page anchors.
- `docs/adr/003-human-in-the-loop-submission.md` — the page must
  surface progress but never auto-submit.
- `docs/adr/004-evidence-constrained-resume-tailoring.md` — the
  generate-resume form must stay evidence-bank aware.
- `agent_tasks/010-frontend-job-capture-flow.md`,
  `agent_tasks/017-frontend-resume-version-approval-and-open-file.md`,
  `agent_tasks/018-frontend-applications-and-submit-flow.md` — prior
  iterations of this page.
- `agent_tasks/027-frontend-dashboard-home.md` — sets the design
  language (workflow-oriented copy, sectioned layout) this task
  continues.
- `frontend/src/pages/JobDetailPage.tsx`,
  `frontend/src/test/jobDetailApply.test.tsx`,
  `frontend/src/test/jobDetailResumeVersions.test.tsx` — current page
  and tests this task updates.

## Scope

Update `frontend/src/pages/JobDetailPage.tsx`:

- Fetch existing data the page already loads (`getJob`,
  `listMasterResumes`, `listEvidenceBanks`, `listResumeVersions`) plus
  the runs (`listRuns`) and applications (`listApplications`) for the
  current job. Filter runs and applications client-side by `job_id`.
  Do not add new API endpoints.
- Render a header block:
  - Title: `"{job.title} — {job.company}"`.
  - Location and external URL (existing behavior).
  - A single-line "Job status" indicator that summarizes the most
    advanced state for this job, e.g.:
    `Captured → Tailoring → Approved → Submitted`. Highlight the
    current stage. Compute the stage from the data already fetched:
    - `Captured` when no runs exist,
    - `Tailoring` when at least one run exists but no resume version
      is approved,
    - `Approved` when at least one resume version is approved but no
      application has `status === "submitted"`,
    - `Submitted` when any application for this job has
      `status === "submitted"`.
- Replace the existing three sub-section headings with workflow-oriented
  ones:
  - "Tailored resumes" instead of "Resume versions".
  - "Submit this job" instead of "Apply".
  - "Tailor a new resume" instead of "Generate tailored resume".
- Inside "Tailored resumes":
  - List existing resume versions (already implemented) using
    user-facing labels (e.g. `"Draft 1"`, `"Draft 2 (approved)"`).
    The visible label change for individual draft items is deferred
    to task 030; this task only renames the section heading and adds
    the runs subsection below.
  - Add an "In-flight runs" sub-list directly under "Tailored
    resumes" that shows runs whose status is one of `created`,
    `running`, or `completed-not-imported`. Each row links to
    `/runs/:runId` and shows status text.
- Inside "Submit this job":
  - Keep the existing approved-resume + "Create application" flow.
  - Add a list of existing applications for this job. Each row shows
    application status, submitted-at timestamp (if any), and links to
    `/applications/:applicationId`. If there is an application in
    `submitted` status, hide the "Create application" buttons to
    avoid encouraging duplicates.
- Inside "Tailor a new resume":
  - Keep the existing master-resume + evidence-bank form.
  - Add one short helper sentence above the form describing when to
    use it (e.g. "Generate a new tailored draft when you want to
    iterate on the resume.").

Update `frontend/src/styles.css`:

- Add styles for the job-status indicator strip (e.g.
  `.job-status-track`, `.job-status-step`, `.job-status-step-active`)
  and for any new inline lists. Do not refactor unrelated styles.

Update `frontend/src/test/jobDetailApply.test.tsx` and
`frontend/src/test/jobDetailResumeVersions.test.tsx`:

- Update assertions for renamed section headings.
- Add assertions covering the new in-flight-runs list and the
  applications list under "Submit this job", and the suppression of
  "Create application" buttons when a submitted application exists.
- Do not weaken existing assertions; they should still cover the
  prior happy paths.

## Allowed files

- `frontend/src/pages/JobDetailPage.tsx`
- `frontend/src/test/jobDetailApply.test.tsx`
- `frontend/src/test/jobDetailResumeVersions.test.tsx`
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
- `frontend/src/api/**` — no new API endpoints.
- `frontend/src/pages/DashboardPage.tsx`,
  `frontend/src/pages/RunDetailPage.tsx`,
  `frontend/src/pages/ResumeVersionDetailPage.tsx`,
  `frontend/src/pages/ApplicationDetailPage.tsx`,
  `frontend/src/App.tsx`,
  `frontend/src/layout/Layout.tsx` — not edited by this task.

## Out of scope

- Renaming `"Version N"` labels on individual resume-version rows or
  on the resume-version detail page — that is task 030.
- Wrapping provenance fields in `<details>` blocks — task 029.
- Adding a global status-badge component — task 030.
- Any backend or API change.

## Acceptance criteria

- The page renders a job-status strip with the correct stage
  highlighted for each of the four stages (Captured, Tailoring,
  Approved, Submitted) given the fetched data.
- Section headings read "Tailored resumes", "Submit this job", and
  "Tailor a new resume".
- The "Tailored resumes" section shows in-flight runs for this job
  with links to `/runs/:runId`.
- The "Submit this job" section shows existing applications for this
  job with links to `/applications/:applicationId`, and suppresses the
  "Create application" buttons when one is already `submitted`.
- All previously passing tests in
  `frontend/src/test/jobDetailApply.test.tsx` and
  `frontend/src/test/jobDetailResumeVersions.test.tsx` either still
  pass or have been replaced with stronger assertions on the new
  copy. No assertion is removed without an equivalent replacement.
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` succeeds.

## Verification

- `cd frontend && npm test`
- `cd frontend && npm run build`

## Git instructions

Commit locally with the message:

```
Make JobDetailPage the central workflow hub
```

Do not push.
