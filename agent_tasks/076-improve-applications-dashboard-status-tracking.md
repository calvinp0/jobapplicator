# Task 076: Improve Applications Dashboard Status Tracking

## Goal

Improve the Applications page so each application card shows enough information to understand the current state of the application.

The current Applications page only shows the job title/company and a generic status like:

```text
Draft
```

This is not enough. The UI should show whether the application is drafted, ready, submitted, waiting for email recognition, rejected, pending, approved/interviewing, or needs user action.

Do not implement Gmail automation in this task.
Do not implement LinkedIn automation in this task.
Do not change Claude tailoring behavior in this task.
Do not change document generation in this task.

## Background

Inspect:

```text
frontend/
backend/app/
backend/tests/
docs/contracts/
```

Find the current Applications page/component and the backend API/model that supplies application data.

Likely areas to inspect:

```text
frontend/src/
frontend/app/
backend/app/main.py
backend/app/run_directory.py
backend/app/models.py
backend/app/database.py
backend/tests/
```

Use the actual project structure.

## Current Problem

The Applications page currently renders application rows/cards with too little information:

```text
Application title
Draft badge
```

Users need to know:

```text
- Is this only a draft?
- Has it been submitted?
- Is it waiting for the user?
- Is it waiting for email recognition?
- Did an email arrive?
- Was it rejected?
- Is it pending?
- Is there an interview / positive response?
- When was it last updated?
- Which job is it linked to?
- Which generation run produced it?
```

## Required Application Status Model

Add or document a clear application lifecycle.

Use these statuses unless the existing project already has equivalent names:

```text
draft
ready_to_submit
submitted
waiting_for_email
email_received
pending
interview
approved
rejected
withdrawn
stale
error
```

Status meanings:

```text
draft
  Resume/application materials are still being generated or edited.

ready_to_submit
  Materials exist and user can submit manually.

submitted
  User marked the application as submitted.

waiting_for_email
  Application was submitted and system is waiting for confirmation/follow-up email.

email_received
  A related email was detected, but not yet classified.

pending
  Application is active with no final outcome.

interview
  Positive response or interview-related state.

approved
  Application advanced beyond initial screen or received positive decision.

rejected
  Rejection detected or manually marked.

withdrawn
  User withdrew or abandoned the application.

stale
  No activity after a configurable number of days.

error
  Something failed in generation/import/tracking.
```

If the backend already has a status enum, extend it rather than creating a conflicting one.

## Application Card UI Requirements

Each application item should show:

```text
Job title
Company
Application status badge
Submission state
Last updated time
Created time or age
Linked job/source
Latest run status if available
Email recognition state if available
Primary next action
```

Example card:

```text
Scientific Machine Learning Engineer — Example Aero Labs

Status: Draft
Submission: Not submitted
Email: Not watching yet
Latest run: Tailoring completed
Updated: 2 minutes ago

Actions:
Open
Generate draft
Mark submitted
```

Another example:

```text
Scientific Machine Learning Engineer — Example Aero Labs

Status: Submitted
Submission: Submitted May 25, 2026
Email: Waiting for confirmation
Latest run: Final resume ready
Updated: 1 day ago

Actions:
Open
Mark response received
Mark rejected
Mark interview
```

Another example:

```text
Scientific Machine Learning Engineer — Example Aero Labs

Status: Rejected
Submission: Submitted May 20, 2026
Email: Rejection detected
Updated: May 24, 2026

Actions:
Open
View email evidence
Archive
```

## Visual Requirements

Use distinct badges for:

```text
Draft
Ready
Submitted
Waiting
Email received
Pending
Interview
Approved
Rejected
Error
```

The UI should not rely only on color. Badge text must be explicit.

Each card should have a short “next action” label, such as:

```text
Needs draft generation
Ready to submit
Waiting for email
Review detected email
Follow up
Rejected
Interview response needed
```

## Backend/Data Requirements

Persist or expose these fields where possible:

```json
{
  "id": "...",
  "job_id": "...",
  "job_title": "...",
  "company": "...",
  "status": "draft",
  "submission_status": "not_submitted",
  "email_status": "not_watching",
  "latest_run_id": "...",
  "latest_run_status": "completed",
  "created_at": "...",
  "updated_at": "...",
  "submitted_at": null,
  "last_email_at": null,
  "next_action": "Generate draft"
}
```

If database migrations exist, add the necessary migration.

If this project currently stores application state in files or JSON, update that storage contract instead.

## Submission State

Add a separate submission state if not already present:

```text
not_submitted
submitted
unknown
```

The application status and submission state are not identical.

For example:

```text
status=draft, submission_status=not_submitted
status=pending, submission_status=submitted
status=rejected, submission_status=submitted
```

## Email Recognition State

Add an email recognition state placeholder without implementing Gmail automation:

```text
not_watching
watching
email_received
classified_positive
classified_rejection
classified_neutral
needs_review
```

For this task, it is acceptable for email state to be manually set or always default to:

```text
not_watching
```

Do not connect Gmail in this task.

## Manual Status Actions

Add minimal backend/frontend actions where practical:

```text
Mark submitted
Mark pending
Mark interview
Mark approved
Mark rejected
Mark withdrawn
```

If adding all actions is too large, implement at least:

```text
Mark submitted
Mark rejected
Mark interview
```

These actions should update:

```text
status
submission_status where relevant
updated_at
submitted_at when marking submitted
```

## Sorting

Applications page should sort by most recently updated first.

Within the same updated time, prioritize applications needing user action:

```text
email_received
ready_to_submit
draft
submitted/waiting
pending
interview
approved
rejected
withdrawn
```

## Filtering

Add simple filters if the frontend structure makes it easy:

```text
All
Drafts
Ready
Submitted
Needs attention
Interviews
Rejected
```

If filtering is too large for this task, add the data model now and leave filtering for a later task.

## Tests

Add or update backend tests to prove:

1. Applications expose richer status fields.
2. New applications default to `draft`.
3. New applications default to `submission_status=not_submitted`.
4. New applications default to `email_status=not_watching`.
5. Mark submitted updates status/submission timestamps.
6. Mark rejected updates status.
7. Mark interview updates status.
8. Applications sort by updated time.
9. API response includes `next_action`.

Add or update frontend tests if the project already has them to prove:

1. Applications page shows status badge.
2. Applications page shows submission state.
3. Applications page shows email state.
4. Applications page shows updated time.
5. Applications page shows next action.
6. Mark submitted/rejected/interview actions appear.

If the project has no frontend test setup, document manual verification instead of adding a new test framework.

## Acceptance Criteria

- Applications page is no longer just title + Draft.
- Each application shows application status, submission state, email state, updated time, latest run state if available, and next action.
- User can manually mark at least submitted, rejected, and interview.
- Backend persists or exposes the richer status fields.
- Existing application data remains backwards compatible.
- Tests pass.

## Verification

Run backend tests:

```bash
pytest
```

Run frontend verification:

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
3. Open Applications page.
4. Confirm each card shows:
   - job title
   - company
   - status badge
   - submission state
   - email state
   - updated time
   - next action
5. Mark one application as submitted.
6. Confirm badge/state update.
7. Mark one application as rejected.
8. Confirm badge/state update.
9. Mark one application as interview.
10. Confirm badge/state update.
11. Refresh page and confirm states persist.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Improve applications dashboard status tracking
```

Do not push.
