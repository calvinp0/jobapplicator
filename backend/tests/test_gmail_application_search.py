"""Tests for the Gmail application-search surface (task 083).

These tests cover:

- The pure query builder in
  :mod:`app.gmail_application_search` (no Gmail required).
- The deterministic match scorer.
- The ``POST /applications/{id}/gmail/search`` endpoint, driven through
  a monkey-patched :mod:`app.gmail_client` so no real Google credentials
  are needed and no network call is ever attempted.

The endpoint tests share the same module-reload + tempdir-token pattern
as ``test_gmail_oauth.py`` so the connected/disconnected state can be
flipped per test.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest


# ---- Pure query-builder tests -----------------------------------------


def test_query_builder_includes_company_and_title():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    q = build_application_query(
        ApplicationQueryInputs(
            company="Example Aero Labs",
            job_title="Scientific Machine Learning Engineer",
            submitted_at=None,
        )
    )
    assert '"Example Aero Labs"' in q
    assert '"Scientific Machine Learning Engineer"' in q


def test_query_builder_uses_submitted_at_after_clause():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    submitted = datetime(2026, 5, 25, 3, 0, tzinfo=timezone.utc)
    q = build_application_query(
        ApplicationQueryInputs(
            company="Acme",
            job_title="Engineer",
            submitted_at=submitted,
        )
    )
    # one-day buffer applied; 2026-05-24 is the cutoff.
    assert "after:2026/5/24" in q
    assert "newer_than" not in q


def test_query_builder_falls_back_to_newer_than_when_no_submitted_at():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    q = build_application_query(
        ApplicationQueryInputs(
            company="Acme",
            job_title="Engineer",
            submitted_at=None,
        )
    )
    assert "newer_than:180d" in q


def test_query_builder_includes_ats_terms_when_requested():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    q = build_application_query(
        ApplicationQueryInputs(
            company="Acme",
            job_title="Engineer",
            submitted_at=None,
            include_ats_terms=True,
        )
    )
    assert "from:greenhouse.io" in q
    assert "from:lever.co" in q


def test_query_builder_omits_ats_terms_when_disabled():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    q = build_application_query(
        ApplicationQueryInputs(
            company="Acme",
            job_title="Engineer",
            submitted_at=None,
            include_ats_terms=False,
        )
    )
    assert "greenhouse" not in q
    assert "lever.co" not in q


def test_query_builder_handles_missing_company_and_title_gracefully():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    # No primary terms at all → the query still produces a valid Gmail
    # filter (just the date clause + ATS sender clause).
    q = build_application_query(
        ApplicationQueryInputs(company=None, job_title=None, submitted_at=None)
    )
    assert "newer_than:180d" in q
    # Should not crash and should not produce a stray "OR" or empty parens.
    assert "()" not in q
    assert " OR )" not in q


def test_query_builder_includes_extra_terms_as_quoted_phrases():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    q = build_application_query(
        ApplicationQueryInputs(
            company="Acme",
            job_title="Engineer",
            submitted_at=None,
            extra_terms=("recruiter@acme", "Acme Labs offer"),
        )
    )
    assert '"recruiter@acme"' in q
    assert '"Acme Labs offer"' in q


def test_query_builder_strips_embedded_quotes_to_avoid_invalid_syntax():
    from app.gmail_application_search import (
        ApplicationQueryInputs,
        build_application_query,
    )

    q = build_application_query(
        ApplicationQueryInputs(
            company='Acme "Holdings"',
            job_title="Engineer",
            submitted_at=None,
        )
    )
    # No bare double-quote should appear adjacent to a word that would
    # break Gmail's parser.
    assert '"Acme Holdings"' in q


# ---- Scorer tests ------------------------------------------------------


def test_scorer_returns_matched_signals_and_deterministic_score():
    from app.gmail_application_search import MatchInputs, score_candidate

    message = {
        "id": "m1",
        "thread_id": "t1",
        "subject": "Thanks for applying to Acme",
        "from": "talent@acme.com",
        "date": "Mon, 25 May 2026 12:00:00 +0000",
        "snippet": "We received your Engineer application.",
    }
    inputs = MatchInputs(
        company="Acme",
        job_title="Engineer",
        submitted_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )
    score1, signals1 = score_candidate(message, inputs)
    score2, signals2 = score_candidate(message, inputs)

    assert score1 == score2
    assert signals1 == signals2
    assert "company_name" in signals1
    assert "job_title" in signals1
    assert "company_sender_domain" in signals1
    assert "after_submitted_at" in signals1
    assert 0.0 <= score1 <= 1.0
    # Multiple signals should push the score above the single-signal weight.
    assert score1 > 0.5


def test_scorer_ignores_unmatched_messages():
    from app.gmail_application_search import MatchInputs, score_candidate

    message = {
        "id": "m1",
        "subject": "Weekly newsletter",
        "from": "news@example.org",
        "date": "Mon, 25 May 2026 12:00:00 +0000",
        "snippet": "Top stories this week.",
    }
    score, signals = score_candidate(
        message,
        MatchInputs(company="Acme", job_title="Engineer", submitted_at=None),
    )
    assert signals == []
    assert score == 0.0


def test_scorer_credits_manual_term_once():
    from app.gmail_application_search import MatchInputs, score_candidate

    message = {
        "id": "m1",
        "subject": "Update on your candidacy",
        "from": "noreply@unknown.com",
        "snippet": "candidacy decision update",
        "date": "",
    }
    score, signals = score_candidate(
        message,
        MatchInputs(
            company=None,
            job_title=None,
            submitted_at=None,
            extra_terms=("candidacy", "decision"),
        ),
    )
    # Even though two manual terms appear, only one ``manual_term`` signal
    # is credited so the score remains explainable.
    assert signals.count("manual_term") == 1
    assert score > 0.0


def test_scorer_credits_ats_sender_domain():
    from app.gmail_application_search import MatchInputs, score_candidate

    message = {
        "id": "m1",
        "subject": "Re: your application",
        "from": "no-reply@greenhouse.io",
        "snippet": "Status update",
        "date": "",
    }
    _, signals = score_candidate(
        message,
        MatchInputs(company="Acme", job_title="Engineer", submitted_at=None),
    )
    assert "ats_sender_domain" in signals


# ---- Endpoint tests ----------------------------------------------------
#
# These mirror the ``gmail_client_app`` pattern in ``test_gmail_oauth.py``
# so the endpoint can be exercised with a monkey-patched gmail_client.


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
def gmail_app(gmail_env, tmp_path: Path):
    from fastapi.testclient import TestClient

    db_file = tmp_path / "search-tests.db"
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


def _make_application(client, *, submit: bool = True) -> dict:
    job_payload = {
        "source_platform": "linkedin",
        "company": "Example Aero Labs",
        "title": "Scientific Machine Learning Engineer",
        "description_text": "Do work.",
    }
    job = client.post("/jobs", json=job_payload).json()
    app_obj = client.post(
        "/applications", json={"job_id": job["id"], "status": "draft"}
    ).json()
    if submit:
        app_obj = client.post(f"/applications/{app_obj['id']}/submit").json()
    return app_obj


def test_search_requires_gmail_connection(gmail_app):
    client, _ = gmail_app
    app_obj = _make_application(client)

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 5, "include_ats_terms": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gmail_connected"] is False
    assert body["count"] == 0
    assert body["candidates"] == []
    assert "Connect Gmail" in (body.get("message") or "")

    # Disconnected search must NOT mutate email_status.
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "watching"


def test_search_404s_for_unknown_application(gmail_app):
    client, _ = gmail_app
    r = client.post(
        "/applications/does-not-exist/gmail/search",
        json={"max_results": 5},
    )
    assert r.status_code == 404


def test_search_returns_candidates_and_safe_metadata(gmail_app, monkeypatch):
    client, gmail_client = gmail_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
    )

    def fake_search(query: str, max_results: int):
        # Pretend the candidate happens to match the company in its
        # subject so the scorer credits at least one signal.
        return [
            {
                "id": "m1",
                "thread_id": "t1",
                "subject": "Thanks for applying to Example Aero Labs",
                "from": "talent@exampleaerolabs.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "We received your Scientific Machine Learning Engineer application.",
            },
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 10, "include_ats_terms": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gmail_connected"] is True
    assert body["gmail_query"]
    assert '"Example Aero Labs"' in body["gmail_query"]
    assert body["count"] == 1
    cand = body["candidates"][0]
    assert cand["message_id"] == "m1"
    assert cand["thread_id"] == "t1"
    assert cand["subject"].startswith("Thanks for applying")
    assert cand["from"] == "talent@exampleaerolabs.com"
    assert cand["snippet"].startswith("We received your")
    assert "matched_signals" in cand
    assert isinstance(cand["match_score"], float)
    assert 0.0 <= cand["match_score"] <= 1.0
    # No body / html / attachments in the response.
    assert set(cand.keys()) == {
        "message_id",
        "thread_id",
        "subject",
        "from",
        "date",
        "snippet",
        "matched_signals",
        "match_score",
    }


def test_search_caps_max_results(gmail_app, monkeypatch):
    client, gmail_client = gmail_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
        }
    )

    seen: dict[str, int] = {}

    def fake_search(query: str, max_results: int):
        seen["max_results"] = max_results
        return []

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 9999, "include_ats_terms": True},
    )
    # Capped to MAX_TEST_SEARCH_RESULTS (the test-search ceiling) which is
    # the smallest of the two limits.
    assert seen["max_results"] == gmail_client.MAX_TEST_SEARCH_RESULTS
    assert gmail_client.MAX_TEST_SEARCH_RESULTS == 10


def test_search_updates_email_status_to_no_match(gmail_app, monkeypatch):
    client, gmail_client = gmail_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
        }
    )
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    app_obj = _make_application(client)
    pre_status = app_obj["status"]

    client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 5},
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "no_match"
    # Application main status must not flip to rejected/interview/etc.
    assert reloaded["status"] == pre_status
    assert reloaded["last_gmail_check_at"] is not None


def test_search_updates_email_status_to_email_received(gmail_app, monkeypatch):
    client, gmail_client = gmail_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
        }
    )

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m1",
                "thread_id": "t1",
                "subject": "Update from Example Aero Labs",
                "from": "noreply@exampleaerolabs.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Hello",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    pre_status = app_obj["status"]

    client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 5},
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "email_received"
    # Main status untouched — classification is a separate task.
    assert reloaded["status"] == pre_status


def test_search_does_not_change_main_application_status(gmail_app, monkeypatch):
    """Even matches that *look* like rejections / offers do not change
    ``Application.status`` in this task."""
    client, gmail_client = gmail_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
        }
    )

    monkeypatch.setattr(
        gmail_client,
        "search_messages",
        lambda q, n: [
            {
                "id": "m1",
                "thread_id": "t1",
                "subject": "We regret to inform you - rejection",
                "from": "no-reply@exampleaerolabs.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Unfortunately we will not be moving forward.",
            },
        ],
    )

    app_obj = _make_application(client)
    pre_status = app_obj["status"]
    client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 5},
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == pre_status
    # No EmailLink rows were created either.
    links = client.get(f"/applications/{app_obj['id']}/email-links").json()
    assert links == []


def test_search_returns_candidates_sorted_by_score(gmail_app, monkeypatch):
    client, gmail_client = gmail_app
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
        }
    )

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "low",
                "thread_id": "t",
                "subject": "Newsletter",
                "from": "news@example.org",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Top stories",
            },
            {
                "id": "high",
                "thread_id": "t",
                "subject": "Example Aero Labs interview",
                "from": "talent@exampleaerolabs.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Scientific Machine Learning Engineer chat",
            },
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    body = client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 5},
    ).json()
    assert [c["message_id"] for c in body["candidates"]] == ["high", "low"]
    assert body["candidates"][0]["match_score"] > body["candidates"][1]["match_score"]


# ---- Safety guards ---------------------------------------------------


def test_search_module_imports_no_google_libraries():
    """The application-search module must stay free of any google deps.

    The actual Gmail round-trip lives in ``app.gmail_client``; this
    helper is pure logic and must not pull google libs into the import
    graph.
    """
    import importlib
    import sys as _sys

    importlib.import_module("app.gmail_application_search")
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


def test_no_gmail_write_routes_added_by_task_083(gmail_app):
    client, _ = gmail_app
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
    # The new endpoint lives under /applications/{id}/gmail/search — no
    # top-level /gmail/search should exist.
    assert all(not p.startswith("/gmail/search") for p in paths)
