"""Tests for the read-only Gmail OAuth + test-search surface (task 082).

These tests **never** hit the real Gmail API. The :mod:`app.gmail_client`
module is monkey-patched (or driven through its on-disk token file) so
the full HTTP surface can be exercised without google libraries
installed or any real Google credentials.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


# ---- Local client fixture ---------------------------------------------
#
# The repo-wide ``client`` fixture from conftest.py runs before any env
# var changes can be picked up. This fixture is the same idea but also
# sets the Gmail-related env vars (GOOGLE_CLIENT_ID, ...) and points the
# token path at a tempdir so a connected/disconnected state can be
# simulated per test.


@pytest.fixture()
def gmail_env(tmp_path: Path) -> Iterator[dict[str, str]]:
    """Configure Gmail OAuth env vars for the duration of one test."""
    token_path = tmp_path / "gmail" / "token.json"
    env = {
        "GOOGLE_CLIENT_ID": "fake-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "fake-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/gmail/oauth/callback",
        "GMAIL_TOKEN_PATH": str(token_path),
    }
    prior = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        yield env
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.fixture()
def gmail_client_app(gmail_env, tmp_path: Path):
    """Yield (TestClient, gmail_client module) wired to ``gmail_env``."""
    from fastapi.testclient import TestClient

    # Mirror conftest.client's strategy: point the DB at a tempfile and
    # reload the app modules so they pick up the env vars.
    db_file = tmp_path / "gmail-tests.db"
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
        "app.settings",
        "app.schemas",
        "app.models",
        "app.db",
        "app",
    ]:
        sys.modules.pop(mod_name, None)

    from app.main import app  # noqa: E402
    from app import gmail_client  # noqa: E402

    with TestClient(app) as c:
        yield c, gmail_client

    import shutil

    shutil.rmtree(master_resumes_dir, ignore_errors=True)


# ---- /gmail/status ----------------------------------------------------


def test_status_reports_disconnected_when_no_token(gmail_client_app):
    client, _ = gmail_client_app
    r = client.get("/gmail/status")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "connected": False,
        "email": None,
        "scopes": [],
        "token_path_configured": True,
        "last_checked_at": None,
    }


def test_status_reports_connected_when_valid_token_exists(gmail_client_app):
    client, gmail_client = gmail_client_app
    gmail_client.save_token(
        {
            "token": "fake-access",
            "refresh_token": "fake-refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id.apps.googleusercontent.com",
            "client_secret": "fake-client-secret",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
    )
    body = client.get("/gmail/status").json()
    assert body["connected"] is True
    assert body["email"] == "calvin@example.com"
    assert body["scopes"] == [gmail_client.GMAIL_READONLY_SCOPE]
    assert body["token_path_configured"] is True
    assert body["last_checked_at"] is not None


def test_status_rejects_stored_token_with_forbidden_scope(gmail_client_app):
    client, gmail_client = gmail_client_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [
                gmail_client.GMAIL_READONLY_SCOPE,
                "https://www.googleapis.com/auth/gmail.send",
            ],
        }
    )
    body = client.get("/gmail/status").json()
    assert body["connected"] is False


# ---- /gmail/auth-url --------------------------------------------------


def test_auth_url_returns_url_and_readonly_scope(gmail_client_app, monkeypatch):
    client, gmail_client = gmail_client_app
    monkeypatch.setattr(
        gmail_client,
        "build_auth_url",
        lambda state=None: {
            "auth_url": "https://accounts.google.com/o/oauth2/auth?fake",
            "scope": gmail_client.GMAIL_READONLY_SCOPE,
        },
    )
    body = client.get("/gmail/auth-url").json()
    assert body["auth_url"].startswith("https://accounts.google.com/")
    assert body["scope"] == gmail_client.GMAIL_READONLY_SCOPE
    assert body["scope"] == "https://www.googleapis.com/auth/gmail.readonly"


def test_auth_url_returns_400_when_oauth_not_configured(gmail_client_app, monkeypatch):
    client, _ = gmail_client_app
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    r = client.get("/gmail/auth-url")
    assert r.status_code == 400


# ---- /gmail/oauth/callback -------------------------------------------


def test_oauth_callback_stores_token(gmail_client_app, monkeypatch):
    client, gmail_client = gmail_client_app

    captured: dict[str, str] = {}

    def fake_exchange(code: str) -> dict:
        captured["code"] = code
        token = {
            "token": "from-fake-exchange",
            "refresh_token": "refresh",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
        gmail_client.save_token(token)
        return token

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    r = client.get("/gmail/oauth/callback", params={"code": "abc-123"})
    assert r.status_code == 200
    assert "Gmail connected" in r.text
    assert captured == {"code": "abc-123"}

    # The status endpoint now reports connected because the token file exists.
    body = client.get("/gmail/status").json()
    assert body["connected"] is True
    assert body["email"] == "calvin@example.com"


def test_oauth_callback_rejects_missing_code(gmail_client_app):
    client, _ = gmail_client_app
    r = client.get("/gmail/oauth/callback")
    assert r.status_code == 400


def test_oauth_callback_renders_error_from_google(gmail_client_app):
    client, _ = gmail_client_app
    r = client.get("/gmail/oauth/callback", params={"error": "access_denied"})
    assert r.status_code == 400
    assert "access_denied" in r.text


# ---- /gmail/test-search ----------------------------------------------


def test_test_search_requires_connection(gmail_client_app):
    client, _ = gmail_client_app
    r = client.post(
        "/gmail/test-search",
        json={"query": "newer_than:7d", "max_results": 5},
    )
    assert r.status_code == 409


def test_test_search_returns_metadata_only(gmail_client_app, monkeypatch):
    client, gmail_client = gmail_client_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
    )

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m1",
                "thread_id": "t1",
                "subject": "Thanks for applying",
                "from": "talent@example.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "We received your application.",
            },
            {
                "id": "m2",
                "thread_id": "t2",
                "subject": "Interview invite",
                "from": "recruiter@example.com",
                "date": "Tue, 26 May 2026 09:00:00 +0000",
                "snippet": "Can you chat Friday?",
            },
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    r = client.post(
        "/gmail/test-search",
        json={"query": "newer_than:7d", "max_results": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is True
    assert body["query"] == "newer_than:7d"
    assert body["count"] == 2
    assert {m["id"] for m in body["messages"]} == {"m1", "m2"}

    # The response shape includes only safe metadata and snippet — no
    # body, html, attachments, or raw payload.
    for msg in body["messages"]:
        assert set(msg.keys()) == {
            "id",
            "thread_id",
            "subject",
            "from",
            "date",
            "snippet",
        }


def test_test_search_caps_max_results(gmail_client_app, monkeypatch):
    client, gmail_client = gmail_client_app
    gmail_client.save_token(
        {"token": "fake", "scopes": [gmail_client.GMAIL_READONLY_SCOPE]}
    )

    seen: dict[str, int] = {}

    def fake_search(query: str, max_results: int):
        seen["max_results"] = max_results
        return []

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    client.post(
        "/gmail/test-search",
        json={"query": "newer_than:7d", "max_results": 9999},
    )
    assert seen["max_results"] == gmail_client.MAX_TEST_SEARCH_RESULTS
    assert gmail_client.MAX_TEST_SEARCH_RESULTS == 10


# ---- Scope policy ----------------------------------------------------


def test_only_readonly_scope_is_requested(gmail_client_app):
    _, gmail_client = gmail_client_app
    assert gmail_client.GMAIL_SCOPES == (
        "https://www.googleapis.com/auth/gmail.readonly",
    )


def test_forbidden_scopes_are_rejected(gmail_client_app):
    _, gmail_client = gmail_client_app
    for s in (
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.labels",
        "https://mail.google.com/",
    ):
        with pytest.raises(gmail_client.GmailScopeError):
            gmail_client.assert_readonly_scope([s])


def test_assert_readonly_scope_accepts_readonly(gmail_client_app):
    _, gmail_client = gmail_client_app
    # Should not raise.
    gmail_client.assert_readonly_scope([gmail_client.GMAIL_READONLY_SCOPE])


# ---- Module import safety -------------------------------------------


def test_app_main_import_does_not_load_google_libraries(gmail_client_app):
    """``app.main`` must remain importable without google deps loaded.

    Task 080 introduced ``test_no_gmail_outbound_modules_imported`` which
    enforces this; we re-assert here at the task-082 surface so a future
    refactor that accidentally hoists a top-level google import is caught
    here too.
    """
    forbidden_prefixes = (
        "googleapiclient",
        "google.auth",
        "google_auth_oauthlib",
        "smtplib",
        "imaplib",
        "poplib",
    )
    leaked = [
        name
        for name in sys.modules
        if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)
    ]
    assert leaked == [], leaked


def test_gmail_client_import_does_not_load_google_libraries(gmail_client_app):
    """Importing :mod:`app.gmail_client` directly must also stay lazy."""
    # gmail_client_app already imported it; just check nothing leaked.
    forbidden_prefixes = (
        "googleapiclient",
        "google.auth",
        "google_auth_oauthlib",
    )
    leaked = [
        name
        for name in sys.modules
        if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)
    ]
    assert leaked == [], leaked


# ---- Token file safety ----------------------------------------------


def test_default_token_path_lives_under_candidate_context(gmail_client_app, monkeypatch):
    _, gmail_client = gmail_client_app
    monkeypatch.delenv("GMAIL_TOKEN_PATH", raising=False)
    cfg = gmail_client.get_gmail_config()
    parts = cfg.token_path.parts
    assert "candidate_context" in parts
    assert "gmail" in parts
    assert cfg.token_path.name == "token.json"


def test_gitignore_excludes_gmail_token_files():
    """The repo .gitignore must keep local OAuth tokens out of git."""
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text()
    assert "candidate_context/gmail/token.json" in gitignore
    assert "candidate_context/gmail/*.json" in gitignore


def test_save_token_writes_file_atomically(gmail_client_app):
    _, gmail_client = gmail_client_app
    path = gmail_client.save_token({"token": "abc", "scopes": []})
    assert path.is_file()
    assert json.loads(path.read_text())["token"] == "abc"


# ---- HTTP-surface safety ---------------------------------------------


def test_no_send_archive_delete_label_routes(gmail_client_app):
    """Task 082 must not expose any write-side Gmail action."""
    client, _ = gmail_client_app
    paths = [getattr(r, "path", "") for r in client.app.routes]
    suspicious = (
        "/gmail/send",
        "/gmail/archive",
        "/gmail/delete",
        "/gmail/label",
        "/gmail/modify",
        "/gmail/trash",
        "/gmail/draft",
        "/gmail/reply",
    )
    for needle in suspicious:
        assert not any(needle in p for p in paths), needle
