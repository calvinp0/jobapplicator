# Task 086: Add Manual Gmail Sync for Applications

## Goal

Add a manual Gmail sync action that checks Gmail for all relevant applications and updates their email tracking/classification state.

This should be user-triggered only.

Do not implement background polling.  
Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Task 080 added the Gmail email status model.

Task 082 added Gmail read-only OAuth connection.

Task 083 added Gmail search for application-related emails.

Task 084 added Gmail email classification with evidence.

Task 085 added Gmail evidence to the Applications UI.

Now the user needs a higher-level workflow:

```text
Applications page
  ↓
Click "Sync Gmail"
  ↓
Search relevant applications
  ↓
Classify top matched emails
  ↓
Update application email statuses
  ↓
Show summary
```

This task should reduce the need to open each application and manually check Gmail one by one.

## Inspect

Inspect:

```text
backend/app/
backend/tests/
frontend/src/api/
frontend/src/pages/
frontend/src/components/
docs/contracts/gmail_integration.md
agent_tasks/queue.yaml
```

Search for:

```bash
rg "gmail|email_status|classify|application|submitted|sync" backend frontend docs
```

Use the existing project style.

## Sync Scope

Manual sync should consider applications that are likely relevant.

Include applications with statuses such as:

```text
submitted
waiting_for_email
email_received
pending
interview
ready_to_submit if explicitly marked as watching
```

Exclude by default:

```text
draft
rejected
approved
withdrawn
error
```

Do not sync archived/terminal applications unless a request option explicitly includes them.

If the existing status model differs, map to the closest equivalent.

## Backend API Requirements

Add an endpoint following project route style.

Suggested endpoint:

```text
POST /api/gmail/sync-applications
```

Request:

```json
{
  "max_applications": 25,
  "max_results_per_application": 10,
  "classify": true,
  "include_terminal": false
}
```

Response:

```json
{
  "gmail_connected": true,
  "checked_count": 5,
  "updated_count": 2,
  "no_match_count": 3,
  "needs_review_count": 1,
  "results": [
    {
      "application_id": "...",
      "job_title": "...",
      "company": "...",
      "previous_email_status": "watching",
      "new_email_status": "classified_rejection",
      "previous_application_status": "pending",
      "new_application_status": "rejected",
      "matched_email_count": 1,
      "classification": "rejection",
      "confidence": 0.86,
      "evidence": [
        {
          "field": "snippet",
          "text": "not moving forward",
          "reason": "contains rejection phrase"
        }
      ]
    }
  ]
}
```

If Gmail is not connected:

```json
{
  "gmail_connected": false,
  "message": "Connect Gmail before syncing applications"
}
```

Do not start OAuth from this endpoint.

## Sync Behavior

For each included application:

```text
1. Build Gmail query using Task 083 query builder.
2. Search Gmail read-only.
3. If no candidates:
   - update email_status to no_match or keep watching depending existing model
   - update last_gmail_check_at
4. If candidates found:
   - store/update candidate metadata summary
   - if classify=true, classify top candidate or candidates
   - update email_status and application status according to Task 084 mapping
5. Record evidence.
```

Classification should remain conservative.

Do not override terminal statuses unless:

```text
include_terminal=true
```

and the code explicitly documents the behavior.

Do not auto-change withdrawn applications.

## Rate/Limit Requirements

Add safe caps:

```text
max_applications <= 50
max_results_per_application <= 10
```

Default:

```text
max_applications = 25
max_results_per_application = 10
```

The endpoint should process applications deterministically, sorted by:

```text
updated_at descending
```

or by applications needing attention first if that already exists.

## Frontend Requirements

Add a manual sync control to the Applications page.

Suggested UI:

```text
[Sync Gmail]
```

When clicked:

```text
- call POST /api/gmail/sync-applications
- show loading state
- show summary:
  Checked 5 applications
  Updated 2
  No match 3
  Needs review 1
- refresh applications list
```

Show per-application results if practical:

```text
Example Aero Labs — Rejected
Evidence: "not moving forward"
```

If Gmail is not connected, show:

```text
Connect Gmail before syncing applications.
```

and provide the existing Connect Gmail action if available.

## Privacy and Safety Requirements

Enforce:

```text
Read-only Gmail usage only.
No sending.
No deleting.
No archiving.
No labeling.
No modifying.
No full email bodies.
Manual user-triggered sync only.
Every status change must have evidence.
```

## Documentation

Update:

```text
docs/contracts/gmail_integration.md
```

Add:

```text
manual sync behavior
included/excluded application statuses
sync endpoint
rate limits
result summary format
privacy constraints
why background sync is deferred
```

Document that background polling should be a future task after manual sync is stable.

## Tests

Use mocked Gmail client responses.

Tests must not hit real Gmail.

Add/update backend tests to prove:

1. Sync endpoint requires Gmail connection.
2. Sync includes submitted/pending/watching applications.
3. Sync excludes draft applications by default.
4. Sync excludes rejected/approved/withdrawn applications by default.
5. `include_terminal=true` can include terminal statuses if implemented.
6. Sync caps max_applications.
7. Sync caps max_results_per_application.
8. No-match result updates last_gmail_check_at and email status appropriately.
9. Matched/classified rejection updates status with evidence.
10. Matched/classified interview updates status with evidence.
11. Withdrawn applications are not auto-changed.
12. Response includes checked/updated/no-match/needs-review counts.
13. No full email bodies are returned or stored.
14. No Gmail write operations are used.
15. Tests do not require real Google credentials.

Add frontend tests if the project has test infrastructure:

1. Sync Gmail button appears.
2. Clicking Sync Gmail calls sync endpoint.
3. Loading state appears.
4. Summary counts render.
5. Gmail disconnected message renders.
6. Applications refresh after sync.

## Acceptance Criteria

- User can manually sync Gmail across relevant applications.
- Sync searches and classifies matched emails using existing Gmail logic.
- Sync returns a clear summary.
- Applications UI exposes Sync Gmail action.
- Terminal applications are excluded by default.
- Status changes include evidence.
- No Gmail write operations exist.
- No background polling is implemented.
- Tests pass.

## Verification

Run:

```bash
pytest
cd frontend && npm run build
```

If frontend tests exist:

```bash
cd frontend && npm test -- --run
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Connect Gmail.
4. Open Applications page.
5. Click Sync Gmail.
6. Confirm summary appears.
7. Confirm applications refresh.
8. Confirm updated statuses show evidence.
9. Confirm no send/delete/archive/label actions exist.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add manual Gmail sync for applications
```

Do not push.
