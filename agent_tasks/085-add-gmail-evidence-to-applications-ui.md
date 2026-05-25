# Task 085: Add Gmail Evidence to Applications UI

## Goal

Show Gmail tracking, matched email candidates, classification results, and evidence in the Applications UI.

This task should connect the frontend to the Gmail search/classification backend from Tasks 083 and 084.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Task 080 added the Gmail email status model.

Task 082 added Gmail read-only OAuth connection.

Task 083 added Gmail search for application-related emails.

Task 084 added Gmail email classification with evidence.

The frontend now needs to make this visible and usable:

```text
Application card/detail
  ↓
Gmail status
  ↓
Check Gmail button
  ↓
Candidate emails
  ↓
Classify button
  ↓
Evidence and resulting application status
```

The user should be able to understand why an application is marked as rejected, interview, pending, or needs review.

## Inspect

Inspect:

```text
frontend/src/api/
frontend/src/pages/
frontend/src/components/
frontend/src/test/
backend/app/routers/
backend/app/schemas.py
docs/contracts/gmail_integration.md
agent_tasks/queue.yaml
```

Search for:

```bash
rg "Applications|Application|gmail|email_status|classification|evidence|status" frontend backend docs
```

Use the existing UI style and API conventions.

## Required UI Behavior

Add Gmail information to the application card and/or application detail page.

Each application should show, where available:

```text
Email status
Matched email count
Latest email subject
Latest email sender
Latest email snippet
Latest classification
Classification confidence
Evidence
Last Gmail check time
```

Example display:

```text
Email: Classified rejection
Latest email: Application update from jobs@example.com
Evidence: "not moving forward" in snippet
Checked: 2 minutes ago
```

If Gmail is not connected:

```text
Gmail: Not connected
Action: Connect Gmail
```

If Gmail is connected but no search has run:

```text
Gmail: Not checked
Action: Check Gmail
```

If no match:

```text
Gmail: No related emails found
Action: Check again
```

If candidates exist but are unclassified:

```text
Gmail: Email received
Action: Review candidate email
```

## Required Actions

Add these user actions where appropriate:

```text
Connect Gmail
Check Gmail
Classify
Review evidence
```

### Connect Gmail

Use the Task 082 endpoint:

```text
GET /api/gmail/auth-url
```

Open or navigate to the returned auth URL.

If frontend OAuth handling already exists, use it.

### Check Gmail

Call the Task 083 endpoint, likely:

```text
POST /api/applications/{application_id}/gmail/search
```

Payload:

```json
{
  "max_results": 10,
  "include_ats_terms": true
}
```

Show returned candidates.

### Classify

Call the Task 084 endpoint, likely:

```text
POST /api/applications/{application_id}/gmail/classify
```

Payload may be:

```json
{
  "message_id": "<message-id>"
}
```

or:

```json
{
  "classify_top_candidate": true
}
```

Use the implemented backend shape.

After classification, refresh the application data.

## Candidate Email Display

Show candidate emails as compact cards:

```text
Subject
From
Date
Snippet
Matched signals
Match score
Classify button
```

Do not show full email bodies.

Do not show raw internal Gmail IDs unless needed for debugging; if needed, keep them visually secondary.

## Evidence Display

For classified emails, show evidence clearly:

```text
Classification: Rejection
Confidence: 86%
Reason: Matched rejection phrase in email snippet
Evidence:
- snippet: "not moving forward"
```

The UI must not rely only on color. Use explicit labels.

## Application Status Interaction

If backend classification updates the application status, show the new status immediately after refresh.

If backend returns a suggested status but does not apply it automatically, provide an explicit action:

```text
Apply suggested status
```

Only add this action if the backend supports it.

Do not implement new backend status-changing behavior in this task unless necessary to complete the UI integration.

## Frontend API Types

Update frontend API client/types to include Gmail fields from previous tasks:

```ts
email_status
matched_email_count
latest_email_subject
latest_email_from
latest_email_snippet
latest_email_classification
latest_email_confidence
latest_email_evidence
last_gmail_check_at
```

Also add types for:

```ts
GmailStatusResponse
GmailSearchResponse
GmailCandidateEmail
GmailClassificationResponse
GmailEvidenceItem
```

Use the actual project TypeScript conventions.

## Error Handling

Handle:

```text
Gmail not connected
OAuth URL failure
Search failure
No candidates
Classification failure
Backend validation errors
```

The UI should show useful messages without crashing.

Examples:

```text
Connect Gmail before checking for application emails.
No related emails found.
Could not classify this email. Try again or review manually.
```

## Privacy and Safety Requirements

Enforce in UI:

```text
Read-only Gmail integration.
No sending.
No deleting.
No archiving.
No labeling.
No full email bodies.
Only snippets/metadata/evidence are displayed.
```

Add a short note in the Gmail UI area:

```text
Gmail is used read-only for application tracking. JobApplicator does not send, delete, archive, or label emails.
```

## Documentation

Update:

```text
docs/contracts/gmail_integration.md
```

Add:

```text
Frontend Gmail evidence UI
User actions
Displayed fields
Privacy note
Manual review behavior
```

If there is a user-facing README or install guide, add a short pointer to Gmail setup if not already present.

## Tests

Add frontend tests if the project has test infrastructure.

Tests should prove:

1. Application card/detail shows email status.
2. Gmail not connected state shows Connect Gmail action.
3. Check Gmail action calls search endpoint.
4. Candidate emails render subject/from/snippet/matched signals.
5. Candidate email does not render full body.
6. Classify action calls classification endpoint.
7. Classification result renders label/confidence/reason/evidence.
8. Rejection/interview/assessment labels are explicit text, not color-only.
9. Privacy note is visible.
10. Errors render useful messages.

Add/update backend tests only if endpoint response shape needs minor compatibility changes.

## Acceptance Criteria

- Applications UI shows Gmail/email tracking state.
- User can initiate Gmail search from the UI.
- User can classify candidate emails from the UI.
- Candidate email metadata/snippets are displayed.
- Classification evidence is displayed.
- Application status refreshes after classification.
- UI includes read-only Gmail privacy note.
- No Gmail write actions are added.
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

Run backend tests if API shape changed:

```bash
pytest
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Open Applications page.
4. Confirm each application shows email status.
5. If Gmail is disconnected, confirm Connect Gmail appears.
6. Connect Gmail using the existing OAuth flow.
7. Click Check Gmail for an application.
8. Confirm candidate email cards appear.
9. Click Classify.
10. Confirm classification/evidence appears.
11. Confirm no full email body appears.
12. Confirm no send/delete/archive/label actions exist.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Gmail evidence to applications UI
```

Do not push.
