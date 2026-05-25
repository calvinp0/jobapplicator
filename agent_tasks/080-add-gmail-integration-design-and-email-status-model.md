# Task 080: Add Gmail Integration Design and Email Status Model

## Goal

Prepare JobApplicator for Gmail-based application tracking by adding a clear email status model, documentation, and backend data structures.

This task should not connect to Gmail yet.

Do not implement Gmail OAuth in this task.
Do not read real emails in this task.
Do not send emails.
Do not archive, delete, label, or modify emails.
Do not implement LinkedIn automation.
Do not change Claude tailoring behavior.

## Background

The Applications dashboard needs to show more than a generic status such as:

```text
Draft
```

Users need to know whether an application is:

```text
submitted
waiting for confirmation
confirmed by email
rejected
interviewing
pending
needs review
```

Gmail integration should eventually help detect these states by matching incoming emails to applications.

Before connecting Gmail, define the application-email model and lifecycle.

## Required Email Status Model

Add or document an email tracking state for applications.

Use these states unless the existing project already has equivalent names:

```text
not_watching
watching
confirmation_found
email_received
needs_review
classified_rejection
classified_interview
classified_assessment
classified_offer
classified_neutral
no_match
error
```

Meanings:

```text
not_watching
  No Gmail tracking is enabled for this application.

watching
  Gmail tracking is enabled and waiting for matching emails.

confirmation_found
  A submission confirmation email was found.

email_received
  A potentially related email was found but has not been classified.

needs_review
  A related email was found but classification is uncertain.

classified_rejection
  A rejection email was detected.

classified_interview
  An interview or recruiter follow-up email was detected.

classified_assessment
  An assessment, test, coding challenge, or action-required email was detected.

classified_offer
  A positive offer/approval email was detected.

classified_neutral
  A related but non-decisive update was detected.

no_match
  Gmail was checked but no related email was found.

error
  Gmail search/classification failed.
```

## Data Model Requirements

Persist or expose fields similar to:

```json
{
  "email_status": "not_watching",
  "gmail_query": null,
  "last_gmail_check_at": null,
  "last_matched_email_at": null,
  "matched_email_count": 0,
  "latest_email_subject": null,
  "latest_email_from": null,
  "latest_email_snippet": null,
  "latest_email_classification": null,
  "latest_email_confidence": null,
  "latest_email_evidence": null
}
```

If the project uses a database, add a migration.

If the project uses JSON/file state, update that contract.

Preserve backwards compatibility for existing applications.

Existing applications should default to:

```text
email_status = not_watching
matched_email_count = 0
```

## Email Classification Labels

Document these future classification labels:

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

## Matching Signals

Document the future Gmail matching signals:

```text
company name
job title
ATS name if known
sender email/domain
submitted_at timestamp
subject line
email body/snippet
known phrases
manual user-provided search terms
```

Examples:

```text
Company: Example Aero Labs
Job title: Scientific Machine Learning Engineer

Possible Gmail query:
("Example Aero Labs" OR "Scientific Machine Learning Engineer") newer_than:90d
```

Do not implement Gmail search yet in this task.

## Application Status Interaction

Document how email status should affect application status later:

```text
submission_confirmation
  application.status = pending
  application.submission_status = submitted
  email_status = confirmation_found

rejection
  application.status = rejected
  email_status = classified_rejection

interview_request or recruiter_followup
  application.status = interview
  email_status = classified_interview

assessment
  application.status = pending
  next_action = complete assessment
  email_status = classified_assessment

unknown but related
  application.status unchanged
  email_status = needs_review
```

Do not automatically change application status in this task unless the current code requires derived fields.

## Privacy and Safety Requirements

Document Gmail integration principles:

```text
Use read-only access first.
Never send emails in the Gmail tracking flow.
Never delete, archive, label, or modify emails in the first Gmail implementation.
Store only the minimum email metadata needed for tracking.
Store evidence snippets, not full email bodies, unless explicitly needed.
Let the user review uncertain matches.
Every automatic status change should have visible evidence.
```

## Backend Requirements

Add helper functions or model fields where appropriate.

Suggested helpers:

```text
get_email_status(application)
set_email_status(application, status)
build_default_gmail_tracking_state()
derive_next_action_from_email_status()
```

Use existing project style.

## API Requirements

If there is an application detail/list API, ensure it can expose:

```text
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

If API work is too large for this task, document the desired response shape and add backend model support first.

## Documentation

Create or update:

```text
docs/contracts/gmail_integration.md
```

Include:

```text
Gmail integration goals
Non-goals
Email status lifecycle
Classification labels
Matching signals
Application status interaction
Privacy rules
Future task breakdown
```

## Tests

Add or update tests to prove:

1. New applications default to `email_status=not_watching`.
2. Existing/backwards-compatible application data without email fields still loads.
3. Valid email statuses are accepted.
4. Invalid email statuses are rejected.
5. API/application serialization includes email status fields if applicable.
6. Derived next action can mention Gmail state when relevant.
7. No Gmail network/API calls occur in tests.
8. No email send/delete/archive/label behavior exists in this task.

## Acceptance Criteria

- Gmail email status model exists or is documented.
- Existing applications default to `not_watching`.
- Gmail tracking fields are backwards compatible.
- Privacy/safety rules are documented.
- Future Gmail classification labels are documented.
- No real Gmail connection is implemented yet.
- Tests pass.

## Verification

Run:

```bash
pytest
```

If frontend build is affected:

```bash
cd frontend
npm run build
```

Manual verification:

1. Start backend.
2. Open Applications page or application API response.
3. Confirm applications expose/default email status as:

```text
not_watching
```

4. Confirm no Gmail connection is attempted.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Gmail email status model
```

Do not push.
