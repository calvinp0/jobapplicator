# Task 083: Search Gmail for Application-Related Emails

## Goal

Add Gmail search functionality that can find emails related to a specific job application.

This task should use the read-only Gmail connection from Task 082.

Do not classify emails in this task.  
Do not automatically update application status in this task.  
Do not send emails.  
Do not archive, delete, label, or modify emails.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Task 080 added the Gmail email status model.

Task 082 added Gmail read-only OAuth connection and safe test search.

The next step is to search Gmail for messages that may relate to a specific application using signals such as:

```text
company name
job title
submitted_at timestamp
known ATS terms
manual search terms
sender domain if known
```

This task should only find and return candidate emails with match evidence.

Classification comes later.

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

Search for existing application/job models and Gmail client code:

```bash
rg "Application|application|Job|job|gmail|email_status|submitted_at" backend frontend docs
```

Use the project’s existing route/model style.

## Required Behavior

Add a backend function that builds a Gmail search query for an application.

The search should consider:

```text
company name
job title
application submitted_at date if available
manual extra search terms if provided
known ATS keywords
```

Known ATS keywords may include:

```text
greenhouse
lever
workday
ashby
smartrecruiters
icims
bamboohr
jobvite
recruitee
successfactors
```

Do not overfit this list. It is only a query aid.

## Query Builder Requirements

Create a query builder that produces a Gmail search query.

Example input:

```json
{
  "company": "Example Aero Labs",
  "job_title": "Scientific Machine Learning Engineer",
  "submitted_at": "2026-05-25T03:00:00Z"
}
```

Example query:

```text
("Example Aero Labs" OR "Scientific Machine Learning Engineer") newer_than:120d
```

If `submitted_at` exists, prefer a bounded date query:

```text
after:2026/5/24
```

Use a small pre-submission buffer, such as one day before submitted date.

If no `submitted_at` exists, use a recency window:

```text
newer_than:180d
```

The query builder should avoid generating invalid Gmail syntax.

## Matching Requirements

Search Gmail using the read-only client.

Return candidate emails with safe metadata only:

```json
{
  "message_id": "...",
  "thread_id": "...",
  "subject": "...",
  "from": "...",
  "date": "...",
  "snippet": "...",
  "matched_signals": [
    "company_name",
    "job_title"
  ],
  "match_score": 0.78,
  "gmail_query": "..."
}
```

Do not return full email bodies in this task.

Do not store full email bodies.

## Match Scoring

Add simple deterministic scoring.

Signals:

```text
company name appears in subject/snippet/from
job title appears in subject/snippet
sender domain resembles company domain if available
known ATS sender/domain appears
email date is after submitted_at
manual search term appears
```

Return:

```text
match_score
matched_signals
```

The scoring does not need to be perfect. It should be transparent and testable.

## Backend API Requirements

Add endpoint following project route style.

Suggested endpoint:

```text
POST /api/applications/{application_id}/gmail/search
```

or if applications are modeled differently:

```text
POST /api/jobs/{job_id}/gmail/search
```

Use the actual app model.

Request body:

```json
{
  "max_results": 10,
  "extra_terms": ["optional phrase"],
  "include_ats_terms": true
}
```

Response:

```json
{
  "application_id": "...",
  "gmail_connected": true,
  "gmail_query": "...",
  "count": 2,
  "candidates": [
    {
      "message_id": "...",
      "thread_id": "...",
      "subject": "...",
      "from": "...",
      "date": "...",
      "snippet": "...",
      "matched_signals": ["company_name"],
      "match_score": 0.65
    }
  ]
}
```

If Gmail is not connected, return a clear project-standard error or response:

```json
{
  "gmail_connected": false,
  "message": "Connect Gmail before searching for application emails"
}
```

Do not trigger OAuth from this endpoint.

## Application Email State Update

After a search completes, update only safe summary fields if the existing Task 080 model supports them:

```text
last_gmail_check_at
matched_email_count
email_status
```

Rules:

```text
if Gmail disconnected:
  do not change application email_status

if search succeeds and no matches:
  email_status = no_match

if search succeeds and matches exist:
  email_status = email_received
  matched_email_count = number of candidates
  latest_email_subject/from/snippet/date = top candidate metadata
```

Do not classify rejection/interview/etc. in this task.

Do not update application main status to rejected/interview/pending in this task.

## Frontend Requirements

Add minimal UI only if the Applications/Application Detail page already has a natural place for it.

Suggested minimal UI:

```text
Check Gmail
```

button on application detail/card.

When clicked:

```text
- calls application Gmail search endpoint
- shows number of possible related emails
- shows top candidate subject/from/snippet
- shows "Needs review" or "Email received" without final classification
```

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
User-triggered search only in this task.
```

## Documentation

Update:

```text
docs/contracts/gmail_integration.md
```

Add:

```text
application email search
query builder rules
matching signals
match scoring
API endpoint
privacy constraints
known limitations
```

Document that this task does not classify emails and does not make final application decisions.

## Tests

Use mocked Gmail client responses.

Tests must not hit real Gmail.

Add or update tests to prove:

1. Query builder includes company name.
2. Query builder includes job title.
3. Query builder uses submitted_at date when available.
4. Query builder falls back to `newer_than:180d` when no submitted_at exists.
5. Search endpoint requires Gmail connection.
6. Search endpoint caps max_results to a safe limit.
7. Search returns safe metadata only, not full body.
8. Matching returns matched_signals.
9. Matching returns deterministic match_score.
10. No matches update email_status to `no_match` if model supports it.
11. Matches update email_status to `email_received` if model supports it.
12. Main application status is not changed to rejected/interview/approved in this task.
13. No send/modify/delete/archive Gmail scopes or operations are used.
14. Tests do not require real Google credentials.

If frontend UI is added, add tests if frontend test infrastructure exists.

## Acceptance Criteria

- Backend can build Gmail search queries for applications.
- Backend can search Gmail read-only for candidate application emails.
- Search returns only safe metadata/snippets.
- Match signals and score are returned.
- Email tracking summary fields update if supported.
- No classification is performed.
- No main application outcome status is changed.
- No Gmail write operations exist.
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
2. Mark or use an application with company/job title.
3. Call the search endpoint:

```bash
curl -X POST http://localhost:8000/api/applications/<application_id>/gmail/search \
  -H "Content-Type: application/json" \
  -d '{"max_results":10,"include_ats_terms":true}'
```

4. Confirm response includes:

```text
gmail_query
candidates
matched_signals
match_score
```

5. Confirm no full email bodies are returned.
6. Confirm application status is not automatically set to rejected/interview/etc.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Gmail application email search
```

Do not push.
