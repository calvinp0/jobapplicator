# Task 082: Add Gmail Read-Only OAuth Connection

## Goal

Add the first real Gmail integration step: a read-only Gmail connection that can report whether Gmail is connected and can perform a safe test search.

This task should establish OAuth/config plumbing only.

Do not classify emails in this task.  
Do not match emails to applications in this task.  
Do not send emails.  
Do not archive, delete, label, or modify emails.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Task 080 added the Gmail integration design and email status model.

The intended Gmail flow is:

```text
Application submitted
  ↓
Gmail read-only connection
  ↓
Search for related emails
  ↓
Match email to application
  ↓
Classify email
  ↓
Update application status with evidence
```

This task only implements:

```text
Gmail connection status
OAuth/read-only setup
safe test search
backend API endpoints for connection state
documentation for setup
```

## Required Scope

Use Gmail read-only access only.

Required Gmail permission scope:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Do not request broader scopes such as:

```text
gmail.modify
gmail.send
mail.google.com
```

unless the project already has a documented reason. If broader scopes already exist, document why and do not expand them in this task.

## Inspect

Inspect:

```text
backend/app/
backend/tests/
frontend/src/api/
frontend/src/pages/
docs/contracts/gmail_integration.md
docs/install.md
README_INSTALL.md
agent_tasks/queue.yaml
```

Search for existing OAuth/auth patterns:

```bash
rg "oauth|google|gmail|credential|token|auth" backend frontend docs
```

Use the existing project style.

## Configuration Requirements

Add configuration for Gmail OAuth credentials.

Support environment variables such as:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
GMAIL_TOKEN_PATH
```

Use existing settings/config patterns if present.

Add or update `.env.example` if the project has one.

Do not commit real secrets.

If no `.env.example` exists, document expected variables in the install guide or Gmail docs instead.

## Token Storage Requirements

Store OAuth tokens locally in a development-safe way.

Acceptable for this task:

```text
candidate_context/gmail/token.json
```

or another existing app-data location.

Requirements:

```text
- Do not commit token files.
- Add token path to .gitignore if needed.
- Store refresh token only in local dev state.
- Document that this is local development storage, not production-grade secret management.
```

If the project already has a secure local settings storage pattern, use it.

## Backend API Requirements

Add backend endpoints following the project’s existing route style.

Suggested endpoints:

```text
GET  /api/gmail/status
GET  /api/gmail/auth-url
GET  /api/gmail/oauth/callback
POST /api/gmail/test-search
```

Use actual project route conventions.

### GET /api/gmail/status

Returns:

```json
{
  "connected": false,
  "email": null,
  "scopes": [],
  "token_path_configured": true,
  "last_checked_at": null
}
```

When connected:

```json
{
  "connected": true,
  "email": "user@example.com",
  "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "token_path_configured": true,
  "last_checked_at": "..."
}
```

If getting the email address requires an additional Google profile scope, do not add it in this task. Return `email: null` and document why.

### GET /api/gmail/auth-url

Returns a Google OAuth URL for user authorization.

Response shape:

```json
{
  "auth_url": "https://accounts.google.com/...",
  "scope": "https://www.googleapis.com/auth/gmail.readonly"
}
```

### GET /api/gmail/oauth/callback

Handles the OAuth callback and stores the token.

Use the existing framework style for redirects or JSON responses.

If frontend callback handling is not ready, return a simple page or JSON success response.

### POST /api/gmail/test-search

Performs a safe read-only test search.

Request:

```json
{
  "query": "newer_than:7d",
  "max_results": 5
}
```

Response:

```json
{
  "connected": true,
  "query": "newer_than:7d",
  "count": 3,
  "messages": [
    {
      "id": "...",
      "thread_id": "...",
      "subject": "...",
      "from": "...",
      "date": "...",
      "snippet": "..."
    }
  ]
}
```

Limit max results to a small number, such as:

```text
10
```

Do not return full email bodies in this task.

Do not store messages in the database in this task.

## Gmail Client Requirements

Add a small Gmail service module.

Suggested file:

```text
backend/app/gmail_client.py
```

Responsibilities:

```text
build OAuth auth URL
exchange callback code for token
load token
refresh token when needed
check connection
perform read-only message search
fetch safe metadata/snippets
```

Use official Google client libraries if already present or add necessary dependencies.

If dependencies are added, update the appropriate dependency file.

Do not use browser automation.

## Frontend Requirements

Add minimal UI only if the project already has a settings page or integrations area.

If practical, add a Gmail integration card showing:

```text
Gmail: Connected / Not connected
Connect Gmail button
Test search button
```

If frontend integration is too large, expose backend endpoints and document manual verification with curl. Do not create a new large frontend surface in this task.

Do not show full email bodies.

## Security and Privacy Requirements

Document and enforce:

```text
Read-only Gmail scope only.
No sending emails.
No deleting emails.
No archiving emails.
No labeling emails.
No background polling yet.
No storing full email bodies.
Store only token and small test-search response in memory/API response.
```

Add `.gitignore` entries for local token files, such as:

```text
candidate_context/gmail/token.json
candidate_context/gmail/*.json
```

Do not ignore committed example config files if they exist.

## Documentation

Update:

```text
docs/contracts/gmail_integration.md
```

Add:

```text
OAuth setup
Required Google Cloud credentials
Required redirect URI
Read-only scope
Local token storage
Manual verification
Known limitations
```

Also update install docs if present:

```text
README_INSTALL.md
docs/install.md
```

Include setup steps:

```text
1. Create Google Cloud OAuth client.
2. Add redirect URI matching GOOGLE_REDIRECT_URI.
3. Put client ID/secret in local env.
4. Start backend.
5. Visit /api/gmail/auth-url or frontend connect button.
6. Complete Google consent.
7. Confirm /api/gmail/status reports connected.
8. Run test search.
```

Do not include real credentials.

## Tests

Add backend tests using mocked Google/Gmail client behavior.

Tests must not hit the real Gmail API.

Prove:

1. Gmail status returns disconnected when no token exists.
2. Auth URL endpoint returns a URL and read-only scope.
3. Callback stores token through mocked OAuth flow.
4. Status returns connected when mocked valid token exists.
5. Test search requires connection.
6. Test search caps max results.
7. Test search returns only safe metadata/snippets, not full body.
8. Gmail service never requests modify/send/mail.google.com scopes.
9. Token files are not committed and are ignored where appropriate.
10. No tests require real Google credentials.

If frontend UI is added, add tests if the frontend has test infrastructure.

## Acceptance Criteria

- Gmail read-only OAuth configuration exists.
- Backend exposes Gmail connection status.
- Backend can generate Google OAuth URL.
- Backend can handle OAuth callback with mocked tests.
- Backend can perform a safe mocked test search.
- Only Gmail read-only scope is used.
- No sending/modifying/deleting/labeling behavior is implemented.
- Token file path is ignored by git.
- Gmail setup is documented.
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

Manual verification with real credentials, optional:

1. Configure:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
GMAIL_TOKEN_PATH
```

2. Start backend.

3. Visit:

```text
/api/gmail/status
```

Confirm disconnected.

4. Visit:

```text
/api/gmail/auth-url
```

Open returned URL.

5. Complete Google consent.

6. Confirm:

```text
/api/gmail/status
```

shows connected.

7. Run test search:

```bash
curl -X POST http://localhost:8000/api/gmail/test-search \
  -H "Content-Type: application/json" \
  -d '{"query":"newer_than:7d","max_results":5}'
```

8. Confirm response includes only metadata/snippets.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Gmail read-only OAuth connection
```

Do not push.
