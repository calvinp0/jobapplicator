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
        "configured": True,
        "missing_config": [],
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
    assert body["configured"] is True
    assert body["missing_config"] == []
    assert body["email"] == "calvin@example.com"
    assert body["scopes"] == [gmail_client.GMAIL_READONLY_SCOPE]
    assert body["token_path_configured"] is True
    assert body["last_checked_at"] is not None


def test_status_reports_not_configured_when_oauth_env_missing(
    gmail_client_app, monkeypatch
):
    client, _ = gmail_client_app
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    body = client.get("/gmail/status").json()
    assert body["connected"] is False
    assert body["configured"] is False
    assert body["missing_config"] == [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
    ]


def test_status_reports_configured_when_required_env_present(
    gmail_client_app,
):
    # ``gmail_client_app`` already sets all three env vars; no token saved.
    client, _ = gmail_client_app
    body = client.get("/gmail/status").json()
    assert body["configured"] is True
    assert body["missing_config"] == []
    assert body["connected"] is False


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
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    r = client.get("/gmail/auth-url")
    assert r.status_code == 400


def test_auth_url_returns_structured_error_when_config_missing(
    gmail_client_app, monkeypatch
):
    client, _ = gmail_client_app
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)
    r = client.get("/gmail/auth-url")
    assert r.status_code == 400
    body = r.json()
    detail = body["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "gmail_oauth_not_configured"
    assert "GOOGLE_CLIENT_ID" in detail["message"]
    assert detail["missing"] == [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
    ]


# ---- /gmail/oauth/callback -------------------------------------------


def test_oauth_callback_stores_token(gmail_client_app, monkeypatch):
    client, gmail_client = gmail_client_app

    captured: dict[str, str] = {}

    def fake_exchange(code: str, state: str | None = None) -> dict:
        captured["code"] = code
        captured["state"] = state or ""
        token = {
            "token": "from-fake-exchange",
            "refresh_token": "refresh",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
        gmail_client.save_token(token)
        return token

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    r = client.get(
        "/gmail/oauth/callback",
        params={"code": "abc-123", "state": "state-xyz"},
    )
    assert r.status_code == 200
    assert "Gmail connected" in r.text
    assert captured == {"code": "abc-123", "state": "state-xyz"}

    # The status endpoint now reports connected because the token file exists.
    body = client.get("/gmail/status").json()
    assert body["connected"] is True
    assert body["email"] == "calvin@example.com"


def test_oauth_callback_rejects_missing_code(gmail_client_app):
    client, _ = gmail_client_app
    r = client.get("/gmail/oauth/callback", params={"state": "abc"})
    assert r.status_code == 400
    assert "missing" in r.text.lower()
    assert "code" in r.text.lower()


def test_oauth_callback_rejects_missing_state(gmail_client_app):
    client, _ = gmail_client_app
    r = client.get("/gmail/oauth/callback", params={"code": "abc"})
    assert r.status_code == 400
    assert "state" in r.text.lower()


def test_oauth_callback_renders_error_from_google(gmail_client_app):
    client, _ = gmail_client_app
    r = client.get("/gmail/oauth/callback", params={"error": "access_denied"})
    assert r.status_code == 400
    assert "access_denied" in r.text


# ---- /gmail/auth-url state + PKCE persistence ------------------------


def test_auth_url_persists_state_and_code_verifier(gmail_client_app, monkeypatch):
    """Calling /gmail/auth-url must persist state + PKCE verifier locally."""
    client, gmail_client = gmail_client_app

    class FakeFlow:
        code_verifier: str | None = None

        @classmethod
        def from_client_config(cls, *args, **kwargs):
            inst = cls()
            inst.code_verifier = "fake-verifier-43-chars-min-aaaaaaaaaaaaaaaaa"
            return inst

        def authorization_url(self, **kwargs):
            return (
                "https://accounts.google.com/o/oauth2/auth?fake=1",
                "generated-state-token",
            )

    import sys
    import types

    fake_module = types.ModuleType("google_auth_oauthlib.flow")
    fake_module.Flow = FakeFlow  # type: ignore[attr-defined]
    pkg = types.ModuleType("google_auth_oauthlib")
    pkg.flow = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", pkg)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", fake_module)

    body = client.get("/gmail/auth-url").json()
    assert body["auth_url"].startswith("https://accounts.google.com/")
    assert body["scope"] == gmail_client.GMAIL_READONLY_SCOPE

    pending = gmail_client.load_oauth_state()
    assert pending is not None
    assert pending["state"] == "generated-state-token"
    assert pending["code_verifier"] == "fake-verifier-43-chars-min-aaaaaaaaaaaaaaaaa"
    assert pending["scope"] == gmail_client.GMAIL_READONLY_SCOPE
    assert pending["redirect_uri"] == "http://localhost:8000/gmail/oauth/callback"
    assert "created_at" in pending


def test_exchange_code_restores_code_verifier(gmail_client_app, monkeypatch):
    """``exchange_code`` must restore the persisted verifier before fetch_token."""
    _, gmail_client = gmail_client_app

    gmail_client.save_oauth_state(
        state="state-xyz",
        code_verifier="verifier-xyz",
        redirect_uri="http://localhost:8000/gmail/oauth/callback",
        scope=gmail_client.GMAIL_READONLY_SCOPE,
    )

    captured: dict[str, object] = {}

    class FakeCredentials:
        token = "access"
        refresh_token = "refresh"
        token_uri = "https://oauth2.googleapis.com/token"
        client_id = "fake-id"
        client_secret = "fake-secret"
        scopes = [gmail_client.GMAIL_READONLY_SCOPE]
        expiry = None

    class FakeFlow:
        code_verifier: str | None = None

        @classmethod
        def from_client_config(cls, *args, **kwargs):
            inst = cls()
            inst.code_verifier = None
            return inst

        def fetch_token(self, **kwargs):
            captured["verifier_at_fetch"] = self.code_verifier
            captured["code"] = kwargs.get("code")

        @property
        def credentials(self):
            return FakeCredentials()

    import sys
    import types

    fake_module = types.ModuleType("google_auth_oauthlib.flow")
    fake_module.Flow = FakeFlow  # type: ignore[attr-defined]
    pkg = types.ModuleType("google_auth_oauthlib")
    pkg.flow = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", pkg)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", fake_module)

    # Skip the network getProfile call.
    monkeypatch.setattr(gmail_client, "_fetch_profile_email", lambda creds: None)

    token = gmail_client.exchange_code("auth-code", state="state-xyz")
    assert captured["verifier_at_fetch"] == "verifier-xyz"
    assert captured["code"] == "auth-code"
    assert token["token"] == "access"

    # State file is cleared after success.
    assert gmail_client.load_oauth_state() is None


