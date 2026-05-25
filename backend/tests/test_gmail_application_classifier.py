"""Tests for the Gmail application classifier (task 084).

The classifier itself is a pure-Python function that takes a small
``CandidateEmail`` and returns a label / confidence / evidence triple.
The endpoint that wraps it is exercised through a TestClient with no
real Gmail credentials — the classifier never touches the network, so
no monkey-patching of ``gmail_client`` is required for the classify
route.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


# ---- Pure classifier tests --------------------------------------------


def _make_candidate(**kwargs):
    from app.gmail_application_classifier import CandidateEmail

    return CandidateEmail(**kwargs)


def test_rejection_phrase_classifies_as_rejection():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Update on your application",
        from_="recruiting@example.com",
        snippet="Unfortunately, we will not be moving forward with your application.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "rejection"
    assert result.confidence > 0.5
    assert any(
        "moving forward" in e.text.lower() for e in result.evidence
    )


def test_interview_phrase_classifies_as_interview_request():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Phone screen with our team",
        from_="recruiting@example.com",
        snippet="We'd love to schedule an interview to chat with our team.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "interview_request"
    assert result.confidence > 0.5


def test_assessment_phrase_classifies_as_assessment():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Take-home assignment",
        from_="recruiting@example.com",
        snippet="Please complete the assessment using HackerRank.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "assessment"


def test_submission_confirmation_phrase_classifies_as_confirmation():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Application received",
        from_="noreply@example.com",
        snippet="Thank you for applying to our Engineer role.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "submission_confirmation"


def test_offer_phrase_classifies_as_offer():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="We would like to extend an offer",
        from_="hiring@example.com",
        snippet="We are pleased to offer you the role.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "offer"


def test_neutral_update_phrase_classifies_as_application_update():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Status update",
        from_="recruiting@example.com",
        snippet="Your application is still under review; we will be in touch.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "application_update"


def test_newsletter_or_unrelated_does_not_classify_as_decision():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Weekly digest",
        from_="news@example.org",
        snippet="This week in tech. Unsubscribe at the link below.",
    )
    result = classify_candidate(candidate)
    assert result.classification in ("newsletter_or_unrelated", "unknown")


def test_ambiguous_reschedule_does_not_classify_as_rejection():
    """The classic false positive: "unfortunately" hits the rejection
    table, but the precedence rule must pick ``interview_request`` because
    of the "reschedule your interview" hit.
    """
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Quick scheduling change",
        from_="recruiting@example.com",
        snippet="Unfortunately, we need to reschedule your interview to next week.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "interview_request"


def test_classification_includes_confidence_and_evidence():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Application received",
        from_="noreply@example.com",
        snippet="Thank you for applying.",
    )
    result = classify_candidate(candidate)
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.evidence) >= 1
    for evidence in result.evidence:
        assert evidence.field in {"subject", "from", "snippet"}
        assert evidence.text
        assert evidence.reason


def test_evidence_only_uses_safe_metadata_fields():
    """The classifier must never accept or emit full-body content."""
    from app.gmail_application_classifier import (
        CandidateEmail,
        candidate_from_metadata,
    )

    # ``body`` and ``html`` are silently dropped so a caller cannot leak
    # them into the classifier.
    meta = {
        "subject": "Thanks for applying",
        "from": "noreply@example.com",
        "snippet": "We received your application.",
        "body": "FULL BODY THAT MUST NEVER BE READ",
        "html": "<html>NOPE</html>",
    }
    candidate = candidate_from_metadata(meta)
    assert isinstance(candidate, CandidateEmail)
    # No attribute on the dataclass holds the body.
    assert not hasattr(candidate, "body")
    assert not hasattr(candidate, "html")


def test_unknown_classification_when_no_phrases_match():
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Hello!",
        from_="friend@example.com",
        snippet="Long time no see.",
    )
    result = classify_candidate(candidate)
    assert result.classification == "unknown"
    assert result.evidence == ()


def test_offer_outranks_concurrent_interview_signal():
    """Precedence: an offer phrase must win over an interview phrase
    when both are present."""
    from app.gmail_application_classifier import classify_candidate

    candidate = _make_candidate(
        subject="Offer letter",
        from_="hiring@example.com",
        snippet=(
            "We are pleased to offer you the role. We will set up a time "
            "to chat with our team about next steps."
        ),
    )
    result = classify_candidate(candidate)
    assert result.classification == "offer"


# ---- Endpoint tests ---------------------------------------------------


@pytest.fixture()
def classify_app(tmp_path: Path) -> Iterator:
    from fastapi.testclient import TestClient

    db_file = tmp_path / "classify-tests.db"
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

    with TestClient(app) as c:
        yield c

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


def test_classify_endpoint_rejection_updates_application_status(classify_app):
    client = classify_app
    app_obj = _make_application(client)

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={
            "candidate": {
                "message_id": "m-reject",
                "subject": "Update on your application",
                "from": "jobs@example.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Unfortunately, we will not be moving forward.",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classification"] == "rejection"
    assert body["email_status"] == "classified_rejection"
    assert body["application_status"] == "rejected"
    assert body["application_status_changed"] is True
    assert body["evidence"]
    assert "reason" in body and body["reason"]
    # Persisted EmailLink exists and the GET endpoint reflects the new state.
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "rejected"
    assert reloaded["email_status"] == "classified_rejection"


def test_classify_endpoint_interview_updates_application_status(classify_app):
    client = classify_app
    app_obj = _make_application(client)

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={
            "candidate": {
                "message_id": "m-interview",
                "subject": "Phone screen with our team",
                "from": "recruiting@example.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "We'd love to schedule an interview.",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classification"] == "interview_request"
    assert body["email_status"] == "classified_interview"
    assert body["application_status"] == "interview"
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "interview"
    assert reloaded["email_status"] == "classified_interview"


def test_classify_endpoint_assessment_does_not_mark_approved_or_rejected(
    classify_app,
):
    client = classify_app
    app_obj = _make_application(client)
    pre_status = app_obj["status"]

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={
            "candidate": {
                "message_id": "m-asmt",
                "subject": "Take-home assignment",
                "from": "recruiting@example.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Please complete the assessment using HackerRank.",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classification"] == "assessment"
    assert body["email_status"] == "classified_assessment"
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    # Assessment must not mark the application approved or rejected.
    assert reloaded["status"] not in {"approved", "rejected"}
    # In particular, the existing EmailLink side-effect mapping routes
    # assessment → next_step → application.status = interview today.
    # The point of this test is to pin "not rejected, not approved".
    assert reloaded["status"] in {"submitted", "interview", pre_status}


def test_classify_endpoint_does_not_change_withdrawn_application(classify_app):
    client = classify_app
    app_obj = _make_application(client)
    # Force the application into ``withdrawn`` via the events endpoint —
    # mark-status helpers only cover rejected/interview, so we update the
    # row via the create_application_event surface and then manually
    # withdraw using the existing routes.
    # The simplest path: call the mark-status helper for rejected first
    # would taint the test; instead we patch the row directly via the
    # /events surface alongside a status flip using a fresh sqlite UPDATE.
    import sqlite3

    db_path = os.environ["JOBAPPLY_DATABASE_URL"].replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE applications SET status='withdrawn' WHERE id=?",
            (app_obj["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={
            "candidate": {
                "message_id": "m-reject-on-withdrawn",
                "subject": "Update on your application",
                "from": "jobs@example.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "Unfortunately, we will not be moving forward.",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The classifier still reports the rejection label and evidence so
    # the user sees what was detected.
    assert body["classification"] == "rejection"
    # But the application's main status is unchanged.
    assert body["application_status"] == "withdrawn"
    assert body["application_status_changed"] is False
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "withdrawn"


def test_classify_endpoint_requires_candidate(classify_app):
    client = classify_app
    app_obj = _make_application(client)

    # No candidate metadata and no message_id → 422.
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={},
    )
    assert r.status_code == 422

    # ``classify_top_candidate`` without a stored candidate → 400 with
    # a clear error.
    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={"classify_top_candidate": True},
    )
    assert r.status_code == 400
    assert "candidate" in r.json()["detail"].lower()


def test_classify_endpoint_404s_for_unknown_application(classify_app):
    client = classify_app
    r = client.post(
        "/applications/does-not-exist/gmail/classify",
        json={
            "candidate": {
                "message_id": "m1",
                "subject": "x",
                "from": "x@example.com",
                "date": "",
                "snippet": "y",
            }
        },
    )
    assert r.status_code == 404


def test_classify_endpoint_evidence_uses_only_safe_fields(classify_app):
    """The response evidence must only quote subject/from/snippet."""
    client = classify_app
    app_obj = _make_application(client)

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={
            "candidate": {
                "message_id": "m-evidence",
                "subject": "Thanks for applying",
                "from": "noreply@example.com",
                "date": "Mon, 25 May 2026 12:00:00 +0000",
                "snippet": "We received your application.",
            }
        },
    )
    body = r.json()
    assert r.status_code == 200, body
    for ev in body["evidence"]:
        assert ev["field"] in {"subject", "from", "snippet"}
        assert "body" not in ev
        assert "html" not in ev


def test_classify_endpoint_does_not_persist_body_in_email_link(classify_app):
    client = classify_app
    app_obj = _make_application(client)

    r = client.post(
        f"/applications/{app_obj['id']}/gmail/classify",
        json={
            "candidate": {
                "message_id": "m-no-body",
                "subject": "Update on your application",
                "from": "jobs@example.com",
                "snippet": "Unfortunately, we will not be moving forward.",
            }
        },
    )
    assert r.status_code == 200, r.text
    links = client.get(f"/applications/{app_obj['id']}/email-links").json()
    assert len(links) == 1
    link = links[0]
    # EmailLink schema is purely metadata; assert no body / html ever
    # appears in the persisted row.
    assert "body" not in link
    assert "html" not in link
    assert link["gmail_message_id"] == "m-no-body"


def test_classify_endpoint_idempotent_on_repeated_calls(classify_app):
    """Re-classifying the same message_id must not write duplicate
    EmailLink rows or duplicate events."""
    client = classify_app
    app_obj = _make_application(client)

    payload = {
        "candidate": {
            "message_id": "m-idem",
            "subject": "Update on your application",
            "from": "jobs@example.com",
            "snippet": "Unfortunately, we will not be moving forward.",
        }
    }
    client.post(f"/applications/{app_obj['id']}/gmail/classify", json=payload)
    client.post(f"/applications/{app_obj['id']}/gmail/classify", json=payload)

    links = client.get(f"/applications/{app_obj['id']}/email-links").json()
    assert len(links) == 1


# ---- Safety guards ----------------------------------------------------


def test_classifier_module_imports_no_google_libraries():
    """The classifier module must not pull google / IMAP / SMTP libs in."""
    import importlib
    import sys as _sys

    importlib.import_module("app.gmail_application_classifier")
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


def test_no_gmail_write_routes_added_by_task_084(classify_app):
    client = classify_app
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
