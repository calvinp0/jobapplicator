"""Tests for the Gmail integration design surface (task 080).

These tests cover the *model* and *contract* introduced in task 080:
``EMAIL_STATUSES`` vocabulary, the ``derive_email_status`` /
``derive_next_action`` / ``build_default_gmail_tracking_state`` /
``is_valid_email_status`` helpers, and the new ``ApplicationRead``
Gmail-tracking fields.

The tests deliberately do **not** exercise any Gmail network/API path
because there is none yet; they only assert the design surface compiles,
validates, and serializes correctly.
"""

from __future__ import annotations

import uuid


# ---- Fixtures ----------------------------------------------------------


def _job(client):
    payload = {
        "source_platform": "linkedin",
        "company": "Example Aero Labs",
        "title": "Scientific Machine Learning Engineer",
        "description_text": "Do work.",
    }
    return client.post("/jobs", json=payload).json()


def _application(client, status="draft"):
    job = _job(client)
    return client.post(
        "/applications", json={"job_id": job["id"], "status": status}
    ).json()


def _manual_id() -> str:
    return f"manual:{uuid.uuid4()}"


# ---- Vocabulary --------------------------------------------------------


def test_email_statuses_tuple_contains_full_task_vocabulary():
    from app.models import EMAIL_STATUSES

    expected = {
        "not_watching",
        "watching",
        "confirmation_found",
        "email_received",
        "needs_review",
        "classified_rejection",
        "classified_interview",
        "classified_assessment",
        "classified_offer",
        "classified_neutral",
        "no_match",
        "error",
    }
    assert set(EMAIL_STATUSES) == expected


def test_email_status_set_is_frozen_and_matches_tuple():
    from app.models import EMAIL_STATUSES
    from app.schemas import EMAIL_STATUS_SET

    assert isinstance(EMAIL_STATUS_SET, frozenset)
    assert EMAIL_STATUS_SET == frozenset(EMAIL_STATUSES)


def test_is_valid_email_status_accepts_canonical_values():
    from app.models import EMAIL_STATUSES
    from app.routers.applications import is_valid_email_status

    for value in EMAIL_STATUSES:
        assert is_valid_email_status(value), value


def test_is_valid_email_status_rejects_unknown_values():
    from app.routers.applications import is_valid_email_status

    for value in ("", "totally_invented", "classified_positive", "WATCHING", None):
        assert not is_valid_email_status(value), value


# ---- Default tracking state -------------------------------------------


def test_build_default_gmail_tracking_state_matches_contract():
    from app.routers.applications import build_default_gmail_tracking_state

    default = build_default_gmail_tracking_state()

    assert default == {
        "email_status": "not_watching",
        "gmail_query": None,
        "last_gmail_check_at": None,
        "last_matched_email_at": None,
        "matched_email_count": 0,
        "latest_email_subject": None,
        "latest_email_from": None,
        "latest_email_snippet": None,
        "latest_email_classification": None,
        "latest_email_confidence": None,
        "latest_email_evidence": None,
    }


# ---- ApplicationRead serialization ------------------------------------


def test_new_application_serializes_default_gmail_state(client):
    from app.routers.applications import build_default_gmail_tracking_state

    app_obj = _application(client)

    default = build_default_gmail_tracking_state()
    for field, expected in default.items():
        assert app_obj[field] == expected, field


def test_submitted_application_is_watching_with_no_match_data(client):
    app_obj = _application(client)
    submitted = client.post(f"/applications/{app_obj['id']}/submit").json()

    assert submitted["email_status"] == "watching"
    assert submitted["matched_email_count"] == 0
    assert submitted["last_matched_email_at"] is None
    assert submitted["latest_email_subject"] is None
    assert submitted["latest_email_from"] is None
    assert submitted["latest_email_classification"] is None
    assert submitted["latest_email_confidence"] is None
    assert submitted["latest_email_snippet"] is None
    assert submitted["latest_email_evidence"] is None


def test_confirmation_email_surfaces_as_confirmation_found(client):
    app_obj = _application(client)
    client.post(f"/applications/{app_obj['id']}/submit")
    r = client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": _manual_id(),
            "classified_status": "confirmation",
            "subject": "Thanks for applying to Example Aero Labs",
            "sender": "talent@exampleaero.com",
            "confidence": 0.93,
        },
    )
    assert r.status_code == 201, r.text

    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "confirmation_found"
    assert reloaded["matched_email_count"] == 1
    assert reloaded["latest_email_subject"] == "Thanks for applying to Example Aero Labs"
    assert reloaded["latest_email_from"] == "talent@exampleaero.com"
    assert reloaded["latest_email_classification"] == "confirmation"
    assert reloaded["latest_email_confidence"] == 0.93
    assert reloaded["last_matched_email_at"] is not None


