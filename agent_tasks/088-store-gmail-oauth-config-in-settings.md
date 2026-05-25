# Task 088: Store Gmail OAuth Config in Settings

## Goal

Allow Gmail OAuth configuration to be entered and persisted from the Settings page instead of requiring shell environment variables before starting the backend.

The app should still support environment variables as a fallback, but local Settings should be the primary user-friendly path.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

Current Gmail setup requires setting environment variables before starting the backend:

```bash
export GOOGLE_CLIENT_ID="<your client id>.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="<your client secret>"
export GOOGLE_REDIRECT_URI="http://localhost:8000/gmail/oauth/callback"
export GMAIL_TOKEN_PATH="$PWD/candidate_context/gmail/token.json"
```

This is inconvenient for a local cockpit app, especially when moving across Linux, macOS, and Windows.

The user expectation is:

```text
Open Settings
Paste Gmail OAuth client ID / client secret / redirect URI
Save
Click Connect Gmail
```

Settings should persist the config locally.

## Desired Behavior

Gmail OAuth config resolution should use this priority order:

```text
1. Settings-stored Gmail OAuth config
2. Environment variables
3. Not configured
```

Environment variables remain useful for deployment/CI/power users, but they should not be required for local use.

## Inspect

Inspect:

```text
backend/app/
backend/tests/
frontend/src/pages/
frontend/src/components/
frontend/src/api/
frontend/src/test/
docs/contracts/gmail_integration.md
docs/install.md
README_INSTALL.md
.gitignore
.env.example
agent_tasks/queue.yaml
```

Search for existing settings storage:

```bash
rg "settings|Setting|config|GMAIL|GOOGLE_CLIENT|TOKEN_PATH" backend frontend docs
```

Use the existing project settings architecture if one exists.

## Backend Requirements

Add persisted Gmail OAuth config support.

Suggested local storage location if no settings storage exists:

```text
candidate_context/settings/gmail_oauth.json
```

Suggested shape:

```json
{
  "google_client_id": "<client id>",
  "google_client_secret": "<client secret>",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json",
  "updated_at": "..."
}
```

If the project already has a settings table/file, use that instead.

## Secret Handling Requirements

The stored Gmail OAuth config contains a client secret.

Requirements:

```text
- Do not commit the settings file.
- Add it to .gitignore if needed.
- Never log google_client_secret.
- Never return google_client_secret in plaintext from GET endpoints.
- Return only a masked value or a boolean flag such as has_google_client_secret.
```

Example GET response:

```json
{
  "google_client_id": "123456789-abc.apps.googleusercontent.com",
  "has_google_client_secret": true,
  "google_client_secret_preview": "••••••••",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json",
  "source": "settings"
}
```

If config comes from env vars, response may say:

```json
{
  "source": "environment",
  "google_client_id": "123456789-abc.apps.googleusercontent.com",
  "has_google_client_secret": true,
  "google_client_secret_preview": "from environment",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json"
}
```

Do not expose the env secret.

## Config Resolution Requirements

Update Gmail config loading so it can read from:

```text
settings file/table
environment variables
defaults
```

Required fields:

```text
GOOGLE_CLIENT_ID / google_client_id
GOOGLE_CLIENT_SECRET / google_client_secret
GOOGLE_REDIRECT_URI / google_redirect_uri
```

Optional:

```text
GMAIL_TOKEN_PATH / gmail_token_path
```

Default token path:

```text
candidate_context/gmail/token.json
```

If required fields are missing, `/gmail/status` should report:

```json
{
  "configured": false,
  "missing_config": [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI"
  ]
}
```

But if values exist in settings, do not require env vars.

## Backend API Requirements

Add Settings endpoints following project route style.

Suggested endpoints:

```text
GET  /api/settings/gmail-oauth
PUT  /api/settings/gmail-oauth
DELETE /api/settings/gmail-oauth
```

Use existing route conventions.

### GET settings

Return sanitized config only:

```json
{
  "configured": true,
  "source": "settings",
  "google_client_id": "...",
  "has_google_client_secret": true,
  "google_client_secret_preview": "••••••••",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json"
}
```

### PUT settings

Request:

```json
{
  "google_client_id": "...",
  "google_client_secret": "...",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json"
}
```

Validation:

```text
google_client_id is required
google_client_secret is required unless preserving existing secret is explicitly supported
google_redirect_uri is required
gmail_token_path optional
```

Do not log request body.

