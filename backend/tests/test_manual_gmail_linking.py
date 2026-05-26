"""Tests for the manual Gmail email-linking endpoints (task 093).

These tests cover:

- The threshold-based ``email_search_state`` derivation on the existing
  search endpoint (strong / possible / no_match).
- The new ``POST /applications/{id}/gmail/candidates`` endpoint that
  surfaces both strong and low-confidence candidates and supports
  manual queries.
- ``POST /applications/{id}/gmail/link-email`` for manual linking with
  ``match_method=manual`` + ``linked_by_user=true``.
- ``GET /applications/{id}/gmail/linked-emails``.
- ``DELETE /applications/{id}/gmail/linked-emails/{id}``.
- Status mapping for each classification (confirmation, rejection,
  interview, assessment, application_update, unknown).
- Withdrawn-application protection.
- No Gmail write routes are added.

The Gmail client is monkey-patched so no real Google credentials are
required and no network call is ever attempted.
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
def link_app(gmail_env, tmp_path: Path):
    from fastapi.testclient import TestClient

    db_file = tmp_path / "link-tests.db"
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


def _connect(gmail_client) -> None:
    gmail_client.save_token(
        {
            "token": "fake",
            "scopes": [gmail_client.GMAIL_READONLY_SCOPE],
            "email": "calvin@example.com",
        }
    )


def _make_application(client, *, company: str = "Infinity Labs R&D",
                      title: str = "Graduates", submit: bool = True) -> dict:
    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": company,
            "title": title,
            "description_text": "Do work.",
        },
    ).json()
    app_obj = client.post(
        "/applications", json={"job_id": job["id"], "status": "draft"}
    ).json()
    if submit:
        app_obj = client.post(f"/applications/{app_obj['id']}/submit").json()
    return app_obj


# ---- Threshold behavior on the existing search endpoint --------------


def test_search_strong_match_sets_email_received(link_app, monkeypatch):
    """A high-scoring candidate (>= 0.70) yields email_received."""
    client, gmail_client = link_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "m1",
                "thread_id": "t1",
                "subject": "Thanks for applying to Infinity Labs R&D — Graduates",
                "from": "talent@infinitylabsrd.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "We received your Graduates application.",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/search",
        json={"max_results": 10},
    )
    assert r.status_code == 200, r.text
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "email_received"


def test_search_only_possible_matches_set_needs_review(link_app, monkeypatch):
    """A mid-score candidate (0.25 <= score < 0.70) yields needs_review."""
    client, gmail_client = link_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        # The body mentions the company once but lacks the job title and
        # the sender domain doesn't include the company slug — score
        # should land in the "possible" band.
        return [
            {
                "id": "p1",
                "thread_id": "t1",
                "subject": "Update from Infinity Labs R&D",
                "from": "no-reply@mailservice.example",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Hello",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)
    app_obj = _make_application(client)
    client.post(
        f"/applications/{app_obj['id']}/gmail/search", json={"max_results": 5}
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    # Score = 0.45 (company_name) + 0.10 (after_submitted_at) = 0.55 → possible.
    assert reloaded["email_status"] == "needs_review", reloaded


def test_search_true_no_match_sets_no_match(link_app, monkeypatch):
    """Empty results yield no_match (binary fall-through)."""
    client, gmail_client = link_app
    _connect(gmail_client)
    monkeypatch.setattr(gmail_client, "search_messages", lambda q, n: [])

    app_obj = _make_application(client)
    client.post(
        f"/applications/{app_obj['id']}/gmail/search", json={"max_results": 5}
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "no_match"


# ---- /gmail/candidates endpoint --------------------------------------


def test_candidates_returns_strong_and_possible(link_app, monkeypatch):
    client, gmail_client = link_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "strong",
                "thread_id": "t1",
                "subject": "Thanks for applying to Infinity Labs R&D — Graduates",
                "from": "talent@infinitylabsrd.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "We received your Graduates application.",
            },
            {
                "id": "possible",
                "thread_id": "t2",
                "subject": "Infinity Labs R&D weekly update",
                "from": "newsletter@unrelated.example",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Hello",
            },
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/candidates",
        json={"include_low_confidence": True, "max_results": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gmail_connected"] is True
    assert body["strong_count"] >= 1
    assert body["possible_count"] >= 1
    ids = [c["message_id"] for c in body["candidates"]]
    assert "strong" in ids
    assert "possible" in ids
    # Each candidate carries the classifier label guess.
    by_id = {c["message_id"]: c for c in body["candidates"]}
    assert by_id["strong"]["classification_guess"]


def test_candidates_no_strong_only_possible_sets_needs_review(link_app, monkeypatch):
    client, gmail_client = link_app
    _connect(gmail_client)

    def fake_search(query: str, max_results: int):
        return [
            {
                "id": "p1",
                "thread_id": "t1",
                "subject": "Infinity Labs R&D updates",
                "from": "no-reply@mailservice.example",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Hello",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/candidates",
        json={"include_low_confidence": True, "max_results": 10},
    )
    assert r.status_code == 200, r.text
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "needs_review"


def test_candidates_manual_query_passed_through(link_app, monkeypatch):
    client, gmail_client = link_app
    _connect(gmail_client)
    seen: dict = {}

    def fake_search(query: str, max_results: int):
        seen["query"] = query
        return [
            {
                "id": "m1",
                "thread_id": "t",
                "subject": "Infinity Labs R&D — application confirmation",
                "from": "hr@infinitylabsrd.com",
                "date": "",
                "snippet": "Thanks for applying.",
            }
        ]

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/candidates",
        json={"query": "Infinity Labs", "max_results": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert seen["query"] == "Infinity Labs"
    assert body["query_used"] == "Infinity Labs"


def test_candidates_requires_gmail_connection(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/candidates",
        json={"include_low_confidence": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["gmail_connected"] is False
    assert "Connect Gmail" in (body.get("message") or "")


def test_candidates_404_for_unknown_application(link_app):
    client, _ = link_app
    r = client.post(
        "/applications/does-not-exist/gmail/candidates",
        json={"include_low_confidence": True},
    )
    assert r.status_code == 404


# ---- /gmail/link-email endpoint -------------------------------------


def _link_payload(**overrides) -> dict:
    payload = {
        "message_id": overrides.get("message_id", "msg-1"),
        "thread_id": overrides.get("thread_id", "thr-1"),
        "classification": overrides.get(
            "classification", "submission_confirmation"
        ),
        "sender": overrides.get(
            "sender", "Infinity Labs R&D <hr@infinitylabsrd.com>"
        ),
        "subject": overrides.get(
            "subject", "Thank you for contacting Infinity Labs R&D"
        ),
        "snippet": overrides.get(
            "snippet", "Thank you for applying to Infinity Labs R&D..."
        ),
        "received_at": overrides.get("received_at"),
        "match_score": overrides.get("match_score", 0.42),
        "user_confirmed": overrides.get("user_confirmed", True),
    }
    return {k: v for k, v in payload.items() if v is not None}


def test_link_email_persists_message_and_thread_id(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="gmail-msg-abc", thread_id="gmail-thr-xyz"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    link = body["email_link"]
    assert link["gmail_message_id"] == "gmail-msg-abc"
    assert link["gmail_thread_id"] == "gmail-thr-xyz"


def test_link_email_records_manual_method_and_user_flag(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(),
    )
    assert r.status_code == 200, r.text
    link = r.json()["email_link"]
    # Gmail-candidate manual confirmations carry the more specific match_method
    # so the UI can distinguish them from raw manual-entry rows.
    assert link["match_method"] == "manual_candidate_link"
    assert link["linked_by_user"] is True
    # Evidence carries the user-confirmation note (no full body).
    assert link["evidence"] is not None
    assert any(
        "manually confirmed" in item["reason"].lower() for item in link["evidence"]
    )


def test_link_email_stores_metadata(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(
            sender="Infinity Labs R&D <hr@infinitylabsrd.co.il>",
            subject="Thank you for contacting Infinity Labs R&D",
            snippet="Thank you for applying to Infinity Labs R&D...",
        ),
    )
    assert r.status_code == 200, r.text
    link = r.json()["email_link"]
    assert "Infinity Labs" in link["sender"]
    assert link["subject"].startswith("Thank you for contacting")
    assert link["snippet"].startswith("Thank you for applying")


def test_link_email_does_not_store_full_body(link_app):
    """Even when callers pass a giant blob as ``snippet`` we don't extend
    the schema to a body field. The endpoint accepts ``snippet`` only."""
    client, _ = link_app
    app_obj = _make_application(client)
    # Try to slip an unknown ``body`` field — pydantic will simply ignore
    # it because EmailLinkCreate / GmailLinkEmailRequest never declared it.
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json={
            **_link_payload(),
            "body": "FULL EMAIL BODY THAT SHOULD NEVER PERSIST" * 50,
        },
    )
    assert r.status_code == 200
    link = r.json()["email_link"]
    assert "body" not in link
    assert "FULL EMAIL BODY" not in (link.get("snippet") or "")


def test_link_as_confirmation_updates_status(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    pre = app_obj["status"]
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="submission_confirmation"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email_status"] == "confirmation_found"
    # submission_confirmation does not change main status.
    assert body["application_status"] == pre
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "confirmation_found"


def test_link_as_rejection_marks_rejected(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="rejection", message_id="r1"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["application_status"] == "rejected"
    assert body["application_status_changed"] is True
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "rejected"
    assert reloaded["email_status"] == "classified_rejection"


def test_link_as_interview_marks_interview(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="interview_request", message_id="i1"),
    )
    assert r.status_code == 200
    assert r.json()["application_status"] == "interview"
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "interview"
    assert reloaded["email_status"] == "classified_interview"


def test_link_as_assessment_records_link_without_terminal_change(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    pre = app_obj["status"]
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="assessment", message_id="a1"),
    )
    assert r.status_code == 200
    body = r.json()
    # assessment maps to next_step today (per the contract), so the main
    # status becomes "interview". The classification label we return is
    # the user's intent.
    assert body["classification"] == "assessment"
    assert body["application_status"] in {"interview", pre}
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_link_count"] == 1


def test_link_as_application_update_keeps_status(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    pre = app_obj["status"]
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="application_update", message_id="u1"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["application_status"] == pre
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == pre


def test_link_unknown_classification_defaults_to_needs_review(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    pre = app_obj["status"]
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json={
            "message_id": "u-1",
            "thread_id": "t",
            "subject": "Something",
            "sender": "x@y.com",
            "snippet": "We are reviewing",
            "user_confirmed": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["classification"] == "unknown"
    assert body["email_status"] == "needs_review"
    assert body["application_status"] == pre


def test_link_invalid_classification_returns_422(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="totally-made-up"),
    )
    assert r.status_code == 422


def test_link_withdrawn_does_not_auto_change_main_status(link_app):
    from app.db import SessionLocal
    from app.models import Application

    client, _ = link_app
    app_obj = _make_application(client)
    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.status = "withdrawn"
        db.commit()

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(classification="rejection", message_id="w1"),
    )
    assert r.status_code == 200
    # Status stays withdrawn even though rejection was linked.
    assert r.json()["application_status"] == "withdrawn"
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "withdrawn"


def test_link_email_404_for_unknown_application(link_app):
    client, _ = link_app
    r = client.post(
        "/applications/does-not-exist/gmail/link-email",
        json=_link_payload(),
    )
    assert r.status_code == 404


def test_link_email_idempotent_on_same_message_id(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    first = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="dup", classification="rejection"),
    )
    assert first.status_code == 200
    second = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="dup", classification="offer"),
    )
    assert second.status_code == 200
    # Status stays rejected — second link did not re-apply side effects.
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "rejected"
    assert reloaded["email_link_count"] == 1


# ---- /gmail/linked-emails endpoint ----------------------------------


def test_linked_emails_returns_stored_evidence(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="le-1", classification="submission_confirmation"),
    )
    r = client.get(f"/applications/{app_obj['id']}/gmail/linked-emails")
    assert r.status_code == 200
    body = r.json()
    assert body["application_id"] == app_obj["id"]
    assert len(body["linked_emails"]) == 1
    link = body["linked_emails"][0]
    assert link["gmail_message_id"] == "le-1"
    assert link["match_method"] == "manual_candidate_link"
    assert link["linked_by_user"] is True


def test_linked_emails_empty_when_nothing_linked(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.get(f"/applications/{app_obj['id']}/gmail/linked-emails")
    assert r.status_code == 200
    assert r.json()["linked_emails"] == []


# ---- DELETE / unlink ------------------------------------------------


def test_unlink_removes_application_email_association(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    link_resp = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="del-1", classification="submission_confirmation"),
    ).json()
    link_id = link_resp["email_link"]["id"]

    r = client.delete(
        f"/applications/{app_obj['id']}/gmail/linked-emails/{link_id}"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["removed_email_link_id"] == link_id
    assert body["remaining_linked_count"] == 0

    listing = client.get(
        f"/applications/{app_obj['id']}/gmail/linked-emails"
    ).json()
    assert listing["linked_emails"] == []


def test_unlink_404_for_unknown_link(link_app):
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.delete(
        f"/applications/{app_obj['id']}/gmail/linked-emails/does-not-exist"
    )
    assert r.status_code == 404


def test_unlink_does_not_modify_gmail(link_app, monkeypatch):
    """Unlinking only touches the local DB — Gmail itself is never called."""
    client, gmail_client = link_app
    _connect(gmail_client)

    called: list[str] = []

    def fake_search(*args, **kwargs):
        called.append("search")
        return []

    monkeypatch.setattr(gmail_client, "search_messages", fake_search)

    app_obj = _make_application(client)
    link_resp = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="ng-1", classification="rejection"),
    ).json()
    link_id = link_resp["email_link"]["id"]

    r = client.delete(
        f"/applications/{app_obj['id']}/gmail/linked-emails/{link_id}"
    )
    assert r.status_code == 200
    # Gmail client search was never invoked by the unlink flow.
    assert called == []


# ---- Safety / no Gmail write surface --------------------------------


def test_no_gmail_write_routes_added_by_task_093(link_app):
    client, _ = link_app
    paths = [getattr(r, "path", "") for r in client.app.routes]
    forbidden = (
        "send",
        "archive",
        "delete-message",
        "label",
        "modify-message",
        "trash",
        "draft",
        "reply",
    )
    for path in paths:
        if "/gmail" not in path:
            continue
        for needle in forbidden:
            assert needle not in path.lower(), (path, needle)


def test_link_email_preserves_real_gmail_message_id_not_manual_uuid(link_app):
    """A Gmail-candidate link must store the real Gmail id verbatim — no
    ``manual:<uuid>`` is substituted for the candidate's message_id."""
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="1936ab12345abcdef", thread_id="1936aaa"),
    )
    assert r.status_code == 200, r.text
    link = r.json()["email_link"]
    assert link["gmail_message_id"] == "1936ab12345abcdef"
    assert not link["gmail_message_id"].startswith("manual:")


