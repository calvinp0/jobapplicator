# Task 096: Prefill and Simplify Manual Gmail Linking UI

## Goal

Fix the Gmail manual linking UI so candidate email link actions use the selected Gmail candidate metadata automatically.

Current observed issue:

```text
User clicks "Link as confirmation" on a Gmail candidate.
Email evidence appears with the linked candidate.
But the lower "Record email" form remains blank/default with a generated manual message id.
```

This is confusing.

When linking a Gmail candidate, the app should automatically use that candidate's:

```text
message id
thread id
sender
subject
snippet
received date
match score
classification guess
selected classification
```

The manual "Record email" form should be reserved for emails that were not found through Gmail.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Task 093 added manual Gmail email linking.

The intended flow is:

```text
Candidate Gmail email appears
  ↓
User clicks Link as confirmation/rejection/interview/assessment/update
  ↓
Backend stores exact Gmail message/thread ID and metadata
  ↓
Email evidence updates
```

The user should not need to retype sender, subject, or received date after selecting a Gmail candidate.

The manual Record Email form should exist only for cases where Gmail is unavailable or the user wants to record evidence by hand.

## Inspect

Inspect:

```text
frontend/src/pages/
frontend/src/components/
frontend/src/api/
frontend/src/test/
backend/app/
backend/tests/
docs/contracts/gmail_integration.md
agent_tasks/queue.yaml
```

Search:

```bash
rg "Link as confirmation|Link as rejection|Record email|manual:|linked email|gmail candidate|link-email" frontend backend docs
```

Use the existing project structure.

## Required UI Behavior

### Candidate Link Buttons

For each candidate email card, buttons like:

```text
Link as confirmation
Link as rejection
Link as interview
Link as assessment
Link as neutral/update
Not related
```

should call the backend link-email endpoint directly using the selected candidate metadata.

Request should include:

```json
{
  "message_id": "<candidate.message_id>",
  "thread_id": "<candidate.thread_id>",
  "classification": "submission_confirmation",
  "sender": "<candidate.from>",
  "subject": "<candidate.subject>",
  "snippet": "<candidate.snippet>",
  "received_at": "<candidate.date>",
  "match_score": "<candidate.match_score>",
  "matched_signals": ["..."],
  "user_confirmed": true
}
```

Use actual backend field names.

Do not create a fake `manual:<uuid>` message ID for Gmail candidates.

After successful link:

```text
- refresh linked email evidence
- refresh application status/email status
- show a success message
- remove or mark the candidate as linked
```

### Manual Record Form

The lower "Record email" form should be clearly labeled:

```text
Record email manually
```

Add helper text:

```text
Use this only if the email was not found through Gmail search.
```

It should not appear as the next step after clicking a Gmail candidate link.

If Gmail candidates exist, place the manual form below a collapsed section:

```text
Record email manually
```

or visually separate it.

## Prefill Option

If the project intentionally wants review-before-save behavior, implement it consistently:

```text
Click "Use this email"
  ↓
Record form is prefilled with candidate metadata
  ↓
User confirms "Record linked email"
```

But do not mix immediate linking with a blank form.

Preferred behavior for this task:

```text
Candidate link buttons save immediately.
Manual form is only for non-Gmail/manual evidence.
```

## Evidence Display Requirements

Linked evidence should show:

```text
Subject
Sender
Classification
Received date
Snippet/evidence
Linked manually or linked from Gmail
Unlink button
```

If linked from a Gmail candidate but confirmed by user, show:

```text
Linked from Gmail · confirmed manually
```

If recorded with the manual form, show:

```text
Recorded manually
```

Do not show raw message IDs prominently unless needed for debug.

## Backend Requirements

Ensure link-email endpoint distinguishes:

```text
match_method = manual_candidate_link
```

or equivalent for Gmail candidate manually confirmed.

Use:

```text
linked_by_user = true
source = gmail
```

For the manual Record Email form, use:

```text
source = manual
match_method = manual_entry
message_id = manual:<uuid>
```

Do not use `manual:<uuid>` for actual Gmail candidates.

If existing backend currently overwrites candidate message IDs with manual IDs, fix that.

## Not Related Behavior

Clicking:

```text
Not related
```

should mark the candidate as dismissed for that application if a candidate-dismissal model exists.

If no dismissal model exists, it may simply hide the candidate in frontend state for the current page session.

Do not delete or modify Gmail.

A future task can persist dismissed candidates.

## Frontend Error Handling

If link fails, show:

```text
Could not link this email. Try again.
```

Do not clear candidate data on failure.

## Tests

Add/update frontend tests if infrastructure exists:

1. Candidate "Link as confirmation" sends candidate message_id, not `manual:<uuid>`.
2. Candidate "Link as rejection" sends candidate sender/subject/snippet/date.
3. Candidate link action calls backend directly.
4. Candidate link success refreshes email evidence.
5. Manual Record Email form remains for manual entry only.
6. Manual Record Email form helper text says it is for emails not found through Gmail.
7. Manual form uses `manual:<uuid>` only for manual entries.
8. Linked Gmail evidence shows "Linked from Gmail" or equivalent.
9. Raw message ID is not the primary displayed label.
10. Link failure shows useful error.

Add/update backend tests:

1. Link-email endpoint preserves Gmail candidate message_id.
2. Link-email endpoint preserves thread_id.
3. Link-email endpoint stores sender/subject/snippet/date from request.
4. Link-email endpoint sets linked_by_user=true.
5. Gmail candidate link does not generate `manual:<uuid>`.
6. Manual entry still can generate `manual:<uuid>`.
7. No Gmail write operations are used.

## Acceptance Criteria

- Clicking a Gmail candidate link button records the selected candidate metadata automatically.
- User does not need to retype sender/subject/date/snippet for a candidate.
- Gmail candidate links preserve real Gmail message/thread IDs.
- `manual:<uuid>` is used only for truly manual entries.
- Manual Record Email form is visually separated and clearly explained.
- Linked evidence display distinguishes Gmail candidate links from manual entries.
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
2. Open an application.
3. Search Gmail and display candidates.
4. Click:

```text
Link as confirmation
```

5. Confirm linked evidence appears with:
   - candidate subject
   - candidate sender
   - candidate snippet
   - classification confirmation
   - Gmail source / manually confirmed label
6. Confirm the Record Email form is not blank as if it needs re-entry.
7. Confirm no `manual:<uuid>` is used for the Gmail candidate.
8. Use the manual form separately and confirm manual entries still work.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Prefill Gmail manual linking UI
```

Do not push.
