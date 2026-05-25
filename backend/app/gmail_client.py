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
    """Raised when GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are missing."""


class GmailNotConnectedError(RuntimeError):
    """Raised when an operation needs a stored token but none exists."""


class GmailScopeError(RuntimeError):
    """Raised when a non-readonly scope appears on an OAuth request or token."""


class GmailDependencyError(RuntimeError):
    """Raised when the optional google libraries are not installed."""


@dataclass(frozen=True)
class GmailConfig:
    """Resolved Gmail OAuth configuration.

    ``client_id`` / ``client_secret`` are required for any OAuth
    operation; the other fields have sensible local defaults.
    """

    client_id: str | None
    client_secret: str | None
    redirect_uri: str
    token_path: Path

    def is_oauth_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


def _repo_root() -> Path:
    # backend/app/gmail_client.py -> repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _default_token_path() -> Path:
    return _repo_root() / "candidate_context" / "gmail" / "token.json"


def _default_redirect_uri() -> str:
    return "http://localhost:8000/gmail/oauth/callback"


def get_gmail_config() -> GmailConfig:
    """Read the Gmail OAuth configuration from the environment.

    Always returns a :class:`GmailConfig`; call
    :meth:`GmailConfig.is_oauth_configured` to check whether the
    client credentials are present.
    """
    token_path_env = os.environ.get("GMAIL_TOKEN_PATH")
    token_path = Path(token_path_env) if token_path_env else _default_token_path()
    return GmailConfig(
        client_id=os.environ.get("GOOGLE_CLIENT_ID") or None,
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET") or None,
        redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI") or _default_redirect_uri(),
        token_path=token_path,
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
        raise GmailNotConfiguredError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set to use "
            "the Gmail integration"
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
    """Return the Google OAuth consent URL plus the requested scope."""
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
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
        state=state or "",
    )
    return {"auth_url": auth_url, "scope": GMAIL_READONLY_SCOPE}


def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an OAuth ``code`` for a token blob and persist it.

    Returns the saved token blob (a JSON-serializable dict).
    """
    cfg = _require_configured()
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise GmailDependencyError(
            "google-auth-oauthlib is not installed; install the Gmail "
            "extras with `pip install -e .[gmail]`"
        ) from exc

    flow = Flow.from_client_config(
        _client_config(cfg),
        scopes=list(GMAIL_SCOPES),
        redirect_uri=cfg.redirect_uri,
    )
    flow.fetch_token(code=code)
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
    token_blob = load_token()
    if token_blob is None:
        return {
            "connected": False,
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
            "email": None,
            "scopes": scopes,
            "token_path_configured": True,
            "last_checked_at": None,
        }
    return {
        "connected": True,
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
