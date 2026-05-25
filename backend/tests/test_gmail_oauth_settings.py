"""Tests for the Settings-stored Gmail OAuth config (task 088).

Covers:

- The settings-first / env-fallback resolution in
  :func:`app.gmail_client.get_gmail_config`.
- The new ``/settings/gmail-oauth`` GET/PUT/DELETE endpoints.
- Secret-handling guarantees (never returned in plaintext, never
  logged in the PUT request handler).
- That `/gmail/status` and `/gmail/auth-url` pick up the saved config
  without a restart (i.e. each request re-reads the resolver).
- Default token path when none is supplied.
- That the secret-bearing files are gitignored.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture()
def settings_env(tmp_path: Path) -> Iterator[Path]:
    """Configure a fresh DB + master-resumes dir, with NO Gmail env vars."""
    token_path = tmp_path / "gmail" / "token.json"
    # Make sure no Gmail env vars are present so the resolution path
    # exercises the "Settings empty + env empty" baseline.
    for key in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "GMAIL_TOKEN_PATH",
    ):
        os.environ.pop(key, None)
    # Per-test token path so a stale token never leaks across tests.
    os.environ["GMAIL_TOKEN_PATH"] = str(token_path)
    yield token_path
    for key in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "GMAIL_TOKEN_PATH",
    ):
        os.environ.pop(key, None)


@pytest.fixture()
def gmail_settings_client(settings_env, tmp_path: Path):
    """Yield (TestClient, gmail_client module, gmail_settings module)."""
    from fastapi.testclient import TestClient

    db_file = tmp_path / "gmail-settings-tests.db"
    os.environ["JOBAPPLY_DATABASE_URL"] = f"sqlite:///{db_file}"

    master_resumes_dir = tempfile.mkdtemp(prefix="jobapply-master-resumes-")
    os.environ["JOBAPPLY_MASTER_RESUMES_ROOT"] = master_resumes_dir

    for mod_name in [
        "app.main",
        "app.routers.applications",
        "app.routers.captures",
        "app.routers.evidence_banks",
        "app.routers.files",
        "app.routers.gmail",
        "app.routers.jobs",
        "app.routers.llm_providers",
        "app.routers.master_resumes",
        "app.routers.resume_versions",
        "app.routers.runs",
        "app.routers.settings",
        "app.routers",
        "app.run_directory",
        "app.run_import",
        "app.claude_worker",
        "app.llm_providers",
        "app.gmail_client",
        "app.gmail_settings",
        "app.settings",
        "app.schemas",
        "app.models",
        "app.db",
        "app",
    ]:
        sys.modules.pop(mod_name, None)

    from app.main import app  # noqa: E402
    from app import gmail_client, gmail_settings  # noqa: E402

    with TestClient(app) as c:
        yield c, gmail_client, gmail_settings

    import shutil

    shutil.rmtree(master_resumes_dir, ignore_errors=True)


# ---- Status / resolution -------------------------------------------------


def test_status_not_configured_without_settings_or_env(gmail_settings_client):
    client, _, _ = gmail_settings_client
    body = client.get("/gmail/status").json()
    assert body["configured"] is False
    assert body["missing_config"] == [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
    ]


def test_saving_settings_configures_gmail_without_env(gmail_settings_client):
    client, _, _ = gmail_settings_client
    payload = {
        "google_client_id": "set-id.apps.googleusercontent.com",
        "google_client_secret": "set-secret",
        "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        "gmail_token_path": "candidate_context/gmail/token.json",
    }
    r = client.put("/settings/gmail-oauth", json=payload)
    assert r.status_code == 200, r.text

    status_body = client.get("/gmail/status").json()
    assert status_body["configured"] is True
    assert status_body["missing_config"] == []


def test_auth_url_uses_settings_config(gmail_settings_client, monkeypatch):
    client, gmail_client, _ = gmail_settings_client

    captured: dict[str, object] = {}

    def fake_build_auth_url(state=None):  # noqa: ARG001
        # Read the live resolver each call to confirm it returns the
        # Settings-stored credentials, not the (empty) env.
        cfg = gmail_client.get_gmail_config()
        captured["client_id"] = cfg.client_id
        captured["source"] = cfg.source
        return {
            "auth_url": "https://accounts.google.com/o/oauth2/auth?fake",
            "scope": gmail_client.GMAIL_READONLY_SCOPE,
        }

    monkeypatch.setattr(gmail_client, "build_auth_url", fake_build_auth_url)

    client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "live-id.apps.googleusercontent.com",
            "google_client_secret": "live-secret",
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    ).raise_for_status()

    r = client.get("/gmail/auth-url")
    assert r.status_code == 200, r.text
    assert captured["client_id"] == "live-id.apps.googleusercontent.com"
    assert captured["source"] == "settings"


def test_env_vars_work_as_fallback_when_settings_absent(gmail_settings_client):
    client, gmail_client, _ = gmail_settings_client
    os.environ["GOOGLE_CLIENT_ID"] = "env-id.apps.googleusercontent.com"
    os.environ["GOOGLE_CLIENT_SECRET"] = "env-secret"
    os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:8000/gmail/oauth/callback"
    try:
        body = client.get("/gmail/status").json()
        assert body["configured"] is True
        cfg = gmail_client.get_gmail_config()
        assert cfg.source == "environment"
        assert cfg.client_id == "env-id.apps.googleusercontent.com"
    finally:
        for k in (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_REDIRECT_URI",
        ):
            os.environ.pop(k, None)


def test_settings_take_precedence_over_env(gmail_settings_client):
    client, gmail_client, _ = gmail_settings_client
    os.environ["GOOGLE_CLIENT_ID"] = "env-id.apps.googleusercontent.com"
    os.environ["GOOGLE_CLIENT_SECRET"] = "env-secret"
    os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:8000/gmail/oauth/callback"
    try:
        client.put(
            "/settings/gmail-oauth",
            json={
                "google_client_id": "settings-id.apps.googleusercontent.com",
                "google_client_secret": "settings-secret",
                "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
            },
        ).raise_for_status()
        cfg = gmail_client.get_gmail_config()
        assert cfg.source == "settings"
        assert cfg.client_id == "settings-id.apps.googleusercontent.com"
        assert cfg.client_secret == "settings-secret"
    finally:
        for k in (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GOOGLE_REDIRECT_URI",
        ):
            os.environ.pop(k, None)


def test_default_token_path_when_unset(gmail_settings_client):
    client, gmail_client, _ = gmail_settings_client
    # The settings_env fixture sets GMAIL_TOKEN_PATH for token isolation;
    # clear it again to exercise the default-path branch.
    os.environ.pop("GMAIL_TOKEN_PATH", None)
    client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "set-id.apps.googleusercontent.com",
            "google_client_secret": "set-secret",
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    ).raise_for_status()
    cfg = gmail_client.get_gmail_config()
    assert cfg.token_path.name == "token.json"
    assert "candidate_context" in cfg.token_path.parts
    assert "gmail" in cfg.token_path.parts


# ---- GET / PUT / DELETE endpoint shape -----------------------------------


def test_get_settings_returns_none_when_unconfigured(gmail_settings_client):
    client, _, _ = gmail_settings_client
    body = client.get("/settings/gmail-oauth").json()
    assert body["configured"] is False
    assert body["source"] == "none"
    assert body["has_google_client_secret"] is False
    assert body["google_client_secret_preview"] == ""


def test_get_settings_never_returns_plaintext_secret(gmail_settings_client):
    client, _, _ = gmail_settings_client
    secret = "super-secret-do-not-leak-1234"
    client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "x.apps.googleusercontent.com",
            "google_client_secret": secret,
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    ).raise_for_status()
    body = client.get("/settings/gmail-oauth").json()
    assert body["configured"] is True
    assert body["source"] == "settings"
    assert body["has_google_client_secret"] is True
    # Bullets, never the real secret.
    assert body["google_client_secret_preview"] == "•" * 8
    assert secret not in body["google_client_secret_preview"]
    # And the raw secret must not appear anywhere in the response body.
    assert secret not in str(body)


def test_get_settings_shows_env_source_without_exposing_env_secret(
    gmail_settings_client,
):
    client, _, _ = gmail_settings_client
    os.environ["GOOGLE_CLIENT_ID"] = "env-id.apps.googleusercontent.com"
    os.environ["GOOGLE_CLIENT_SECRET"] = "env-only-secret-987"
    try:
        body = client.get("/settings/gmail-oauth").json()
        assert body["source"] == "environment"
        assert body["has_google_client_secret"] is True
        assert body["google_client_secret_preview"] == "from environment"
        assert "env-only-secret-987" not in str(body)
    finally:
        os.environ.pop("GOOGLE_CLIENT_ID", None)
        os.environ.pop("GOOGLE_CLIENT_SECRET", None)


def test_put_settings_does_not_log_client_secret(
    gmail_settings_client, caplog
):
    client, _, _ = gmail_settings_client
    secret = "ultra-confidential-9999-do-not-log"
    with caplog.at_level(logging.DEBUG):
        client.put(
            "/settings/gmail-oauth",
            json={
                "google_client_id": "x.apps.googleusercontent.com",
                "google_client_secret": secret,
                "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
            },
        ).raise_for_status()
    for record in caplog.records:
        assert secret not in record.getMessage()


def test_put_requires_client_id(gmail_settings_client):
    client, _, _ = gmail_settings_client
    r = client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "",
            "google_client_secret": "x",
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    )
    assert r.status_code == 422


def test_put_requires_secret_unless_preserve(gmail_settings_client):
    client, _, _ = gmail_settings_client
    r = client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "x.apps.googleusercontent.com",
            "google_client_secret": "",
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    )
    assert r.status_code == 400, r.text


def test_put_preserve_existing_secret(gmail_settings_client):
    client, _, gmail_settings = gmail_settings_client
    client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "x.apps.googleusercontent.com",
            "google_client_secret": "original-secret",
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    ).raise_for_status()

    # Rotate the redirect URI without touching the secret.
    r = client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "x.apps.googleusercontent.com",
            "google_client_secret": None,
            "google_redirect_uri": "http://localhost:9000/gmail/oauth/callback",
            "preserve_existing_secret": True,
        },
    )
    assert r.status_code == 200, r.text

    stored = gmail_settings.get_stored_config()
    assert stored is not None
    assert stored.google_client_secret == "original-secret"
    assert stored.google_redirect_uri == "http://localhost:9000/gmail/oauth/callback"


def test_delete_removes_settings_row(gmail_settings_client):
    client, _, gmail_settings = gmail_settings_client
    client.put(
        "/settings/gmail-oauth",
        json={
            "google_client_id": "x.apps.googleusercontent.com",
            "google_client_secret": "secret-x",
            "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
        },
    ).raise_for_status()
    assert gmail_settings.has_stored_config() is True

    r = client.delete("/settings/gmail-oauth")
    assert r.status_code == 200, r.text
    assert gmail_settings.has_stored_config() is False
    # And the GET endpoint now reports unconfigured.
    body = client.get("/settings/gmail-oauth").json()
    assert body["configured"] is False
    assert body["source"] == "none"


# ---- Missing-config error wording ---------------------------------------


def test_auth_url_error_mentions_settings_or_env(gmail_settings_client):
    client, _, _ = gmail_settings_client
    r = client.get("/gmail/auth-url")
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    # The structured fields still name the env vars; the
    # human-readable text in the install docs / settings card directs
    # the user to either save settings or set env vars + restart.
    assert detail["error"] == "gmail_oauth_not_configured"
    assert "GOOGLE_CLIENT_ID" in detail["missing"]


# ---- Gitignore safety ---------------------------------------------------


def test_gitignore_excludes_settings_secret_files():
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text()
    assert "candidate_context/settings/gmail_oauth.json" in gitignore
    assert "candidate_context/settings/*.secret.json" in gitignore
