# Task 093: Add Manual Gmail Email Linking for Applications

## Goal

Improve Gmail application tracking so users can manually confirm/link a Gmail message to an application when automatic matching misses or has low confidence.

Current observed issue:

```text
Application: Graduates — InfinityLabs R&D
Gmail tracking says: Gmail: No related emails found
```

But Gmail contains a clear related email:

```text
From: Infinity Labs R&D
Subject: Thank you for contacting Infinity Labs R&D
Body: Thank you for applying to Infinity Labs R&D...
```

The matcher failed to link it. The UI should present candidate emails and allow the user to confirm:

```text
Yes, this email belongs to this application
```

The backend should then record the exact Gmail message/thread ID and evidence.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

The existing Gmail flow includes:

```text
Gmail read-only OAuth
application email search
classification
Gmail evidence UI
manual sync
```

However, automatic matching can fail because companies use unexpected sender names, job titles differ, emails are generic, or subjects do not exactly match the application record.

Therefore, the system needs a manual linking workflow.

Correct behavior:

```text
1. Search Gmail for candidates.
2. Show high-confidence matches.
3. Also show low-confidence possible matches when no high-confidence match exists.
4. Let the user manually link one or more emails to the application.
5. Store the linked Gmail message ID/thread ID.
6. Classify or allow manual classification.
7. Display linked email evidence on the application page.
```

## Inspect

Inspect:

```text
backend/app/
backend/tests/
frontend/src/api/
frontend/src/pages/
frontend/src/components/
frontend/src/test/
docs/contracts/gmail_integration.md
agent_tasks/queue.yaml
```

Search:

```bash
rg "gmail|email_status|matched_email|classification|message_id|thread_id|application" backend frontend docs
```

Use the existing project architecture.

## Required Behavior

When Gmail search finds no high-confidence match, the UI should not simply say:

```text
No related emails found
```

Instead, it should offer:

```text
No strong match found.
Review possible Gmail emails.
```

Then show candidate emails from a broader search.

Example broader search strategies:

```text
company name only
company domain if known
job title keywords
recent emails after submitted_at
ATS keywords
manual search query entered by user
```

The user should be able to click:

```text
Link this email
```

or:

```text
This is the application confirmation
This is a rejection
This is an interview/update
Not related
```

## Backend Data Model Requirements

Persist linked Gmail evidence for applications.

Use existing email evidence model if present.

At minimum store:

```json
{
  "application_id": "...",
  "gmail_message_id": "...",
  "gmail_thread_id": "...",
  "classification": "submission_confirmation",
  "sender": "hr@infinitylabs.co.il",
  "subject": "Thank you for contacting Infinity Labs R&D",
  "snippet": "Thank you for applying to Infinity Labs R&D...",
  "received_at": "...",
  "match_score": 0.42,
  "match_method": "manual",
  "linked_by_user": true,
  "evidence": [
    {
      "field": "snippet",
      "text": "Thank you for applying to Infinity Labs R&D",
      "reason": "User manually confirmed this email belongs to the application"
    }
  ],
  "created_at": "..."
}
```

Do not store full email bodies.

Do not store OAuth tokens in this model.

## Backend API Requirements

Add endpoints following current route style.

Suggested endpoints:

```text
POST /api/applications/{application_id}/gmail/candidates
POST /api/applications/{application_id}/gmail/link-email
GET  /api/applications/{application_id}/gmail/linked-emails
DELETE /api/applications/{application_id}/gmail/linked-emails/{linked_email_id}
```

Use actual route conventions.

### Candidate Search Endpoint

Request:

```json
{
  "query": "optional manual query",
  "max_results": 20,
  "include_low_confidence": true
}
```

Behavior:

```text
- If query is provided, use it directly or combine with safe date filters.
- If no query is provided, run broader candidate searches.
- Return candidates with metadata/snippets only.
- Include match score and matched signals.
```

Response:

```json
{
  "application_id": "...",
  "query_used": "...",
  "candidates": [
    {
      "message_id": "...",
      "thread_id": "...",
      "subject": "Thank you for contacting Infinity Labs R&D",
      "from": "Infinity Labs R&D <hr@infinitylabs.co.il>",
      "date": "2026-05-25T20:01:00Z",
      "snippet": "Thank you for applying to Infinity Labs R&D...",
      "match_score": 0.42,
      "matched_signals": ["company_name_partial"],
      "classification_guess": "submission_confirmation"
    }
  ]
}
```

### Link Email Endpoint

Request:

```json
{
  "message_id": "...",
  "thread_id": "...",
  "classification": "submission_confirmation",
  "sender": "Infinity Labs R&D <hr@infinitylabs.co.il>",
  "subject": "Thank you for contacting Infinity Labs R&D",
  "snippet": "Thank you for applying to Infinity Labs R&D...",
  "received_at": "2026-05-25T20:01:00Z",
  "match_score": 0.42,
  "user_confirmed": true
}
```

Behavior:

