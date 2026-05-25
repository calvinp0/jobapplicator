# Task 089: Fix Gmail OAuth PKCE Callback Handling

## Goal

Fix Gmail OAuth callback failures caused by missing PKCE code verifier/state handling.

Current observed browser callback:

```text
/gmail/oauth/callback?state=...&code=...&scope=https://www.googleapis.com/auth/gmail.readonly
```

Current backend result:

```text
500 Internal Server Error
```

Current backend traceback ends with:

```text
oauthlib.oauth2.rfc6749.errors.InvalidGrantError: (invalid_grant) Missing code verifier.
```

The backend must return a clear user-facing error instead of 500, and the OAuth flow must persist/reuse the PKCE code verifier between auth URL generation and callback token exchange.

Do not send emails.  
Do not archive, delete, label, or modify Gmail messages.  
Do not implement background polling.  
Do not implement LinkedIn automation.  
Do not change Claude tailoring behavior.

## Background

The Gmail OAuth flow currently has these endpoints:

```text
/gmail/auth-url
/gmail/oauth/callback
/gmail/status
/gmail/test-search
```

The failing stack trace shows:

```text
backend/app/routers/gmail.py
gmail_oauth_callback
  gmail_client.exchange_code(code)

backend/app/gmail_client.py
exchange_code
  flow.fetch_token(code=code)
```

Then:

```text
InvalidGrantError: (invalid_grant) Missing code verifier.
```

This means the authorization URL likely used PKCE, but the callback token exchange did not include the original code verifier.

Google OAuth web-server flow requires maintaining state across redirect and exchanging the authorization code for tokens using the same flow/session assumptions. Localhost redirect URIs are valid for testing when configured in Google Cloud OAuth client.

## Inspect

Inspect:

```text
backend/app/gmail_client.py
backend/app/routers/gmail.py
backend/tests/
frontend/src/pages/
frontend/src/api/
docs/contracts/gmail_integration.md
docs/install.md
README_INSTALL.md
.gitignore
```

Search:

```bash
rg "Flow|authorization_url|fetch_token|code_verifier|state|gmail/auth-url|gmail/oauth/callback" backend frontend docs
```

Use the actual google-auth-oauthlib behavior already in the project.

## Required Behavior

The Gmail OAuth flow must:

```text
1. Generate auth URL.
2. Generate/store state.
3. Generate/store PKCE code verifier if the library uses PKCE.
4. Return the auth URL to the frontend.
5. On callback, validate state.
6. Rehydrate/recreate the OAuth flow with the same redirect URI and code verifier.
7. Exchange code for token.
8. Save token.
9. Return a friendly success response or redirect to Settings.
```

The callback must never expose a raw stack trace or generic 500 for expected OAuth errors.

## PKCE / State Storage

Persist pending OAuth state locally.

Suggested path:

```text
candidate_context/gmail/oauth_state.json
```

or use the existing settings/app-data storage.

Example stored shape:

```json
{
  "state": "...",
  "code_verifier": "...",
  "created_at": "...",
  "redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "scope": "https://www.googleapis.com/auth/gmail.readonly"
}
```

Security requirements:

```text
- Do not commit oauth_state.json.
- Add it to .gitignore if needed.
- Treat oauth_state.json as local secret/session data.
- Delete or invalidate it after successful callback.
- Expire old state, e.g. after 10 minutes.
- Validate callback state before exchanging code.
```

If google-auth-oauthlib exposes `flow.code_verifier`, persist that value after authorization URL creation and restore it before `fetch_token`.

If the installed library can disable PKCE safely for confidential web clients, prefer preserving PKCE rather than disabling it.

## Error Handling Requirements

Handle expected OAuth errors gracefully.

Cases:

```text
missing code
missing state
state mismatch
expired state
missing code verifier
invalid_grant
access_denied
Google token exchange error
missing OAuth config
```

Return structured errors or a small HTML page that links back to Settings.

Do not return generic 500.

Example JSON error:

```json
{
  "detail": {
    "error": "gmail_oauth_callback_failed",
    "message": "Gmail OAuth callback failed: missing or expired OAuth state. Return to Settings and click Connect Gmail again.",
    "recoverable": true
  }
}
```

If browser-based callback returns HTML, it should say:

```text
Gmail connection failed.
Reason: missing or expired OAuth state.
Return to Settings and click Connect Gmail again.
```

## Success Behavior

After successful callback:

```text
- token file is saved
- pending oauth state is cleared
- /gmail/status reports connected
```

Return either:

```text
A simple success HTML page with link to Settings
```

or redirect to frontend Settings if frontend route exists.

Suggested local redirect:

```text
http://localhost:5173/settings?gmail=connected
```

Only use frontend redirect if configurable and documented.

## Unverified App Screen Documentation

Update docs to explain the Google warning:

```text
During local development, Google may show "Google hasn't verified this app" for Gmail scopes.
This is expected for an unverified/test OAuth app.
For local use, add your Google account as a test user in the OAuth consent screen and continue through Advanced/unsafe.
For public distribution, submit app verification to Google.
```

Do not imply users should bypass this for a public/production app.

## Redirect URI Documentation

Update docs to emphasize exact redirect URI matching.

Default:

```text
http://localhost:8000/gmail/oauth/callback
```

The Google Cloud OAuth client must include exactly that URI unless the app config uses a different value.

Mention that changing host/port requires updating both:

```text
GOOGLE_REDIRECT_URI or Settings value
Google Cloud authorized redirect URI
```

## Frontend Requirements

Settings page should handle callback results if applicable.

If callback redirects to:

```text
/settings?gmail=connected
```

show success message:

```text
Gmail connected.
```

If callback redirects to:

```text
/settings?gmail=error
```

show error message and suggest reconnecting.

If backend returns HTML instead, frontend changes may be minimal.

## Tests

Use mocked OAuth library behavior. Do not hit Google.

Add/update backend tests:

1. `/gmail/auth-url` stores pending OAuth state.
2. Stored pending OAuth state includes state and code verifier when PKCE is used.
3. `/gmail/oauth/callback` rejects missing `code`.
4. `/gmail/oauth/callback` rejects missing `state`.
5. `/gmail/oauth/callback` rejects state mismatch.
6. `/gmail/oauth/callback` rejects expired pending state.
7. `/gmail/oauth/callback` restores code verifier before token exchange.
8. Successful callback saves token.
9. Successful callback clears pending OAuth state.
10. `/gmail/status` reports connected after successful callback.
11. InvalidGrantError returns structured/friendly error, not 500.
12. `access_denied` returns structured/friendly error, not 500.
13. Missing OAuth config returns structured/friendly error.
14. OAuth state/token files are gitignored.
15. Tests do not require real Google credentials.

If frontend callback behavior changes, add frontend tests if infrastructure exists.

## Acceptance Criteria

- Gmail OAuth callback no longer fails with missing code verifier when auth URL was generated by this app.
- OAuth state and PKCE verifier are persisted between auth-url and callback.
- Callback validates state.
- Callback clears state after success.
- Expected OAuth errors return friendly messages, not generic 500.
- Docs explain Google unverified-app warning for local development.
- Docs emphasize exact redirect URI matching.
- Tests pass.

## Verification

Run:

```bash
pytest
cd frontend && npm run build
```

Manual verification:

1. Clear stale token/state files:

```bash
rm -f candidate_context/gmail/token.json
rm -f candidate_context/gmail/oauth_state.json
```

2. Start backend and frontend.

3. Open Settings.

4. Click Connect Gmail.

5. Complete Google consent.

6. If Google shows:

```text
Google hasn't verified this app
```

use Advanced/unsafe only for local development with your own test account.

7. Confirm callback does not show 500.

8. Confirm Settings shows Gmail connected.

9. Confirm:

```bash
curl http://localhost:8000/gmail/status
```

returns:

```json
{
  "connected": true
}
```

10. Confirm `candidate_context/gmail/oauth_state.json` was cleared after success.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix Gmail OAuth PKCE callback
```

Do not push.