def test_exchange_code_rejects_state_mismatch(gmail_client_app):
    _, gmail_client = gmail_client_app
    gmail_client.save_oauth_state(
        state="state-xyz",
        code_verifier="verifier",
        redirect_uri="http://localhost:8000/gmail/oauth/callback",
        scope=gmail_client.GMAIL_READONLY_SCOPE,
    )
    with pytest.raises(gmail_client.GmailOAuthStateError):
        gmail_client.exchange_code("code", state="WRONG")


def test_exchange_code_rejects_missing_state_when_expected(gmail_client_app):
    _, gmail_client = gmail_client_app
    gmail_client.save_oauth_state(
        state="state-xyz",
        code_verifier="verifier",
        redirect_uri="http://localhost:8000/gmail/oauth/callback",
        scope=gmail_client.GMAIL_READONLY_SCOPE,
    )
    with pytest.raises(gmail_client.GmailOAuthStateError):
        gmail_client.exchange_code("code", state=None)


def test_exchange_code_rejects_missing_pending_state(gmail_client_app):
    _, gmail_client = gmail_client_app
    # No pending state on disk at all.
    with pytest.raises(gmail_client.GmailOAuthStateError):
        gmail_client.exchange_code("code", state="anything")


def test_exchange_code_rejects_expired_state(gmail_client_app, monkeypatch):
    _, gmail_client = gmail_client_app
    gmail_client.save_oauth_state(
        state="state-xyz",
        code_verifier="verifier",
        redirect_uri="http://localhost:8000/gmail/oauth/callback",
        scope=gmail_client.GMAIL_READONLY_SCOPE,
    )
    # Force the stored state to look ancient.
    monkeypatch.setattr(
        gmail_client,
        "_oauth_state_age_seconds",
        lambda blob: gmail_client.OAUTH_STATE_TTL_SECONDS + 1,
    )
    with pytest.raises(gmail_client.GmailOAuthStateError):
        gmail_client.exchange_code("code", state="state-xyz")
    # Expired state is cleared.
    assert gmail_client.load_oauth_state() is None


