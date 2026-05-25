"""Persisted Gmail OAuth configuration (task 088).

Today the user has to set ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``
/ ``GOOGLE_REDIRECT_URI`` env vars before starting the backend. This
module lets the user save the same config from the Settings page
instead, with env vars retained as a fallback for CI / deployment.

Storage uses the existing :class:`~app.models.AppSetting` key/value
table (ADR-009 / task 066). The secret value never leaves this module
in plaintext outside the OAuth flow itself: callers asking for a UI
snapshot get :func:`get_settings_view`, which returns a masked preview.

Lookup priority (read by :mod:`app.gmail_client`):

    1. Settings-stored Gmail OAuth config (this module).
    2. Environment variables.
    3. Built-in defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import SessionLocal
from .models import AppSetting


GMAIL_OAUTH_SETTING_KEY = "gmail_oauth_config"

SECRET_PREVIEW_MASK = "•" * 8  # 8 bullets

_DEFAULT_REDIRECT_URI = "http://localhost:8000/gmail/oauth/callback"
_DEFAULT_TOKEN_PATH = "candidate_context/gmail/token.json"


class GmailSettingsValidationError(ValueError):
    """Raised when an attempt to persist invalid OAuth config is made."""


@dataclass(frozen=True)
class StoredGmailOAuthConfig:
    """The persisted Gmail OAuth config, decoded from the settings row."""

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    gmail_token_path: str | None
    updated_at: str | None


def _load_row() -> dict[str, Any] | None:
    with SessionLocal() as session:
        row = session.get(AppSetting, GMAIL_OAUTH_SETTING_KEY)
        if row is None:
            return None
        try:
            data = json.loads(row.value)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data


def get_stored_config() -> StoredGmailOAuthConfig | None:
    """Return the persisted OAuth config or ``None`` when nothing is saved."""
    raw = _load_row()
    if raw is None:
        return None
    client_id = raw.get("google_client_id") or ""
    client_secret = raw.get("google_client_secret") or ""
    redirect_uri = raw.get("google_redirect_uri") or ""
    if not (client_id and client_secret and redirect_uri):
        # A partially-written row is treated as "not configured" so a
        # later GET / status call falls through to the env fallback.
        return None
    token_path = raw.get("gmail_token_path") or None
    return StoredGmailOAuthConfig(
        google_client_id=client_id,
        google_client_secret=client_secret,
        google_redirect_uri=redirect_uri,
        gmail_token_path=token_path,
        updated_at=raw.get("updated_at"),
    )


def has_stored_config() -> bool:
    return get_stored_config() is not None


def _mask_secret(secret: str | None) -> str:
    if not secret:
        return ""
    return SECRET_PREVIEW_MASK


def save_config(
    *,
    google_client_id: str,
    google_client_secret: str,
    google_redirect_uri: str,
    gmail_token_path: str | None = None,
) -> StoredGmailOAuthConfig:
    """Validate and persist the Gmail OAuth config.

    Raises :class:`GmailSettingsValidationError` for any missing required
    field. The plaintext client secret is **never** logged.
    """
    client_id = (google_client_id or "").strip()
    client_secret = (google_client_secret or "").strip()
    redirect_uri = (google_redirect_uri or "").strip() or _DEFAULT_REDIRECT_URI
    token_path = (gmail_token_path or "").strip() or None

    missing: list[str] = []
    if not client_id:
        missing.append("google_client_id")
    if not client_secret:
        missing.append("google_client_secret")
    if missing:
        raise GmailSettingsValidationError(
            "missing required fields: " + ", ".join(missing)
        )

    payload = {
        "google_client_id": client_id,
        "google_client_secret": client_secret,
        "google_redirect_uri": redirect_uri,
        "gmail_token_path": token_path,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    serialized = json.dumps(payload, sort_keys=True)
    with SessionLocal() as session:
        row = session.get(AppSetting, GMAIL_OAUTH_SETTING_KEY)
        if row is None:
            row = AppSetting(key=GMAIL_OAUTH_SETTING_KEY, value=serialized)
            session.add(row)
        else:
            row.value = serialized
        session.commit()
    return StoredGmailOAuthConfig(
        google_client_id=client_id,
        google_client_secret=client_secret,
        google_redirect_uri=redirect_uri,
        gmail_token_path=token_path,
        updated_at=payload["updated_at"],
    )


def delete_config() -> bool:
    """Remove the persisted OAuth config. Returns ``True`` if a row existed."""
    with SessionLocal() as session:
        row = session.get(AppSetting, GMAIL_OAUTH_SETTING_KEY)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def get_settings_view() -> dict[str, Any]:
    """Return a sanitized snapshot for the GET endpoint and Settings UI.

    Combines the persisted config (if any) with the env-var fallback so
    the UI can render the current effective config in one place. The
    client secret is never returned in plaintext; callers see a masked
    preview and a boolean flag.
    """
    # Import lazily to avoid an import cycle (``gmail_client`` reads this
    # module to layer settings on top of env vars).
    from . import gmail_client

    stored = get_stored_config()
    env_client_id = (gmail_client._env("GOOGLE_CLIENT_ID") or "").strip()
    env_client_secret = (gmail_client._env("GOOGLE_CLIENT_SECRET") or "").strip()
    env_redirect = (gmail_client._env("GOOGLE_REDIRECT_URI") or "").strip()
    env_token_path = (gmail_client._env("GMAIL_TOKEN_PATH") or "").strip()
    env_has_required = bool(env_client_id and env_client_secret)

    if stored is not None:
        return {
            "configured": True,
            "source": "settings",
            "google_client_id": stored.google_client_id,
            "has_google_client_secret": True,
            "google_client_secret_preview": SECRET_PREVIEW_MASK,
            "google_redirect_uri": stored.google_redirect_uri,
            "gmail_token_path": stored.gmail_token_path
            or _DEFAULT_TOKEN_PATH,
            "updated_at": stored.updated_at,
        }
    if env_has_required:
        return {
            "configured": True,
            "source": "environment",
            "google_client_id": env_client_id,
            "has_google_client_secret": True,
            "google_client_secret_preview": "from environment",
            "google_redirect_uri": env_redirect or _DEFAULT_REDIRECT_URI,
            "gmail_token_path": env_token_path or _DEFAULT_TOKEN_PATH,
            "updated_at": None,
        }
    return {
        "configured": False,
        "source": "none",
        "google_client_id": env_client_id or None,
        "has_google_client_secret": False,
        "google_client_secret_preview": "",
        "google_redirect_uri": env_redirect or _DEFAULT_REDIRECT_URI,
        "gmail_token_path": env_token_path or _DEFAULT_TOKEN_PATH,
        "updated_at": None,
    }