def test_next_step_email_surfaces_as_classified_interview(client):
    app_obj = _application(client)
    client.post(f"/applications/{app_obj['id']}/submit")
    client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": _manual_id(),
            "classified_status": "next_step",
        },
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    # next_step transitions Application.status to interview; the derived
    # next_action follows the status branch ("Interview response needed").
    assert reloaded["status"] == "interview"
    assert reloaded["email_status"] == "classified_interview"
    assert reloaded["next_action"] == "Interview response needed"


def test_offer_email_surfaces_as_classified_offer(client):
    app_obj = _application(client)
    client.post(f"/applications/{app_obj['id']}/submit")
    client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": _manual_id(),
            "classified_status": "offer",
        },
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["status"] == "offer"
    assert reloaded["email_status"] == "classified_offer"


def test_other_email_surfaces_as_classified_neutral(client):
    app_obj = _application(client)
    client.post(f"/applications/{app_obj['id']}/submit")
    client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": _manual_id(),
            "classified_status": "other",
        },
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    # ``other`` is a non-decisive update; status stays "submitted".
    assert reloaded["status"] == "submitted"
    assert reloaded["email_status"] == "classified_neutral"


# ---- Persisted Gmail columns ------------------------------------------


def test_gmail_query_and_last_check_round_trip(client):
    """The new persisted columns are nullable and reachable through ORM."""
    from app.db import SessionLocal
    from app.models import Application
    from datetime import datetime, timezone

    app_obj = _application(client)

    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        assert row.gmail_query is None
        assert row.last_gmail_check_at is None

        row.gmail_query = '"Example Aero Labs" newer_than:90d'
        row.last_gmail_check_at = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
        db.commit()

    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["gmail_query"] == '"Example Aero Labs" newer_than:90d'
    assert reloaded["last_gmail_check_at"].startswith("2026-05-25T12:00:00")


def test_existing_application_without_gmail_fields_still_loads(client):
    """Backwards-compatible: an application created before the Gmail
    columns existed must still serialize with the documented defaults."""
    from app.db import SessionLocal
    from app.models import Application

    app_obj = _application(client)

    # Force the columns to NULL to simulate a row from before the migration.
    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.gmail_query = None
        row.last_gmail_check_at = None
        db.commit()

    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "not_watching"
    assert reloaded["gmail_query"] is None
    assert reloaded["last_gmail_check_at"] is None
    assert reloaded["matched_email_count"] == 0


# ---- Next-action surface ----------------------------------------------


def test_next_action_says_waiting_for_email_when_watching(client):
    app_obj = _application(client)
    submitted = client.post(f"/applications/{app_obj['id']}/submit").json()
    assert submitted["email_status"] == "watching"
    assert submitted["next_action"] == "Waiting for email"


def test_next_action_says_review_when_email_needs_review(client):
    """A submitted application with an attached EmailLink whose
    classified_status is null should derive ``needs_review`` and the
    dashboard hint should ask the user to review it."""
    from app.db import SessionLocal
    from app.models import EmailLink

    app_obj = _application(client)
    client.post(f"/applications/{app_obj['id']}/submit")

    # Bypass the create_email_link side-effect path so we can attach a
    # link with classified_status=None (the endpoint enforces a non-null
    # classification on create, but legacy rows or future low-confidence
    # matches may be unclassified).
    with SessionLocal() as db:
        db.add(
            EmailLink(
                application_id=app_obj["id"],
                gmail_message_id=_manual_id(),
                classified_status=None,
            )
        )
        db.commit()

    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    assert reloaded["email_status"] == "needs_review"
    assert reloaded["next_action"] == "Review detected email"


# ---- Safety: no Gmail network paths exist ----------------------------


def test_no_gmail_outbound_modules_imported():
    """Task 080 must not introduce any Gmail network/SMTP code.

    The contract is design-only; if a Gmail client library shows up in
    the import graph this test will catch it before review.
    """
    import importlib
    import sys

    # Make sure the app is importable; then assert nothing Gmail-y is loaded.
    importlib.import_module("app.main")

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


def test_application_routes_do_not_expose_gmail_send_or_mutate(client):
    """No application endpoint should accept a 'send', 'archive',
    'delete', or 'label' Gmail action. This is a coarse guard: it walks
    the FastAPI route table and asserts no matching path exists."""
    from app.main import app

    suspicious_substrings = (
        "/gmail/send",
        "/gmail/archive",
        "/gmail/delete",
        "/gmail/label",
        "/email/send",
        "/email/archive",
        "/email/delete",
        "/email/label",
    )
    paths = [getattr(r, "path", "") for r in app.routes]
    for needle in suspicious_substrings:
        assert not any(needle in p for p in paths), needle
