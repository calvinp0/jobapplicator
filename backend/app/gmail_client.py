"""Read-only Gmail OAuth + search helpers (task 082).

This module is the *only* place in the backend that knows how to talk to
Google. All Google library imports are intentionally lazy (inside the
functions that need them) for two reasons:

1. ``app.main`` must remain importable without ``google-auth-oauthlib``
   or ``google-api-python-client`` installed. The task-080 safety guard
   ``test_no_gmail_outbound_modules_imported`` enforces this.
2. The Gmail integration is an optional extra (``pip install -e
   .[gmail]``); users who never connect Gmail do not need to install
   those wheels.

Scope policy
------------
Only the read-only Gmail scope is ever requested:

    https://www.googleapis.com/auth/gmail.readonly

Broader scopes (``gmail.modify``, ``gmail.send``, ``mail.google.com``)
are explicitly rejected by :func:`assert_readonly_scope` and are not
configurable. Adding a write scope requires an ADR per
``docs/contracts/gmail_integration.md``.

Token storage
-------------
Tokens live in a local JSON file (default
``candidate_context/gmail/token.json``). This is *development-grade*
storage — the file holds a refresh token in plain text and must never
be committed (see ``.gitignore``). Production-grade secret management
is out of scope for this task.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES: tuple[str, ...] = (GMAIL_READONLY_SCOPE,)

# Hard cap on the number of test-search results a single API response
# can return. The task explicitly limits this surface; the router clamps
# user input to this value before passing it down.
MAX_TEST_SEARCH_RESULTS = 10

# Forbidden scopes — never request these and never accept a stored
# token whose granted scopes include any of them.
FORBIDDEN_SCOPES: frozenset[str] = frozenset(
    {
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.insert",
        "https://www.googleapis.com/auth/gmail.labels",
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/gmail.settings.sharing",
        "https://mail.google.com/",
    }
)


class GmailNotConfiguredError(RuntimeError):
    """Raised when GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are missing.

    ``missing`` carries the env var names the user still needs to set so
    the HTTP layer can return a structured, actionable error body.
    """

    def __init__(self, message: str, missing: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing = list(missing or [])


class GmailNotConnectedError(RuntimeError):
    """Raised when an operation needs a stored token but none exists."""


class GmailScopeError(RuntimeError):
    """Raised when a non-readonly scope appears on an OAuth request or token."""


class GmailDependencyError(RuntimeError):
    """Raised when the optional google libraries are not installed."""


class GmailOAuthStateError(RuntimeError):
    """Raised when the OAuth callback cannot validate pending state.

    Covers the *expected* OAuth callback failure modes — missing state,
    state mismatch, expired pending state, or a missing PKCE code
    verifier. The router turns these into a friendly user-facing
    response instead of a 500 stack trace.
    """


class GmailOAuthExchangeError(RuntimeError):
    """Raised when Google rejects the authorization code at token exchange.

    Wraps the underlying oauthlib error so the router does not need to
    know about google-auth-oauthlib internals.
    """


# The Gmail OAuth env vars the user must set, in the order surfaced to
# the UI. ``GOOGLE_REDIRECT_URI`` has a sensible local default but is
# still part of the documented setup so it is included here so the UI /
# install docs can list it; ``configured`` only requires the credentials.
REQUIRED_OAUTH_ENV_VARS: tuple[str, ...] = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
)


@dataclass(frozen=True)
class GmailConfig:
    """Resolved Gmail OAuth configuration.

    ``client_id`` / ``client_secret`` are required for any OAuth
    operation; the other fields have sensible local defaults.
    ``source`` records where the credentials came from
    (``"settings"`` / ``"environment"`` / ``"none"``) so the UI and the
    structured config-error responses can name it.
    """

    client_id: str | None
    client_secret: str | None
    redirect_uri: str
    redirect_uri_explicit: bool
    token_path: Path
    source: str = "none"

    def is_oauth_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def missing_config(self) -> list[str]:
        """Names of the OAuth fields the user still needs to set.

        Returns ``[]`` when :meth:`is_oauth_configured` is true so the
        ``/gmail/status`` and ``/gmail/auth-url`` surfaces can render a
        clean "ready" state. When the credentials are not set, the
        redirect URI is included if the user has not explicitly set it,
        so the install-time instructions match what the UI tells them
        to set.
        """
        if self.is_oauth_configured():
            return []
        missing: list[str] = []
        if not self.client_id:
            missing.append("GOOGLE_CLIENT_ID")
        if not self.client_secret:
            missing.append("GOOGLE_CLIENT_SECRET")
        if not self.redirect_uri_explicit:
            missing.append("GOOGLE_REDIRECT_URI")
        return missing


def _repo_root() -> Path:
    # backend/app/gmail_client.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _default_token_path() -> Path:
    return _repo_root() / "candidate_context" / "gmail" / "token.json"


# Pending OAuth-state lifetime. Google's consent screen can take time;
# 10 minutes is long enough for a deliberate user but short enough that
# an abandoned attempt cannot be picked up later.
OAUTH_STATE_TTL_SECONDS = 600


def _oauth_state_path() -> Path:
    """Return the path used to persist the pending OAuth state blob.

    Lives next to the token file so the operator only has to remember
    one secret-bearing directory.
    """
    cfg = get_gmail_config()
    return cfg.token_path.parent / "oauth_state.json"


def _default_redirect_uri() -> str:
    return "http://localhost:8000/gmail/oauth/callback"


def _env(name: str) -> str | None:
    """Tiny wrapper around ``os.environ.get`` for test/monkeypatch reach."""
    return os.environ.get(name)


def get_gmail_config() -> GmailConfig:
    """Resolve the Gmail OAuth config.

    Priority order (task 088):

    1. Settings-stored Gmail OAuth config (``app.gmail_settings``).
    2. Environment variables (``GOOGLE_CLIENT_ID`` etc.).
    3. Built-in defaults for non-secret fields.

    Always returns a :class:`GmailConfig`; call
    :meth:`GmailConfig.is_oauth_configured` to check whether the
    client credentials are present. The ``source`` field tells callers
    which layer supplied the credentials so the Settings UI can label
    env-loaded configs accordingly.
    """
    # Imported lazily so ``app.main`` and ``app.gmail_client`` can be
    # imported in any order without a circular import.
    from . import gmail_settings

    stored = gmail_settings.get_stored_config()

    token_path_env = _env("GMAIL_TOKEN_PATH")
    redirect_uri_env = _env("GOOGLE_REDIRECT_URI") or None
    client_id_env = _env("GOOGLE_CLIENT_ID") or None
    client_secret_env = _env("GOOGLE_CLIENT_SECRET") or None

    if stored is not None:
        token_path = (
            Path(stored.gmail_token_path)
            if stored.gmail_token_path
            else _default_token_path()
        )
        return GmailConfig(
            client_id=stored.google_client_id,
            client_secret=stored.google_client_secret,
            redirect_uri=stored.google_redirect_uri,
            redirect_uri_explicit=True,
            token_path=token_path,
            source="settings",
        )

    token_path = (
        Path(token_path_env) if token_path_env else _default_token_path()
    )
    source = "environment" if (client_id_env and client_secret_env) else "none"
    return GmailConfig(
        client_id=client_id_env,
        client_secret=client_secret_env,
        redirect_uri=redirect_uri_env or _default_redirect_uri(),
        redirect_uri_explicit=redirect_uri_env is not None,
        token_path=token_path,
        source=source,
    )


def assert_readonly_scope(scopes: list[str] | tuple[str, ...]) -> None:
    """Reject any scope set that would grant write/modify access."""
    for s in scopes:
        if s in FORBIDDEN_SCOPES:
            raise GmailScopeError(
                f"refusing forbidden Gmail scope: {s!r}; only "
                f"{GMAIL_READONLY_SCOPE} is allowed"
            )


def _require_configured() -> GmailConfig:
    cfg = get_gmail_config()
    if not cfg.is_oauth_configured():
        missing = cfg.missing_config()
        raise GmailNotConfiguredError(
            "Gmail OAuth is not configured. Set "
            + ", ".join(missing) + ".",
            missing=missing,
        )
    return cfg


def _client_config(cfg: GmailConfig) -> dict[str, Any]:
    return {
        "web": {
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [cfg.redirect_uri],
        }
    }


def save_oauth_state(
    *,
    state: str,
    code_verifier: str | None,
    redirect_uri: str,
    scope: str,
) -> Path:
    """Persist the pending OAuth ``state`` + PKCE ``code_verifier``.

    The blob is written atomically next to the token file so that a
    subsequent callback request can rehydrate the same PKCE verifier
    and validate ``state``. Returns the file path.
    """
    path = _oauth_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        "state": state,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2, sort_keys=True))
    os.replace(tmp, path)
    return path


def load_oauth_state() -> dict[str, Any] | None:
    """Return the pending OAuth state blob, or ``None`` if absent/unreadable."""
    path = _oauth_state_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def clear_oauth_state() -> None:
    """Delete the pending OAuth state file if it exists.

    Called after a successful (or definitively failed) exchange so a
    leaked verifier cannot be reused.
    """
    path = _oauth_state_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # Best-effort: a permissions error here should not mask the
        # original outcome of the callback.
        pass


def _oauth_state_age_seconds(blob: dict[str, Any]) -> float | None:
    """Return age in seconds, or ``None`` when the timestamp is unparseable."""
    created_at = blob.get("created_at")
    if not isinstance(created_at, str):
        return None
    try:
        ts = datetime.fromisoformat(created_at)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def save_token(token_data: dict[str, Any]) -> Path:
    """Persist ``token_data`` to the configured token path atomically."""
    cfg = get_gmail_config()
    cfg.token_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.token_path.with_suffix(cfg.token_path.suffix + ".tmp")
    tmp.write_text(json.dumps(token_data, indent=2, sort_keys=True))
    os.replace(tmp, cfg.token_path)
    return cfg.token_path


def load_token() -> dict[str, Any] | None:
    """Return the persisted token blob or ``None`` if no file exists."""
    cfg = get_gmail_config()
    if not cfg.token_path.is_file():
        return None
    try:
        return json.loads(cfg.token_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def has_token() -> bool:
    return load_token() is not None


def build_auth_url(state: str | None = None) -> dict[str, str]:
    """Return the Google OAuth consent URL plus the requested scope.

    Persists the OAuth ``state`` and PKCE ``code_verifier`` chosen by
    the underlying ``Flow`` so :func:`exchange_code` can rehydrate them
    on the callback. Without this round-trip, Google rejects the token
    exchange with ``invalid_grant: Missing code verifier``.
    """
    cfg = _require_configured()
    assert_readonly_scope(list(GMAIL_SCOPES))
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via tests with mock
        raise GmailDependencyError(
            "google-auth-oauthlib is not installed; install the Gmail "
            "extras with `pip install -e .[gmail]`"
        ) from exc

    flow = Flow.from_client_config(
        _client_config(cfg),
        scopes=list(GMAIL_SCOPES),
        redirect_uri=cfg.redirect_uri,
    )
    kwargs: dict[str, Any] = {
        "access_type": "offline",
        "include_granted_scopes": "false",
        "prompt": "consent",
    }
    if state:
        kwargs["state"] = state
    auth_url, returned_state = flow.authorization_url(**kwargs)

    save_oauth_state(
        state=returned_state,
        code_verifier=getattr(flow, "code_verifier", None),
        redirect_uri=cfg.redirect_uri,
        scope=GMAIL_READONLY_SCOPE,
    )
    return {"auth_url": auth_url, "scope": GMAIL_READONLY_SCOPE}


def exchange_code(code: str, state: str | None = None) -> dict[str, Any]:
    """Exchange an OAuth ``code`` for a token blob and persist it.

    Validates ``state`` against the pending OAuth state written by
    :func:`build_auth_url` and restores the PKCE ``code_verifier``
    before calling ``fetch_token``. On success the pending state file
    is cleared. Returns the saved token blob.
    """
    cfg = _require_configured()

    # State validation runs before the google-auth-oauthlib import so a
    # state mismatch / missing-state error surfaces cleanly even on a
    # machine where the optional gmail extras are not installed (and so
    # the tests can exercise the validation path without the wheels).
    pending = load_oauth_state()
    if pending is None:
        raise GmailOAuthStateError(
            "missing or expired OAuth state. Return to Settings and "
            "click Connect Gmail again."
        )
    age = _oauth_state_age_seconds(pending)
    if age is None or age > OAUTH_STATE_TTL_SECONDS:
        clear_oauth_state()
        raise GmailOAuthStateError(
            "OAuth state has expired. Return to Settings and click "
            "Connect Gmail again."
        )
    expected_state = pending.get("state")
    if expected_state:
        if not state:
            raise GmailOAuthStateError(
                "OAuth callback is missing the 'state' parameter."
            )
        if state != expected_state:
            raise GmailOAuthStateError(
                "OAuth state did not match the pending request. "
                "Return to Settings and click Connect Gmail again."
            )

    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmailDependencyError(
            "google-auth-oauthlib is not installed; install the Gmail "
            "extras with `pip install -e .[gmail]`"
        ) from exc

    redirect_uri = pending.get("redirect_uri") or cfg.redirect_uri
    flow = Flow.from_client_config(
        _client_config(cfg),
        scopes=list(GMAIL_SCOPES),
        redirect_uri=redirect_uri,
    )
    stored_verifier = pending.get("code_verifier")
    if stored_verifier:
        flow.code_verifier = stored_verifier

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        # google-auth-oauthlib re-raises oauthlib errors directly; we
        # catch broadly so an InvalidGrantError, MissingCodeError,
        # or any HTTP/network failure becomes a clean structured
        # error instead of a 500. The state file is cleared so the
        # user can start a fresh attempt without a stale verifier.
        clear_oauth_state()
        message = str(exc) or exc.__class__.__name__
        raise GmailOAuthExchangeError(
            f"Google rejected the OAuth code exchange: {message}"
        ) from exc

    creds = flow.credentials
    scopes = list(getattr(creds, "scopes", []) or [])
    assert_readonly_scope(scopes)

    token_blob: dict[str, Any] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    # Best-effort: fetch the connected email via getProfile, which is
    # available under gmail.readonly without any extra scope.
    try:
        token_blob["email"] = _fetch_profile_email(creds)
    except Exception:  # pragma: no cover - network/profile failure is non-fatal
        token_blob["email"] = None

    save_token(token_blob)
    clear_oauth_state()
    return token_blob


def _credentials_from_token(token_blob: dict[str, Any]):
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmailDependencyError(
            "google-auth is not installed; install the Gmail extras with "
            "`pip install -e .[gmail]`"
        ) from exc
    return Credentials(
        token=token_blob.get("token"),
        refresh_token=token_blob.get("refresh_token"),
        token_uri=token_blob.get("token_uri"),
        client_id=token_blob.get("client_id"),
        client_secret=token_blob.get("client_secret"),
        scopes=token_blob.get("scopes") or list(GMAIL_SCOPES),
    )


def _fetch_profile_email(creds) -> str | None:
    """Return the connected mailbox email via ``users.getProfile``."""
    try:
        from googleapiclient.discovery import build  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmailDependencyError(
            "google-api-python-client is not installed; install the Gmail "
            "extras with `pip install -e .[gmail]`"
        ) from exc
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    email = profile.get("emailAddress")
    return email if isinstance(email, str) else None


def get_status() -> dict[str, Any]:
    """Return the connection-state surface consumed by ``GET /gmail/status``."""
    cfg = get_gmail_config()
    configured = cfg.is_oauth_configured()
    missing = cfg.missing_config()
    token_blob = load_token()
    if token_blob is None:
        return {
            "connected": False,
            "configured": configured,
            "missing_config": missing,
            "email": None,
            "scopes": [],
            "token_path_configured": True,
            "last_checked_at": None,
        }
    scopes = list(token_blob.get("scopes") or [])
    try:
        assert_readonly_scope(scopes)
    except GmailScopeError:
        return {
            "connected": False,
            "configured": configured,
            "missing_config": missing,
            "email": None,
            "scopes": scopes,
            "token_path_configured": True,
            "last_checked_at": None,
        }
    return {
        "connected": True,
        "configured": configured,
        "missing_config": missing,
        "email": token_blob.get("email"),
        "scopes": scopes,
        "token_path_configured": bool(cfg.token_path),
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    }


def search_messages(query: str, max_results: int) -> list[dict[str, Any]]:
    """Run a read-only Gmail search and return safe metadata only.

    The returned dicts contain ``id``, ``thread_id``, ``subject``,
    ``from``, ``date``, and ``snippet``. **No** full body is fetched
    or returned by this task.
    """
    token_blob = load_token()
    if token_blob is None:
        raise GmailNotConnectedError("Gmail is not connected")

    capped = max(0, min(int(max_results), MAX_TEST_SEARCH_RESULTS))

    try:
        from googleapiclient.discovery import build  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmailDependencyError(
            "google-api-python-client is not installed; install the Gmail "
            "extras with `pip install -e .[gmail]`"
        ) from exc

    creds = _credentials_from_token(token_blob)
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    listed = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=capped)
        .execute()
    )
    out: list[dict[str, Any]] = []
    for msg in (listed.get("messages") or [])[:capped]:
        detail = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            )
            .execute()
        )
        out.append(_metadata_from_message(detail))
    return out


def _metadata_from_message(message: dict[str, Any]) -> dict[str, Any]:
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in (message.get("payload", {}).get("headers") or [])
    }
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "subject": headers.get("subject"),
        "from": headers.get("from"),
        "date": headers.get("date"),
        "snippet": message.get("snippet"),
    }
