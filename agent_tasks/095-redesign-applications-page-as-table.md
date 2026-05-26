# Task 095: Redesign Applications Page as Table Dashboard

## Goal

Redesign the Applications page from stacked cards into a cleaner table-style dashboard.

The current Applications page feels visually rough:

```text
- application cards are too tall
- repeated action buttons make the page noisy
- "Sync Gmail" appears as a small unstyled button floating under the title
- Gmail status text is hard to scan
- application statuses are not aligned in a dashboard/table style
```

Create a more polished application tracking dashboard.

Do not change Gmail backend behavior in this task.  
Do not change database reset behavior.  
Do not change Claude tailoring behavior.  
Do not implement LinkedIn automation.

## Background

The current page shows applications as separate large cards.

The user wants something closer to a table view.

The Applications page should answer quickly:

```text
Which jobs have I applied to?
Which are drafts?
Which are submitted?
Which are waiting for email?
Which need review?
Which are rejected/interview/approved?
When did I last check Gmail?
What is the next action?
```

## Inspect

Inspect:

```text
frontend/src/pages/
frontend/src/components/
frontend/src/api/types.ts
frontend/src/api/index.ts
frontend/src/test/
backend/app/schemas.py
backend/app/routers/
docs/contracts/
```

Search:

```bash
rg "Applications|Sync Gmail|Mark submitted|Mark interview|Mark rejected|email_status|next_action" frontend backend docs
```

Use the existing design system/styles.

## Required UI Design

Replace or augment the card list with a table-like layout.

Suggested columns:

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

If the app currently stores title/company combined, split visually where possible.

Example row:

```text
Graduate Software Engineer
InfinityLabs R&D
Sent
Submitted 5/25/2026
No related emails found
Draft ready to review
1h ago
Waiting for email
Open · Mark interview · Mark rejected
```

## Header Toolbar

Move Gmail sync into a polished toolbar.

Top area should look like:

```text
Applications                                      [Sync Gmail] [Filters]
Track drafts, submissions, email evidence, and outcomes.
```

The `Sync Gmail` button should:

```text
- be styled consistently with other primary/secondary buttons
- not appear as a tiny raw HTML button
- show loading state while syncing
- show last sync summary if available
```

Example:

```text
[Sync Gmail]
Last sync: checked 5 applications · updated 1 · 2 need review
```

If Gmail is disconnected:

```text
Gmail not connected. Connect in Settings.
```

with a link to Settings.

## Table/Card Hybrid

On desktop, use table layout.

On small screens, responsive compact cards are acceptable.

Desktop table should have:

```text
sticky or clear header row
aligned status badges
compact row actions
consistent spacing
hover state
```

Rows should not be overly tall unless expanded.

## Status Badges

Use explicit text badges, not color alone.

Badges:

```text
Draft
Ready
Sent
Pending
Waiting email
Needs review
Interview
Approved
Rejected
Withdrawn
Error
```

Email badges:

```text
Not watching
No match
Email received
Needs review
Confirmation
Rejection
Interview
Assessment
Offer
```

Submission badges:

```text
Not submitted
Submitted
Unknown
```

## Row Actions

Avoid repeating large buttons.

Use compact actions:

```text
Open
Mark submitted
Mark interview
Mark rejected
```

If there are too many actions, use an actions menu or secondary inline links.

Primary action should be derived from next action:

```text
Ready to submit → Mark submitted
Waiting for email → Check Gmail
Needs review → Review email
Draft → Open
```

## Filtering

Add basic filters if not already present:

```text
All
Drafts
Ready
Submitted
Needs review
Interviews
Rejected
```

The filter UI should be compact and visually integrated near the toolbar.

If filtering is too large, implement layout first and leave filtering for a later task, but the page should be structured so filters can be added easily.

## Sorting

Sort by:

```text
needs attention first
then recently updated
```

Suggested priority:

```text
needs_review
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

If existing backend already sorts, preserve or improve it.

## Gmail Evidence Summary

For each row, show a short email summary:

```text
No related emails found
Possible email needs review
Confirmation found
Rejected by email
Interview email found
Not watching yet
```

If a linked/matched email exists, show:

```text
Subject snippet
Sender
```

Keep it short.

Full evidence belongs on the application detail page.

## Empty State

If there are no applications, show a polished empty state:

```text
No applications yet.
Create or generate a draft from a job to start tracking applications.
```

## Frontend API Types

Update types only as needed.

The table should use existing fields from previous tasks:

```text
status
submission_status
email_status
matched_email_count
latest_email_subject
latest_email_from
latest_email_snippet
latest_email_classification
last_gmail_check_at
latest_run_status
updated_at
next_action
```

If fields are missing, handle gracefully.

## Tests

Add/update frontend tests if infrastructure exists.

Tests should prove:

1. Applications page renders table headers.
2. Applications render as rows, not only large cards.
3. Sync Gmail button is in the toolbar.
4. Sync Gmail button has loading state.
5. Gmail disconnected state links to Settings.
6. Status badge renders.
7. Submission state renders.
8. Email state renders.
9. Next action renders.
10. Mark submitted/interview/rejected actions still work.
11. Empty state renders.
12. Responsive fallback does not break build.

Backend tests are not required unless API shape changes.

## Acceptance Criteria

- Applications page uses a compact table/dashboard layout.
- Gmail sync is integrated into a toolbar and styled consistently.
- Rows show status, submission, email, latest run, updated time, and next action.
- Actions are compact and not visually noisy.
- Gmail disconnected state points to Settings.
- Existing mark submitted/interview/rejected behavior still works.
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
3. Open Applications page.
4. Confirm applications appear in table/dashboard layout.
5. Confirm Sync Gmail is in the toolbar and styled consistently.
6. Confirm rows show:
   - job/company
   - status
   - submission
   - email
   - latest run
   - updated
   - next action
7. Click Mark submitted and confirm row updates.
8. Click Mark rejected and confirm row updates.
9. Click Sync Gmail and confirm loading/summary state.
10. Resize browser and confirm layout remains usable.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Redesign Applications page as table
```

Do not push.