```text
- Validate the application exists.
- Validate Gmail is connected if message metadata must be refreshed.
- Store the linked email.
- Mark match_method=manual.
- Update application email tracking summary.
- Apply classification status mapping if classification is provided.
- Do not modify Gmail.
```

If classification is omitted, use:

```text
needs_review
```

or run existing classifier on the candidate metadata.

### Linked Emails Endpoint

Return all linked Gmail evidence for the application.

### Unlink Endpoint

Allow removing a manually linked email from the application.

Unlinking should not delete or modify the Gmail email.

If unlinking removes the only linked evidence, application email status should be recomputed or set to:

```text
needs_review
```

or previous safe state.

## Matching Changes

Adjust Task 083 search behavior:

```text
- Return low-confidence candidates when no strong match exists.
- Do not claim "No related emails found" if low-confidence candidates exist.
- Use a threshold system:
  strong_match >= 0.70
  possible_match >= 0.25
  below 0.25 = hidden unless user searches manually
```

If no strong matches but possible matches exist, set:

```text
email_status = needs_review
matched_email_count = possible candidate count
```

Do not set:

```text
no_match
```

until both strong and possible searches are empty.

## Frontend Requirements

Update application Gmail UI.

If Gmail is connected, show:

```text
Check Gmail
Review possible emails
Manual search query
```

Candidate card should show:

```text
Subject
From
Date
Snippet
Match score
Matched signals
Classification guess
Actions:
  Link as confirmation
  Link as rejection
  Link as interview
  Link as assessment
  Link as neutral/update
  Not related
```

If the user clicks a link action:

```text
- call link-email endpoint
- refresh application detail
- show linked email under Email evidence
```

## UI Copy

Replace:

```text
Gmail: No related emails found
```

with more nuanced states:

```text
No strong Gmail match found.
Possible related emails are available for review.
```

or:

```text
No related Gmail emails found.
Try a manual Gmail search.
```

Add a manual search input:

```text
Search Gmail manually
```

Example user query:

```text
Infinity Labs
```

## Application Status Mapping

Manual classification should update application/email statuses:

```text
submission_confirmation:
  email_status = confirmation_found
  application.status = pending or submitted
  submission_status = submitted

rejection:
  email_status = classified_rejection
  application.status = rejected

interview_request:
  email_status = classified_interview
  application.status = interview

assessment:
  email_status = classified_assessment
  application.status = pending

application_update:
  email_status = classified_neutral
  application.status = pending unless terminal

unknown:
  email_status = needs_review
  application.status unchanged
```

Do not override withdrawn applications.

If the application is already rejected/approved, manual linking should not change it unless the user explicitly confirms status change.

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
Store metadata/snippets/evidence only.
Manual linking records user confirmation.
```

## Documentation

Update:

```text
docs/contracts/gmail_integration.md
```

Add:

```text
manual email linking
candidate thresholds
low-confidence candidate review
manual Gmail search
linked email evidence model
unlink behavior
privacy constraints
```

## Tests

Use mocked Gmail candidate metadata.

Backend tests:

1. Candidate search returns strong matches.
2. Candidate search returns possible low-confidence matches.
3. No strong match but possible matches sets `email_status=needs_review`, not `no_match`.
4. True no matches sets `email_status=no_match`.
5. Link-email endpoint stores message_id/thread_id.
6. Link-email endpoint stores match_method=manual.
7. Link-email endpoint stores linked_by_user=true.
8. Link-email endpoint stores subject/from/snippet/date.
9. Link-email endpoint does not store full body.
10. Link as confirmation updates email/application status.
11. Link as rejection updates email/application status.
12. Link as interview updates email/application status.
13. Link as assessment updates email/application status.
14. Withdrawn applications are not auto-changed.
15. Linked emails endpoint returns stored evidence.
16. Unlink endpoint removes application-email association.
17. Unlink does not modify Gmail.
18. No Gmail write operations are used.
19. Tests do not require real Google credentials.

Frontend tests if infrastructure exists:

1. UI shows "No strong Gmail match found" when possible candidates exist.
2. Possible email candidates render.
3. Manual search input appears.
4. Link as confirmation button calls link endpoint.
5. Linked email appears under Email evidence.
6. "No related emails found" appears only when no strong or possible candidates exist.
7. UI never renders full email body.

## Acceptance Criteria

- Low-confidence Gmail candidates can be reviewed.
- User can manually link a Gmail email to an application.
- Backend stores exact Gmail message/thread ID.
- Backend stores evidence and user confirmation.
- Application/email status updates according to manual classification.
- UI supports manual search and manual linking.
- No Gmail write actions are added.
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

1. Connect Gmail.
2. Open an application where automatic search misses an obvious email.
3. Click Check Gmail.
4. If no strong match exists, confirm possible candidates appear.
5. Use manual query:

```text
Infinity Labs
```

6. Confirm the email appears.
7. Click:

```text
Link as confirmation
```

8. Confirm Email evidence shows the linked email.
9. Confirm Gmail tracking status changes from no_match to confirmation/linked.
10. Confirm application stores the exact message/thread ID.
11. Confirm Gmail itself is not modified.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add manual Gmail email linking
```

Do not push.
