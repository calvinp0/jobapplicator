# Task 084: Classify Gmail Application Emails with Evidence

## Goal

Add deterministic/LLM-assisted classification for Gmail emails that were matched to job applications by Task 083.

This task should classify candidate emails into application-relevant categories and store visible evidence.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Task 080 added the Gmail email status model.

Task 082 added read-only Gmail OAuth.

Task 083 added Gmail search for application-related candidate emails.

Now the app needs to classify matched emails into categories such as:

```text
submission_confirmation
rejection
interview_request
recruiter_followup
assessment
offer
application_update
newsletter_or_unrelated
unknown
```

Classification must be evidence-based and conservative.

The app should never silently mark an application rejected/interview/offer without visible evidence.

## Inspect

Inspect:

```text
backend/app/
backend/tests/
frontend/src/api/
frontend/src/pages/
docs/contracts/gmail_integration.md
agent_tasks/queue.yaml
```

Search for:

```bash
rg "gmail|email_status|classification|application|status|matched_email" backend frontend docs
```

Use the existing project route/model style.

## Required Classification Labels

Use these labels unless Task 080 already defined equivalent names:

```text
submission_confirmation
rejection
interview_request
recruiter_followup
assessment
offer
application_update
newsletter_or_unrelated
unknown
```

Meanings:

```text
submission_confirmation
  Confirms an application was received/submitted.

rejection
  States the applicant will not proceed, was not selected, or the role is closed for them.

interview_request
  Requests scheduling, interview availability, phone screen, recruiter call, or next conversation.

recruiter_followup
  Recruiter/hiring team follow-up that is positive or requires response but is not clearly an interview.

assessment
  Requests coding challenge, take-home task, assessment, questionnaire, or technical screen task.

offer
  Indicates offer, selection, or approval.

application_update
  Generic status update, application under review, still considering, delay notice.

newsletter_or_unrelated
  Looks related by search terms but is not about this application.

unknown
  Insufficient evidence to classify.
```

## Classification Method

Implement a conservative classifier.

Use deterministic phrase/rule matching first.

Optional LLM classification may be added only if the project already has a safe internal LLM provider abstraction and tests can mock it.

Do not require real LLM calls in tests.

### Deterministic Signals

Examples of rejection phrases:

```text
not moving forward
will not be moving forward
unfortunately
decided not to proceed
not selected
pursue other candidates
unable to offer
position has been filled
role has been filled
application was unsuccessful
```

Examples of interview phrases:

```text
schedule an interview
schedule a call
phone screen
technical interview
interview availability
meet with
next step
speak with
chat with our team
```

Examples of assessment phrases:

```text
assessment
coding challenge
take-home
take home
technical exercise
assignment
questionnaire
test
HackerRank
CodeSignal
```

Examples of confirmation phrases:

```text
application received
thank you for applying
we received your application
your application has been submitted
successfully submitted
```

Examples of offer phrases:

```text
offer
pleased to offer
congratulations
selected for the role
would like to extend
```

Examples of neutral update phrases:

```text
under review
reviewing your application
still reviewing
update on your application
we will be in touch
```

The classifier should be case-insensitive.

## Evidence Requirements

Each classification result must include:

```json
{
  "classification": "rejection",
  "confidence": 0.86,
  "evidence": [
    {
      "field": "snippet",
      "text": "unfortunately, we will not be moving forward",
      "reason": "contains rejection phrase"
    }
  ],
  "reason": "Matched rejection phrase in email snippet"
}
```

Evidence text should be short.

Do not store full email bodies.

Use subject/from/snippet/date only in this task unless Task 083 already safely fetches body excerpts.

## Precedence Rules

If multiple labels match, use a conservative precedence order:

```text
offer
interview_request
assessment
rejection
submission_confirmation
recruiter_followup
application_update
newsletter_or_unrelated
unknown
```

But avoid false positives.

For example:

```text
"Unfortunately, we need to reschedule your interview"
```

should not be classified as rejection solely because it contains "unfortunately".

Add specific tests for ambiguous cases.

## Application Status Update Rules

After classification, update email tracking fields and, where appropriate, application status.

Mapping:

```text
submission_confirmation:
  email_status = confirmation_found
  submission_status = submitted
  application.status = pending unless already interview/approved/rejected

rejection:
  email_status = classified_rejection
  application.status = rejected

interview_request:
  email_status = classified_interview
  application.status = interview

recruiter_followup:
  email_status = classified_interview
  application.status = interview or pending depending existing model

assessment:
  email_status = classified_assessment
  application.status = pending
  next_action should indicate assessment/action required if supported

offer:
  email_status = classified_offer
  application.status = approved

application_update:
  email_status = classified_neutral
  application.status = pending unless already terminal

newsletter_or_unrelated:
  email_status = needs_review or no_match
  application.status unchanged

unknown:
  email_status = needs_review
  application.status unchanged
```

