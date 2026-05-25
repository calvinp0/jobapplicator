from __future__ import annotations

import uuid


def _job(client):
    payload = {
        "source_platform": "linkedin",
        "company": "Acme",
        "title": "Engineer",
        "description_text": "Do work.",
    }
    return client.post("/jobs", json=payload).json()


def _application(client, status="draft"):
    job = _job(client)
    return client.post(
        "/applications", json={"job_id": job["id"], "status": status}
    ).json()


def _submit(client, application_id):
    return client.post(f"/applications/{application_id}/submit").json()


def _manual_id() -> str:
    return f"manual:{uuid.uuid4()}"


def _create_email_link(client, app_id, **overrides):
    payload = {
        "gmail_message_id": overrides.get("gmail_message_id", _manual_id()),
        "classified_status": overrides.get("classified_status", "confirmation"),
    }
    for key in ("gmail_thread_id", "subject", "sender", "received_at", "confidence"):
        if key in overrides:
            payload[key] = overrides[key]
    return client.post(f"/applications/{app_id}/email-links", json=payload)


# ---- Classification side effects -----------------------------------------


def test_confirmation_does_not_change_status_and_appends_event(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    r = _create_email_link(client, app_obj["id"], classified_status="confirmation")
    assert r.status_code == 201, r.text

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "submitted"
    assert fresh["timeline_stage"] == "confirmation_received"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    assert len(email_events) == 1
    assert email_events[0]["event_type"] == "email_confirmation_received"


def test_rejection_sets_status_rejected(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    r = _create_email_link(client, app_obj["id"], classified_status="rejection")
    assert r.status_code == 201

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "rejected"
    assert fresh["timeline_stage"] == "rejected"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    assert [e["event_type"] for e in email_events] == ["email_rejection_received"]


def test_next_step_sets_status_interview(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    r = _create_email_link(client, app_obj["id"], classified_status="next_step")
    assert r.status_code == 201

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "interview"
    assert fresh["timeline_stage"] == "interview"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    assert [e["event_type"] for e in email_events] == ["email_next_step_received"]


def test_offer_sets_status_offer(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    r = _create_email_link(client, app_obj["id"], classified_status="offer")
    assert r.status_code == 201

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "offer"
    assert fresh["timeline_stage"] == "offer"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    assert [e["event_type"] for e in email_events] == ["email_offer_received"]


def test_other_does_not_change_status_and_appends_event(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    r = _create_email_link(client, app_obj["id"], classified_status="other")
    assert r.status_code == 201

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "submitted"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    assert [e["event_type"] for e in email_events] == ["email_other_received"]


# ---- Precedence rules (sticky / terminal statuses) -----------------------


def test_withdrawn_blocks_rejection_status_change_but_appends_event(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    # Manually mark withdrawn via an event-driven path is out of scope here;
    # use the events endpoint via an explicit status change. The status
    # endpoint isn't exposed, so we drive it through create_application_event
    # only after directly setting via /submit then... actually we don't have
    # a status-set endpoint, so use the DB session for setup.
    # Instead: drive through ApplicationCreate (statuses are accepted), then
    # post an email link.
    from app.db import SessionLocal
    from app.models import Application

    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.status = "withdrawn"
        db.commit()

    r = _create_email_link(client, app_obj["id"], classified_status="rejection")
    assert r.status_code == 201

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "withdrawn"
    assert fresh["timeline_stage"] == "withdrawn"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    # The event is still recorded for audit, per the contract.
    assert [e["event_type"] for e in email_events] == ["email_rejection_received"]


def test_withdrawn_blocks_offer_and_next_step(client):
    from app.db import SessionLocal
    from app.models import Application

    app_obj = _application(client)
    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.status = "withdrawn"
        db.commit()

    r = _create_email_link(client, app_obj["id"], classified_status="offer")
    assert r.status_code == 201
    assert client.get(f"/applications/{app_obj['id']}").json()["status"] == "withdrawn"

    r = _create_email_link(client, app_obj["id"], classified_status="next_step")
    assert r.status_code == 201
    assert client.get(f"/applications/{app_obj['id']}").json()["status"] == "withdrawn"


def test_rejected_blocks_next_step(client):
    from app.db import SessionLocal
    from app.models import Application

    app_obj = _application(client)
    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.status = "rejected"
        db.commit()

    r = _create_email_link(client, app_obj["id"], classified_status="next_step")
    assert r.status_code == 201
    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "rejected"
    assert fresh["timeline_stage"] == "rejected"


def test_offer_blocks_next_step(client):
    from app.db import SessionLocal
    from app.models import Application

    app_obj = _application(client)
    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.status = "offer"
        db.commit()

    r = _create_email_link(client, app_obj["id"], classified_status="next_step")
    assert r.status_code == 201
    assert client.get(f"/applications/{app_obj['id']}").json()["status"] == "offer"


# ---- Derived timeline_stage for each ADR-010 stage -----------------------


def test_timeline_stage_draft(client):
    app_obj = _application(client)
    assert app_obj["timeline_stage"] == "draft"
    assert app_obj["last_email_link"] is None
    assert app_obj["email_link_count"] == 0


def test_timeline_stage_sent(client):
    app_obj = _application(client)
    submitted = _submit(client, app_obj["id"])
    assert submitted["timeline_stage"] == "sent"


def test_timeline_stage_confirmation_received(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])
    _create_email_link(client, app_obj["id"], classified_status="confirmation")
    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["timeline_stage"] == "confirmation_received"
    assert fresh["last_email_link"]["classified_status"] == "confirmation"
    assert fresh["email_link_count"] == 1


def test_timeline_stage_response_received(client):
    from app.db import SessionLocal
    from app.models import Application

    app_obj = _application(client)
    with SessionLocal() as db:
        row = db.get(Application, app_obj["id"])
        row.status = "response_received"
        db.commit()
    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["timeline_stage"] == "response_received"


def test_timeline_stage_interview_offer_rejected_withdrawn(client):
    from app.db import SessionLocal
    from app.models import Application

    for raw_status, expected_stage in (
        ("interview", "interview"),
        ("offer", "offer"),
        ("rejected", "rejected"),
        ("withdrawn", "withdrawn"),
    ):
        app_obj = _application(client)
        with SessionLocal() as db:
            row = db.get(Application, app_obj["id"])
            row.status = raw_status
            db.commit()
        fresh = client.get(f"/applications/{app_obj['id']}").json()
        assert fresh["timeline_stage"] == expected_stage, raw_status


def test_confirmation_does_not_advance_past_confirmation_received(client):
    """A confirmation email alongside a non-confirmation signal still
    surfaces the higher stage (here driven by the next_step side effect)."""
    app_obj = _application(client)
    _submit(client, app_obj["id"])
    _create_email_link(client, app_obj["id"], classified_status="confirmation")
    _create_email_link(client, app_obj["id"], classified_status="next_step")
    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "interview"
    assert fresh["timeline_stage"] == "interview"
    assert fresh["email_link_count"] == 2


# ---- Idempotency on (application_id, gmail_message_id) -------------------


def test_recreating_same_gmail_message_id_is_idempotent(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    msg_id = _manual_id()
    first = _create_email_link(
        client, app_obj["id"], gmail_message_id=msg_id, classified_status="rejection"
    )
    assert first.status_code == 201
    first_body = first.json()

    # Same message id, but a different classification on the body. The
    # endpoint must return the existing row and must NOT re-apply side
    # effects (so status stays "rejected" — not "offer").
    second = _create_email_link(
        client, app_obj["id"], gmail_message_id=msg_id, classified_status="offer"
    )
    assert second.status_code == 200
    assert second.json()["id"] == first_body["id"]
    assert second.json()["classified_status"] == "rejection"

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["status"] == "rejected"
    assert fresh["email_link_count"] == 1

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    email_events = [e for e in events if e["source"] == "email"]
    assert len(email_events) == 1


# ---- Error cases ---------------------------------------------------------


def test_create_email_link_404_for_missing_application(client):
    r = client.post(
        "/applications/does-not-exist/email-links",
        json={
            "gmail_message_id": _manual_id(),
            "classified_status": "confirmation",
        },
    )
    assert r.status_code == 404


def test_create_email_link_422_for_invalid_classified_status(client):
    app_obj = _application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": _manual_id(),
            "classified_status": "totally_invented",
        },
    )
    assert r.status_code == 422


def test_create_email_link_422_when_gmail_message_id_missing(client):
    app_obj = _application(client)
    r = client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={"classified_status": "confirmation"},
    )
    assert r.status_code == 422


def test_list_email_links_404_for_missing_application(client):
    r = client.get("/applications/does-not-exist/email-links")
    assert r.status_code == 404


# ---- Listing / ordering --------------------------------------------------


def test_list_email_links_ordered_received_then_created_desc(client):
    app_obj = _application(client)
    _submit(client, app_obj["id"])

    # Two with explicit received_at (newer first wins), one with null
    # (sorts last regardless of when it was created).
    r1 = _create_email_link(
        client,
        app_obj["id"],
        classified_status="other",
        received_at="2026-01-01T00:00:00+00:00",
    )
    r2 = _create_email_link(
        client,
        app_obj["id"],
        classified_status="other",
        received_at="2026-02-01T00:00:00+00:00",
    )
    r3 = _create_email_link(client, app_obj["id"], classified_status="other")
    for r in (r1, r2, r3):
        assert r.status_code == 201

    listing = client.get(f"/applications/{app_obj['id']}/email-links").json()
    assert [link["id"] for link in listing] == [
        r2.json()["id"],
        r1.json()["id"],
        r3.json()["id"],
    ]

    fresh = client.get(f"/applications/{app_obj['id']}").json()
    assert fresh["last_email_link"]["id"] == r2.json()["id"]
    assert fresh["email_link_count"] == 3


def test_list_email_links_empty(client):
    app_obj = _application(client)
    r = client.get(f"/applications/{app_obj['id']}/email-links")
    assert r.status_code == 200
    assert r.json() == []


# ---- N+1 avoidance on list_applications ----------------------------------


def test_list_applications_does_not_n_plus_one(client):
    """Eager loading guarantees one query for applications and one for the
    full set of attached email_links, regardless of application count."""
    from app.db import SessionLocal, engine
    from sqlalchemy import event

    # Create 3 applications, each with 2 email links.
    for _ in range(3):
        app_obj = _application(client)
        _submit(client, app_obj["id"])
        _create_email_link(client, app_obj["id"], classified_status="confirmation")
        _create_email_link(client, app_obj["id"], classified_status="other")

    queries: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", _record)
    try:
        resp = client.get("/applications")
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 3
    for app_read in body:
        assert app_read["email_link_count"] == 2
        assert app_read["last_email_link"] is not None
        assert app_read["timeline_stage"] in {
            "confirmation_received",
            "sent",
            "response_received",
        }

    # selectinload(Application.email_links) issues exactly one extra SELECT
    # for the email_links collection. With one application query + one
    # selectin batch we should see 2 SELECTs from email_links/applications;
    # SQLAlchemy may emit BEGIN/ROLLBACK too. Assert the email_links table
    # is queried no more than once.
    email_link_selects = [
        q for q in queries if "FROM email_links" in q or "from email_links" in q
    ]
    assert len(email_link_selects) == 1, queries