If the frontend wants to update only the redirect URI without changing an existing secret, support:

```json
{
  "google_client_id": "...",
  "google_client_secret": null,
  "preserve_existing_secret": true,
  "google_redirect_uri": "...",
  "gmail_token_path": "..."
}
```

Only add this if simple.

### DELETE settings

Remove local settings-stored OAuth config.

Do not delete token unless explicitly requested. If implementing delete token too, require a separate explicit request.

## Gmail Auth Integration

Update existing Gmail endpoints:

```text
/gmail/status
/gmail/auth-url
/gmail/oauth/callback
/gmail/test-search
```

so they use the resolved config:

```text
settings first
env fallback
```

`/gmail/auth-url` should work after saving config in Settings without restarting the backend.

## Frontend Requirements

Update the Settings page Gmail integration card.

When not configured, show form fields:

```text
Google Client ID
Google Client Secret
Redirect URI
Token path
```

Defaults:

```text
Redirect URI: http://localhost:8000/gmail/oauth/callback
Token path: candidate_context/gmail/token.json
```

Actions:

```text
Save Gmail config
Connect Gmail
Test connection/search if available
Delete local Gmail config
```

Behavior:

```text
- If config is missing, show the form.
- After saving config, refresh Gmail status.
- Connect Gmail should become available immediately without backend restart.
- Secret field should not be prefilled with plaintext secret.
- If a secret exists, show "Client secret saved" or masked placeholder.
```

Do not show the secret in page HTML after save.

## Environment Variable Fallback UI

If config is coming from env vars, Settings should show:

```text
Gmail OAuth config is loaded from environment variables.
You can override it by saving local settings.
```

Do not display env secret.

## Documentation Requirements

Update:

```text
docs/contracts/gmail_integration.md
docs/install.md
README_INSTALL.md
```

Change the docs from env-only to:

```text
Recommended local setup:
  configure Gmail OAuth in Settings

Alternative:
  use environment variables
```

Document:

```text
Settings-stored secrets are local development secrets.
Do not commit candidate_context/settings/gmail_oauth.json.
Env vars still work.
Settings config takes precedence over env vars.
```

Update troubleshooting for:

```text
gmail_oauth_not_configured
```

to say:

```text
Either save Gmail OAuth config in Settings or set env vars and restart backend.
```

## Gitignore Requirements

Ensure local secrets are ignored:

```text
candidate_context/gmail/token.json
candidate_context/gmail/*.json
candidate_context/settings/gmail_oauth.json
candidate_context/settings/*.secret.json
```

Do not ignore non-secret candidate context files broadly unless already intended.

## Tests

Add/update backend tests:

1. Gmail status is not configured when neither settings nor env exists.
2. Saving settings config makes Gmail status configured without env vars.
3. `/gmail/auth-url` uses settings config.
4. Env vars work as fallback when settings config is absent.
5. Settings config takes precedence over env vars.
6. GET settings never returns plaintext client secret.
7. PUT settings does not log client secret.
8. DELETE settings removes local settings config.
9. Missing config error mentions settings or env vars.
10. Token path defaults to `candidate_context/gmail/token.json`.
11. Secret settings file is ignored by git if `.gitignore` is testable.

Add/update frontend tests if test infrastructure exists:

1. Settings page shows Gmail OAuth form when not configured.
2. Save Gmail config calls settings endpoint.
3. After save, Connect Gmail appears.
4. Secret is not rendered in plaintext after save.
5. Env-loaded config shows source as environment.
6. Missing config message mentions Settings.

## Acceptance Criteria

- User can enter Gmail OAuth config in Settings.
- Config persists locally.
- Gmail auth URL works after saving settings without backend restart.
- Env vars remain supported as fallback.
- Settings config takes precedence over env vars.
- Client secret is never returned/logged/displayed in plaintext.
- Secret settings file is gitignored.
- Docs describe Settings-first setup.
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
3. Confirm Gmail OAuth form is visible.
4. Enter client ID, client secret, redirect URI, and token path.
5. Save.
6. Confirm Settings shows configured.
7. Confirm Connect Gmail appears.
8. Click Connect Gmail.
9. Confirm `/gmail/auth-url` succeeds without backend restart.
10. Complete OAuth.
11. Confirm Gmail status is connected.
12. Refresh page and confirm secret is not displayed in plaintext.
13. Confirm `candidate_context/settings/gmail_oauth.json` is not tracked by git.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Store Gmail OAuth config in Settings
```

Do not push.
