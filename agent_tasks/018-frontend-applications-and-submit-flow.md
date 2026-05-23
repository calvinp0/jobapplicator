# Task 018: Frontend applications page and mark-submitted flow

## Goal

Close the loop on the MMVP workflow by giving the operator a UI for
creating an application against an approved resume version, marking
it submitted, and viewing its event timeline. This is the final
in-app step of the local cockpit before Gmail integration.

## Background

Read:

- `docs/product_requirements.md` (MMVP step 12, application
  tracking)
- `docs/adr/003-human-in-the-loop-submission.md`
- `backend/app/routers/applications.py` (existing list/create and
  the submit / events endpoints added in task 014)
- `backend/app/schemas.py` (`ApplicationCreate`,
  `ApplicationRead`, the application event schema added in task 014)
- `agent_tasks/014-backend-application-submit-and-open-file.md`
- `agent_tasks/017-frontend-resume-version-approval-and-open-file.md`
  (approval is a prerequisite of being able to attach a version to an
  application)
- `frontend/src/pages/ApplicationsPage.tsx` (current placeholder)
- `frontend/src/pages/JobDetailPage.tsx`

## Scope

Within `frontend/src/`:

- Extend `frontend/src/api/types.ts` with an `ApplicationEvent`
  type matching the backend schema added in task 014.
- Add API client functions in `frontend/src/api/index.ts`:
  - `createApplication(payload)` → `POST /applications`
  - `submitApplication(id)` → `POST /applications/{id}/submit`
  - `listApplicationEvents(id)` → `GET /applications/{id}/events`
  - `createApplicationEvent(id, payload)` →
    `POST /applications/{id}/events`
- Replace `frontend/src/pages/ApplicationsPage.tsx`:
  - List existing applications with company / title (joined from the
    job), status, submitted_at, and a link to a detail page.
  - Use existing `listJobs()` to resolve job ids to company/title
    client-side (no new backend join required).
- Add a new page `frontend/src/pages/ApplicationDetailPage.tsx` with
  route `/applications/:applicationId`:
  - Show the application status, submitted_at, the linked resume
    version (if any), and the linked job (with a link to
    `/jobs/:jobId`).
  - Show the event timeline from `listApplicationEvents`, ordered
    ascending.
  - **Mark Submitted** button — calls `submitApplication`. Disabled
    when `status === "submitted"` or when there is no linked resume
    version, or when the linked resume version is not yet approved
    (fetch the version to check `approved_at` — display the gating
    reason next to the disabled button).
  - A small form to record a manual event (event_type + notes) via
    `createApplicationEvent`, refreshing the timeline on success.
- Extend `frontend/src/pages/JobDetailPage.tsx` to add an "Apply"
  section that lets the operator create an application for this job
  from a chosen approved resume version:
  - List the approved resume versions for this job.
  - A "Create application" button per version that calls
    `createApplication({ job_id, resume_version_id, status: "approved" })`
    and navigates to the new application's detail page.
  - If no approved version exists for the job, show a clear "approve
    a resume version first" message linking to the Resume versions
    section.
- Register the `/applications/:applicationId` route in
  `frontend/src/App.tsx`.
- Tests in `frontend/src/test/`:
  - Applications list renders with mocked API (multiple applications
    + jobs).
  - Application detail: Mark Submitted is disabled when no approved
    resume version is linked; enabled when one is. Clicking it calls
    `submitApplication` and updates the displayed status.
  - Application detail: a manual event submitted through the form
    appears in the timeline.
  - Job detail: "Create application" is gated on an approved resume
    version and navigates to the new application on success.

## Allowed files

- `frontend/src/pages/ApplicationsPage.tsx`
- `frontend/src/pages/ApplicationDetailPage.tsx`
- `frontend/src/pages/JobDetailPage.tsx`
- `frontend/src/App.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly
  instructed)

## Forbidden files

- `backend/**`
- `extension/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/**`
- Other `agent_tasks/*.md`
- Other frontend pages and layout (run detail, captures, settings,
  resume version detail)

## Out of scope

- Gmail / `EmailLink` integration.
- Editing or deleting applications.
- Reordering events, custom event types beyond what the backend
  accepts.
- Bulk actions across applications.
- Long-polling / websocket updates.

## Acceptance criteria

- `/applications` lists existing applications with their job
  context and status.
- `/applications/:id` shows the timeline and exposes a working
  Mark Submitted action gated on an approved resume version.
- `/jobs/:jobId` exposes an Apply section that creates an
  application against an approved resume version and navigates to
  its detail page.
- Errors from the backend surface in the UI consistently with the
  rest of the cockpit.
- `npm test` and `npm run build` pass from `frontend/`.
- No backend, extension, or doc files are touched.

## Verification

Run from `frontend/`:

```bash
npm test
npm run build
```

## Git instructions

Commit message:

```text
Add applications page and mark-submitted flow
```

Do not push.
