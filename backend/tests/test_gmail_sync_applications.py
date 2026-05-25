"""Tests for the manual Gmail sync endpoint (task 086).

The endpoint searches Gmail (read-only) across all relevant
applications, classifies the top candidate per application, and
returns a summary. These tests exercise the route through a TestClient
with a monkey-patched :mod:`app.gmail_client` so no real Google
credentials or network round-trip is required.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture()
def gmail_env(tmp_path: Path) -> Iterator[dict[str, str]]:
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
def sync_app(gmail_env, tmp_path: Path):
    from fastapi.testclient import TestClient

    db_file = tmp_path / "sync-tests.db"
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
        "app.gmail_application_search",
        "app.gmail_application_classifier",
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


def _make_job(client, *, company: str, title: str) -> dict:
    payload = {
        "source_platform": "linkedin",
        "company": company,
        "title": title,
        "description_text": "Do work.",
    }
    return client.post("/jobs", json=payload).json()


def _make_application(
    client, *, company: str = "Example Aero Labs",
    title: str = "Scientific Machine Learning Engineer",
    submit: bool = True,
) -> dict:
    job = _make_job(client, company=company, title=title)
    app_obj = client.post(
        "/applications", json={"job_id": job["id"], "status": "draft"}
    ).json()
    if submit:
        app_obj = client.post(f"/applications/{app_obj['id']}/submit").json()
    return app_obj


def _set_app_status(app_id: str, status: str) -> None:
    """Directly set an application's status via SQLite for cases the
    public API does not cover (``withdrawn``, ``approved``, etc.)."""
    import sqlite3

    db_path = os.environ["JOBAPPLY_DATABASE_URL"].replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE applications SET status=? WHERE id=?", (status, app_id)
        )
        conn.commit()
    finally:
        conn.close()


def _connect(gmail_client) -> None:
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
    )


# ---- Connectivity ------------------------------------------------------


def test_sync_requires_gmail_connection(sync_app):
    client, _ = sync_app
    _make_application(client)

    r = client.post("/gmail/sync-applications", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gmail_connected"] is False
    assert "Connect Gmail" in (body.get("message") or "")
    assert body["checked_count"] == 0


# ---- Selection rules ---------------------------------------------------


def test_sync_includes_submitted_applications(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    app_obj = _make_application(client, company="Acme", title="Engineer")

    r = client.post("/gmail/sync-applications", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [res["application_id"] for res in body["results"]]
    assert app_obj["id"] in ids


def test_sync_includes_interview_and_response_received(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    interview_app = _make_application(client, company="Acme", title="Eng")
    client.post(f"/applications/{interview_app['id']}/mark-interview")

    rr_app = _make_application(client, company="Beta", title="Lead")
    _set_app_status(rr_app["id"], "response_received")

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    ids = {res["application_id"] for res in body["results"]}
    assert interview_app["id"] in ids
    assert rr_app["id"] in ids


def test_sync_excludes_draft_by_default(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    job = _make_job(client, company="Acme", title="Engineer")
    draft_app = client.post(
        "/applications", json={"job_id": job["id"], "status": "draft"}
    ).json()

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    ids = [res["application_id"] for res in body["results"]]
    assert draft_app["id"] not in ids


def test_sync_excludes_rejected_approved_withdrawn_by_default(
    sync_app, monkeypatch
):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    rejected_app = _make_application(client, company="A", title="X")
    client.post(f"/applications/{rejected_app['id']}/mark-rejected")

    approved_app = _make_application(client, company="B", title="Y", submit=False)
    _set_app_status(approved_app["id"], "approved")

    withdrawn_app = _make_application(client, company="C", title="Z")
    _set_app_status(withdrawn_app["id"], "withdrawn")

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    ids = [res["application_id"] for res in body["results"]]
    assert rejected_app["id"] not in ids
    assert approved_app["id"] not in ids
    assert withdrawn_app["id"] not in ids


def test_sync_include_terminal_picks_up_rejected(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    rejected_app = _make_application(client, company="A", title="X")
    client.post(f"/applications/{rejected_app['id']}/mark-rejected")

    r = client.post(
        "/gmail/sync-applications", json={"include_terminal": True}
    )
    body = r.json()
    ids = [res["application_id"] for res in body["results"]]
    assert rejected_app["id"] in ids


def test_sync_include_terminal_does_not_include_withdrawn(
    sync_app, monkeypatch
):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    withdrawn_app = _make_application(client, company="C", title="Z")
    _set_app_status(withdrawn_app["id"], "withdrawn")

    r = client.post(
        "/gmail/sync-applications", json={"include_terminal": True}
    )
    body = r.json()
    ids = [res["application_id"] for res in body["results"]]
    assert withdrawn_app["id"] not in ids


# ---- Caps --------------------------------------------------------------


def test_sync_caps_max_applications(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    for i in range(5):
        _make_application(client, company=f"Co {i}", title=f"Eng {i}")

    r = client.post(
        "/gmail/sync-applications", json={"max_applications": 2}
    )
    body = r.json()
    assert body["checked_count"] == 2
    assert len(body["results"]) == 2


def test_sync_caps_max_results_per_application(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)

    seen: dict[str, int] = {}

    def fake_search(query: str, max_results: int):
        seen["max_results"] = max_results
        return []

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    _make_application(client, company="Acme", title="Engineer")

    # Asking for the explicit ceiling (10) must reach the Gmail client
    # unchanged; that confirms the route's outer cap is honored.
    client.post(
        "/gmail/sync-applications",
        json={"max_results_per_application": 10},
    )
    assert seen["max_results"] == 10

    # Anything above the ceiling is rejected at the schema layer so the
    # user gets a clear 422 instead of a silent clamp.
    r = client.post(
        "/gmail/sync-applications",
        json={"max_results_per_application": 11},
    )
    assert r.status_code == 422


def test_sync_rejects_oversized_max_applications(sync_app, monkeypatch):
    """Request validation should reject ``max_applications`` above the
    explicit ceiling so the user gets a clear 422 instead of a silent
    clamp."""
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    r = client.post(
        "/gmail/sync-applications", json={"max_applications": 9999}
    )
    assert r.status_code == 422


# ---- Result behavior ---------------------------------------------------


def test_sync_no_match_updates_check_at_and_email_status(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    app_obj = _make_application(client, company="Acme", title="Engineer")

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    assert body["no_match_count"] == 1
    result = body["results"][0]
    assert result["new_email_status"] == "no_match"

    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["last_gmail_check_at"] is not None
    assert reloaded["email_status"] == "no_match"


def test_sync_classifies_rejection_with_evidence(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m-reject",
                "thread_id": "t1",
                "subject": "Update on your application",
                "from": "jobs@exampleaerolabs.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": (
                    "Unfortunately we will not be moving forward with your "
                    "application for the Scientific Machine Learning Engineer "
                    "role at Example Aero Labs."
                ),
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    assert body["updated_count"] == 1
    result = body["results"][0]
    assert result["classification"] == "rejection"
    assert result["new_application_status"] == "rejected"
    assert result["application_status_changed"] is True
    assert any(
        "moving forward" in ev["text"].lower() for ev in result["evidence"]
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "rejected"
    assert reloaded["email_status"] == "classified_rejection"


def test_sync_classifies_interview_with_evidence(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m-interview",
                "thread_id": "t1",
                "subject": "Phone screen with our team",
                "from": "recruiting@exampleaerolabs.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": (
                    "We'd love to schedule an interview about the Scientific "
                    "Machine Learning Engineer role at Example Aero Labs."
                ),
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    result = body["results"][0]
    assert result["classification"] == "interview_request"
    assert result["new_application_status"] == "interview"
    assert result["application_status_changed"] is True
    assert result["evidence"]
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "interview"


def test_sync_does_not_change_withdrawn_application(sync_app, monkeypatch):
    """``withdrawn`` is excluded entirely from sync — even when
    ``include_terminal=true`` and the (mocked) classifier would otherwise
    fire."""
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m-x",
                "subject": "Update on your application",
                "from": "jobs@example.com",
                "date": "",
                "snippet": "Unfortunately we will not be moving forward.",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    _set_app_status(app_obj["id"], "withdrawn")

    r = client.post(
        "/gmail/sync-applications", json={"include_terminal": True}
    )
    body = r.json()
    ids = [res["application_id"] for res in body["results"]]
    assert app_obj["id"] not in ids

    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "withdrawn"


def test_sync_response_includes_summary_counts(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        if "Acme" in query:
            return []
        return [
            {
                "id": "m-other",
                "subject": "Some unrelated subject",
                "from": "noreply@example.com",
                "date": "",
                "snippet": "Hello there",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    _make_application(client, company="Acme", title="Engineer")
    _make_application(client, company="Beta", title="Lead")

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    assert set(body.keys()) >= {
        "gmail_connected",
        "checked_count",
        "updated_count",
        "no_match_count",
        "needs_review_count",
        "results",
    }
    assert body["checked_count"] == 2
    assert body["no_match_count"] == 1
    # The "unrelated" mock yields the ``unknown`` / ``newsletter_or_unrelated``
    # classifier label, which maps to needs_review and writes no EmailLink.
    assert body["needs_review_count"] >= 1


def test_sync_does_not_return_full_email_bodies(sync_app, monkeypatch):
    """The response must contain only metadata + evidence quotes."""
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m1",
                "subject": "Update",
                "from": "jobs@example.com",
                "date": "",
                "snippet": "Unfortunately we will not be moving forward.",
                "body": "FULL BODY MUST NOT LEAK",
                "html": "<html>NOPE</html>",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    _make_application(client)

    r = client.post("/gmail/sync-applications", json={})
    body = r.json()
    serialized = r.text
    assert "FULL BODY MUST NOT LEAK" not in serialized
    assert "NOPE" not in serialized
    for result in body["results"]:
        for ev in result["evidence"]:
            assert ev["field"] in {"subject", "from", "snippet"}
            assert "body" not in ev
            assert "html" not in ev


def test_sync_does_not_persist_full_email_bodies(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m-persist",
                "subject": "Update on your application",
                "from": "jobs@example.com",
                "date": "",
                "snippet": "Unfortunately we will not be moving forward.",
                "body": "FULL BODY MUST NOT LEAK",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    client.post("/gmail/sync-applications", json={})
    links = client.get(f"/applications/{app_obj['id']}/email-links").json()
    assert len(links) == 1
    link = links[0]
    assert "body" not in link
    assert "html" not in link
    for v in link.values():
        if isinstance(v, str):
            assert "FULL BODY MUST NOT LEAK" not in v


def test_sync_classify_false_skips_classification(sync_app, monkeypatch):
    client, gmail_client = sync_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m1",
                "subject": "Update on your application",
                "from": "jobs@example.com",
                "date": "",
                "snippet": "Unfortunately we will not be moving forward.",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    r = client.post("/gmail/sync-applications", json={"classify": False})
    body = r.json()
    result = body["results"][0]
    assert result["classification"] is None
    # The application's main status must not flip when classify=false.
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "submitted"
    # No EmailLink rows are written either.
    links = client.get(f"/applications/{app_obj['id']}/email-links").json()
    assert links == []


# ---- Safety guards ----------------------------------------------------


def test_no_gmail_write_routes_added_by_task_086(sync_app):
    client, _ = sync_app
    paths = [getattr(r, "path", "") for r in client.app.routes]
    forbidden = (
        "/gmail/send",
        "/gmail/archive",
        "/gmail/delete",
        "/gmail/label",
        "/gmail/modify",
        "/gmail/trash",
        "/gmail/draft",
        "/gmail/reply",
    )
    for needle in forbidden:
        assert not any(needle in p for p in paths), needle
    # The new endpoint is reachable.
    assert any(p == "/gmail/sync-applications" for p in paths)


def test_sync_module_imports_no_google_libraries():
    """The sync router itself must not pull google libs into the import
    graph; the gmail_client integration is lazy."""
    import importlib
    import sys as _sys

    importlib.import_module("app.routers.gmail")
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
        for name in _sys.modules
        if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)
    ]
    assert leaked == [], leaked


def test_sync_works_without_real_google_credentials(sync_app, monkeypatch):
    """End-to-end check that the test environment never needs google
    libraries to drive the sync route."""
    client, gmail_client = sync_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    _make_application(client)
    r = client.post("/gmail/sync-applications", json={})
    assert r.status_code == 200
