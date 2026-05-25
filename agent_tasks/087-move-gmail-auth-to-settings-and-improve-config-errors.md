# Task 087: Move Gmail Auth to Settings and Improve Config Errors

## Goal

Fix Gmail UX and configuration errors.

Gmail authentication should be global and managed from Settings, not repeated inside each application card/detail.

Applications should use Gmail only after it is connected.

Current observed UI/error:

```text
Gmail tracking

Gmail is used read-only for application tracking. JobApplicator does not send, delete, archive, or label emails.

Gmail status
    Gmail: Not connected

Request to /gmail/auth-url failed with status 400
```

This is confusing. The UI should explain what is missing and direct the user to Settings.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Current Gmail work added:

```text
Gmail read-only OAuth
Gmail search
Gmail classification
Gmail evidence UI
Manual sync
```

But the UX is wrong:

```text
Each application appears to offer Connect Gmail
```

Instead, Gmail should be authenticated once in Settings.

Correct UX:

```text
Settings page:
  Gmail integration card
  Connect Gmail
  Gmail connection status
  Test search / disconnect if implemented

Applications page:
  Sync Gmail for all applications

Application detail/card:
  Check Gmail for this application
  Show candidates/classification/evidence
  If not connected: "Connect Gmail in Settings"
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
docs/install.md
README_INSTALL.md
agent_tasks/queue.yaml
```

Search:

```bash
rg "gmail|auth-url|Connect Gmail|Gmail status|Settings" backend frontend docs
```

Use existing project patterns.

## Backend Requirements

### Improve `/gmail/auth-url` error responses

If Gmail OAuth config is missing, `/gmail/auth-url` should not return a generic 400.

It should return structured, actionable JSON.

Example:

```json
{
  "detail": {
    "error": "gmail_oauth_not_configured",
    "message": "Gmail OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI.",
    "missing": [
      "GOOGLE_CLIENT_ID",
      "GOOGLE_CLIENT_SECRET",
      "GOOGLE_REDIRECT_URI"
    ]
  }
}
```

Use the project’s existing error response style if different.

The frontend should be able to display:

```text
Gmail OAuth is not configured.
Missing: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
```

### Improve `/gmail/status`

`/gmail/status` should include configuration state:

```json
{
  "connected": false,
  "configured": false,
  "missing_config": [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI"
  ],
  "email": null,
  "scopes": [],
  "token_path_configured": true,
  "last_checked_at": null
}
```

When configured but not connected:

```json
{
  "connected": false,
  "configured": true,
  "missing_config": [],
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
  "configured": true,
  "missing_config": [],
  "email": null,
  "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "token_path_configured": true,
  "last_checked_at": "..."
}
```

Do not add extra Google scopes just to get the email address.

## Frontend Requirements

### Settings Page

Move Gmail connection UI to Settings.

Add a Gmail integration card in Settings:

```text
Gmail integration

Gmail is used read-only for application tracking.
JobApplicator does not send, delete, archive, or label emails.

Status:
  Connected / Not connected / Not configured

Actions:
  Connect Gmail
  Test Gmail search, if endpoint exists
```

If not configured, show:

```text
Gmail OAuth is not configured.
Missing: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
See install docs for setup.
```

Do not show a Connect Gmail button if config is missing.

If configured but not connected, show:

```text
Connect Gmail
```

Clicking Connect Gmail should call:

```text
GET /api/gmail/auth-url
```

or the actual configured route.

If connected, show:

```text
Gmail connected
```

and optionally show scopes.

### Applications Page

Add or keep global manual sync action:

```text
Sync Gmail
```

This belongs on the Applications page, not inside Settings.

If Gmail is disconnected:

```text
Connect Gmail in Settings before syncing applications.
```

Do not call `/gmail/auth-url` from the Applications page.

If Gmail is not configured:

```text
Gmail OAuth is not configured. Open Settings for setup details.
```

### Application Detail/Card

Per-application Gmail area should show:

```text
Check Gmail for this application
```

only when Gmail is connected.

If Gmail is not connected:

```text
Connect Gmail in Settings to check application emails.
```

If Gmail is not configured:

```text
Gmail OAuth is not configured. Configure it in Settings first.
```

Do not show `Connect Gmail` inside each application card/detail.

Do not call `/gmail/auth-url` from application cards/details.

## API Client Requirements

Update frontend API types for Gmail status:

```ts
type GmailStatusResponse = {
  connected: boolean;
  configured: boolean;
  missing_config: string[];
  email: string | null;
  scopes: string[];
  token_path_configured: boolean;
  last_checked_at: string | null;
};
```

Use actual project style.

## Documentation Requirements

Update:

```text
docs/contracts/gmail_integration.md
docs/install.md
README_INSTALL.md
```

Document:

```text
Gmail is configured/authenticated globally in Settings.
Applications only use the existing Gmail connection.
Global sync lives on the Applications page.
Per-application check lives on the application detail/card.
Required env vars:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI
  GMAIL_TOKEN_PATH
```

Also document the observed 400 case:

```text
If /gmail/auth-url returns gmail_oauth_not_configured, set the missing environment variables and restart the backend.
```

## Tests

Add/update backend tests:

1. `/gmail/status` returns `configured=false` and missing vars when OAuth env vars are absent.
2. `/gmail/status` returns `configured=true` when required env vars exist.
3. `/gmail/auth-url` returns structured error when config is missing.
4. `/gmail/auth-url` includes missing config names in the response.
5. `/gmail/auth-url` still returns auth URL when config exists.
6. Gmail scope remains read-only.

Add/update frontend tests if test infrastructure exists:

1. Settings page shows Gmail integration card.
2. Settings page shows not configured state with missing env vars.
3. Settings page hides Connect Gmail when config is missing.
4. Settings page shows Connect Gmail when configured but disconnected.
5. Applications page shows Sync Gmail.
6. Applications page does not show per-card Connect Gmail.
7. Application detail says Connect Gmail in Settings when disconnected.
8. Application detail does not call `/gmail/auth-url`.
9. Connect Gmail action exists only in Settings.
10. 400 config error displays actionable message.

## Acceptance Criteria

- Gmail auth/connect UI lives in Settings.
- Applications page has global Sync Gmail.
- Application detail/card has per-application Check Gmail only when connected.
- Application cards/details do not call `/gmail/auth-url`.
- `/gmail/status` exposes `configured` and `missing_config`.
- `/gmail/auth-url` returns actionable structured error when config is missing.
- Error message no longer appears as generic `Request to /gmail/auth-url failed with status 400`.
- Gmail remains read-only.
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

1. Start backend without Gmail env vars.
2. Open Settings.
3. Confirm Gmail card says not configured and lists missing variables.
4. Confirm Connect Gmail is not shown when config is missing.
5. Open Applications.
6. Confirm application cards do not show Connect Gmail.
7. Confirm global Sync Gmail says Gmail must be configured/connected.
8. Add Gmail env vars and restart backend.
9. Open Settings.
10. Confirm Connect Gmail appears.
11. Click Connect Gmail.
12. Confirm `/gmail/auth-url` no longer returns generic 400.
13. After connecting, open Applications.
14. Confirm Sync Gmail is available.
15. Open application detail.
16. Confirm Check Gmail is available for that application.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Move Gmail auth to Settings
```

Do not push.