Do not override terminal statuses unless the new classification is clearly higher priority and evidence-backed.

Terminal statuses:

```text
rejected
approved
withdrawn
```

If an application is already withdrawn, do not auto-change it.

## Backend API Requirements

Add endpoint following project route style.

Suggested endpoint:

```text
POST /api/applications/{application_id}/gmail/classify
```

Request:

```json
{
  "message_id": "optional specific message id",
  "classify_top_candidate": true
}
```

Behavior:

```text
- If message_id is provided, classify that matched email.
- Else classify the top candidate from the most recent Gmail search if stored.
- If no candidate is available, return a clear error.
```

If Task 083 did not persist candidates, this endpoint may accept candidate metadata directly:

```json
{
  "candidate": {
    "message_id": "...",
    "subject": "...",
    "from": "...",
    "date": "...",
    "snippet": "..."
  }
}
```

Prefer the existing architecture.

Response:

```json
{
  "application_id": "...",
  "message_id": "...",
  "classification": "rejection",
  "confidence": 0.86,
  "email_status": "classified_rejection",
  "application_status": "rejected",
  "evidence": [
    {
      "field": "snippet",
      "text": "not moving forward",
      "reason": "contains rejection phrase"
    }
  ],
  "reason": "Matched rejection phrase in email snippet"
}
```

## Bulk Classification Option

If easy, add endpoint or request option to classify all current candidates:

```json
{
  "classify_all_candidates": true
}
```

Return sorted results by confidence.

If too large, leave bulk classification for a later task.

## Frontend Requirements

Add minimal UI only if Task 083 added Gmail candidate display.

Suggested behavior:

```text
Candidate email card:
  Subject
  From
  Date
  Snippet
  Match score
  Classify button

After classification:
  Label badge
  Confidence
  Evidence
  Suggested application status
  Apply/Accept status change if not automatically applied
```

If backend automatically updates application status, the UI must show evidence.

If frontend work is too large, expose backend API and document manual curl verification.

Do not show full email bodies.

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
No background polling.
Store only metadata/snippets/evidence.
Every status change must have evidence.
```

## Documentation

Update:

```text
docs/contracts/gmail_integration.md
```

Add:

```text
classification labels
deterministic phrase matching
confidence scoring
evidence format
application status update mapping
ambiguous cases
privacy constraints
```

Document that classification is conservative and evidence-based.

## Tests

Use mocked candidate email metadata.

Tests must not hit real Gmail.

Add or update tests to prove:

1. Rejection phrase classifies as `rejection`.
2. Interview phrase classifies as `interview_request`.
3. Assessment phrase classifies as `assessment`.
4. Submission confirmation phrase classifies as `submission_confirmation`.
5. Offer phrase classifies as `offer`.
6. Neutral update phrase classifies as `application_update`.
7. Unrelated/newsletter email classifies as `newsletter_or_unrelated` or `unknown`.
8. Ambiguous phrase such as "unfortunately, we need to reschedule your interview" is not classified as rejection.
9. Classification includes confidence.
10. Classification includes evidence.
11. Evidence uses subject/from/snippet only, not full body.
12. Rejection updates email_status and application status appropriately.
13. Interview updates email_status and application status appropriately.
14. Assessment updates email_status but does not mark approved/rejected.
15. Withdrawn applications are not auto-changed.
16. Tests do not require Gmail network calls.
17. No Gmail write scopes or operations are used.

If frontend UI is added, add tests if frontend test infrastructure exists.

## Acceptance Criteria

- Matched Gmail emails can be classified.
- Classification is conservative and evidence-based.
- Classification results include label, confidence, reason, and evidence.
- Application/email statuses update according to documented mapping.
- No full email bodies are stored.
- No Gmail write operations are implemented.
- Tests pass.

## Verification

Run:

```bash
pytest
```

If frontend changed:

```bash
cd frontend && npm run build
```

Manual verification with real Gmail connection:

1. Connect Gmail using Task 082 flow.
2. Search application emails using Task 083 endpoint.
3. Classify a candidate email:

```bash
curl -X POST http://localhost:8000/api/applications/<application_id>/gmail/classify \
  -H "Content-Type: application/json" \
  -d '{"classify_top_candidate":true}'
```

or with direct candidate metadata if implemented:

```bash
curl -X POST http://localhost:8000/api/applications/<application_id>/gmail/classify \
  -H "Content-Type: application/json" \
  -d '{
    "candidate": {
      "message_id": "test",
      "subject": "Application update",
      "from": "jobs@example.com",
      "date": "2026-05-25",
      "snippet": "Unfortunately, we will not be moving forward."
    }
  }'
```

4. Confirm response includes:

```text
classification
confidence
evidence
reason
email_status
application_status
```

5. Confirm no full email body is returned.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Classify Gmail application emails
```

Do not push.
