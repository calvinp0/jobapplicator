# Task 073: Application detail email evidence and timeline section

Task ID: `073-frontend-application-detail-email-evidence`

## Goal

Surface email evidence on `ApplicationDetailPage`: render the
`EmailLink` rows attached to the application, expose a manual-entry
form so the user can record a confirmation, rejection, next-step,
offer, or other email until Gmail integration lands, and display the
timeline stage derived by the backend.

## Background

Read first:

- `docs/adr/010-application-status-timeline.md`
- `docs/contracts/application_status.md`
- `frontend/src/pages/ApplicationDetailPage.tsx` (current page)
- `frontend/src/api/types.ts`, `frontend/src/api/index.ts` (the
  `EmailLink` type and `Application` extensions land in task 072)
- `frontend/src/lib/workflow.ts` (timeline helpers added in task 072)
- `frontend/src/styles.css` (badge and form styles)
- `frontend/src/test/applicationDetailPage.test.tsx`

The previous task wired the timeline types and labels. This task adds
the API calls, the email-evidence section, and the manual-entry form.

## Scope

- **API client** in `frontend/src/api/index.ts`:
  - Add `listApplicationEmailLinks(applicationId: string):
    Promise<EmailLink[]>` calling
    `GET /applications/{id}/email-links`.
  - Add `createApplicationEmailLink(applicationId: string, payload:
    EmailLinkCreatePayload): Promise<EmailLink>` calling
    `POST /applications/{id}/email-links`. Define
    `EmailLinkCreatePayload` to mirror the contract's
    `EmailLinkCreate` request body.
  - Re-fetch the parent application after a successful create so the
    refreshed `status` and `timeline_stage` flow into the page.

- **ApplicationDetailPage** rendering:
  - Show the current `timeline_stage` as a labelled badge (reusing
    `timelineStageLabel` / `timelineStageVariant` from task 072) next
    to the existing status badge. If they would duplicate, prefer
    the timeline-stage badge as the primary one and drop the raw
    status badge.
  - Add an "Email evidence" section that lists the attached
    `EmailLink` rows (sender, subject, received_at, classified_status
    label, optional confidence). Order: `received_at` desc, then
    `created_at` desc, mirroring the contract.
  - Add a "Record email" form with fields for `gmail_message_id`
    (default-prefilled with `manual:<generated-uuid>` and editable),
    `classified_status` (select), `sender`, `subject`, `received_at`
    (datetime-local), `confidence` (optional number).
    On submit, call `createApplicationEmailLink`, then refresh both
    the application row and the email-link list. Use
    `crypto.randomUUID()` to generate the placeholder id.
  - Treat the manual-entry form as a defense-in-depth bridge until
    Gmail integration lands; do not auto-classify or auto-fetch
    anything.

- **Empty / error states**:
  - Empty state when no `EmailLink` rows exist: "No emails recorded
    yet. The Gmail integration is not enabled — you can record an
    email by hand."
  - On API error from create or list, render an inline `role="alert"`
    error consistent with the existing error rendering.

- **Tests** in `frontend/src/test/applicationDetailPage.test.tsx`:
  - Cover the rendered timeline-stage badge for at least two stages
    (`sent` and `confirmation_received`).
  - Cover the rendered email-link list for a non-empty case.
  - Cover the empty-state copy when `email_link_count === 0`.
  - Cover the create-form happy path with a mocked
    `createApplicationEmailLink`: submitting refreshes both the
    application and the email-link list.
  - Cover the error path on create.

## Allowed files

```
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/styles.css
frontend/src/test/applicationDetailPage.test.tsx
agent_tasks/073-frontend-application-detail-email-evidence.md
agent_tasks/queue.yaml
```

`frontend/src/api/types.ts` is allowed in this task only to add the
`EmailLinkCreatePayload` request type — task 072 already adds the
`EmailLink` response type and the `Application` extensions. Do not
re-shape what task 072 added.

## Forbidden files

```
backend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/**
frontend/src/pages/ApplicationsPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/RunsPage.tsx
frontend/src/pages/JobsPage.tsx
frontend/src/pages/CapturesPage.tsx
frontend/src/pages/CaptureDetailPage.tsx
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/lib/workflow.ts
frontend/src/App.tsx
frontend/src/layout/**
```

Do not change `frontend/src/lib/workflow.ts` here — task 072 owns the
shared helpers. Re-use them.

## Out of scope

- Gmail OAuth, polling, or any network call to Google.
- Automated classification (the form lets the user pick).
- Dashboard or applications-list changes (task 072 covered the list).
- Backend changes.

## Acceptance criteria

- `ApplicationDetailPage` shows the timeline-stage badge for the
  application.
- The email-evidence section lists every attached `EmailLink` row in
  the contract-specified order.
- Submitting the create form posts to
  `POST /applications/{id}/email-links` and refreshes the page state
  on success.
- The form pre-fills `gmail_message_id` with a `manual:<uuid>`
  placeholder generated client-side.
- The page surfaces inline errors from both the list call and the
  create call.
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` passes.
- No file outside `Allowed files` is modified.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit locally on the task branch with the message:

```
Add email evidence section to application detail
```

Do not push.