def test_exchange_code_wraps_invalid_grant_in_friendly_error(
    gmail_client_app, monkeypatch
):
    _, gmail_client = gmail_client_app
    gmail_client.save_oauth_state(
        state="state-xyz",
        code_verifier="verifier",
        redirect_uri="http://localhost:8000/gmail/oauth/callback",
        scope=gmail_client.GMAIL_READONLY_SCOPE,
    )

    class FakeInvalidGrant(Exception):
        pass

    class FakeFlow:
        code_verifier: str | None = None

        @classmethod
        def from_client_config(cls, *args, **kwargs):
            return cls()

        def fetch_token(self, **kwargs):
            raise FakeInvalidGrant("(invalid_grant) Missing code verifier.")

    import sys
    import types

    fake_module = types.ModuleType("google_auth_oauthlib.flow")
    fake_module.Flow = FakeFlow  # type: ignore[attr-defined]
    pkg = types.ModuleType("google_auth_oauthlib")
    pkg.flow = fake_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib", pkg)
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", fake_module)

    with pytest.raises(gmail_client.GmailOAuthExchangeError) as excinfo:
        gmail_client.exchange_code("code", state="state-xyz")
    assert "invalid_grant" in str(excinfo.value).lower()
    # State is cleared on failure so the next attempt starts clean.
    assert gmail_client.load_oauth_state() is None


def test_callback_returns_friendly_html_for_invalid_grant(
    gmail_client_app, monkeypatch
):
    """A failed token exchange must not surface as a generic 500."""
    client, gmail_client = gmail_client_app

    def fake_exchange(code: str, state: str | None = None) -> dict:
        raise gmail_client.GmailOAuthExchangeError(
            "Google rejected the OAuth code exchange: "
            "(invalid_grant) Missing code verifier."
        )

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    r = client.get(
        "/gmail/oauth/callback",
        params={"code": "abc", "state": "state-xyz"},
    )
    assert r.status_code == 400
    assert "invalid_grant" in r.text
    assert "Gmail connection failed" in r.text
    assert "Settings" in r.text


def test_callback_returns_friendly_html_for_missing_state(
    gmail_client_app, monkeypatch
):
    client, gmail_client = gmail_client_app

    def fake_exchange(code: str, state: str | None = None) -> dict:
        raise gmail_client.GmailOAuthStateError(
            "missing or expired OAuth state. Return to Settings and "
            "click Connect Gmail again."
        )

    monkeypatch.setattr(gmail_client, "exchange_code", fake_exchange)

    r = client.get(
        "/gmail/oauth/callback",
        params={"code": "abc", "state": "stale"},
    )
    assert r.status_code == 400
    assert "Gmail connection failed" in r.text
    assert "Settings" in r.text


def test_callback_returns_friendly_html_for_missing_config(
    gmail_client_app, monkeypatch
):
    client, _ = gmail_client_app
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    r = client.get(
        "/gmail/oauth/callback",
        params={"code": "abc", "state": "state-xyz"},
    )
    assert r.status_code == 400
    assert "Gmail connection failed" in r.text


# ---- OAuth-state file safety -----------------------------------------


def test_gitignore_excludes_oauth_state_file():
    """The repo .gitignore must keep the pending OAuth state out of git."""
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text()
    # candidate_context/gmail/*.json covers oauth_state.json too.
    assert "candidate_context/gmail/*.json" in gitignore
    assert "candidate_context/gmail/oauth_state.json" in gitignore


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