def test_link_email_preserves_candidate_metadata_from_request(link_app):
    """sender / subject / snippet / received_at flow through verbatim."""
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(
            message_id="meta-1",
            sender="recruiter@example.com",
            subject="Interview availability",
            snippet="We'd like to schedule a phone screen.",
            received_at="2026-05-25T20:01:00Z",
            classification="interview_request",
        ),
    )
    assert r.status_code == 200, r.text
    link = r.json()["email_link"]
    assert link["sender"] == "recruiter@example.com"
    assert link["subject"] == "Interview availability"
    assert link["snippet"] == "We'd like to schedule a phone screen."
    assert link["received_at"] is not None


# ---- /applications/{id}/email-links (truly manual entry) -------------


def test_manual_email_link_records_manual_entry_method(link_app):
    """The /email-links endpoint (manual Record Email form) tags rows with
    ``match_method=manual_entry`` so the UI can distinguish them from
    Gmail-candidate confirmations."""
    client, _ = link_app
    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": "manual:abc-123",
            "classified_status": "confirmation",
            "sender": "noreply@example.com",
            "subject": "Your application",
        },
    )
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body["gmail_message_id"] == "manual:abc-123"
    assert body["match_method"] == "manual_entry"
    assert body["linked_by_user"] is True


def test_link_email_does_not_call_gmail_client(link_app, monkeypatch):
    """The link-email endpoint trusts the client-supplied metadata and
    must not round-trip Gmail to fetch anything else."""
    client, gmail_client = link_app
    _connect(gmail_client)

    called: list[str] = []
    monkeypatch.setattr(
        gmail_client,
        "search_messages",
        lambda *a, **kw: called.append("search") or [],
    )

    app_obj = _make_application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/link-email",
        json=_link_payload(message_id="nc-1"),
    )
    assert r.status_code == 200
    assert called == []
