def _job(client):
    payload = {
        "source_platform": "linkedin",
        "company": "Acme",
        "title": "Engineer",
        "description_text": "Do work.",
    }
    return client.post("/jobs", json=payload).json()


def test_create_application_for_job(client):
    job = _job(client)
    r = client.post("/applications", json={"job_id": job["id"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job_id"] == job["id"]
    assert body["status"] == "draft"
    assert body["resume_version_id"] is None


def test_application_cannot_reference_missing_job(client):
    r = client.post("/applications", json={"job_id": "does-not-exist"})
    assert r.status_code == 404


def test_application_invalid_status(client):
    job = _job(client)
    r = client.post(
        "/applications",
        json={"job_id": job["id"], "status": "totally_invented"},
    )
    assert r.status_code == 422


def test_submit_application_sets_status_and_creates_event(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    assert app_obj["status"] == "draft"
    assert app_obj["submitted_at"] is None

    r = client.post(f"/applications/{app_obj['id']}/submit")
    assert r.status_code == 200, r.text
    submitted = r.json()
    assert submitted["status"] == "submitted"
    assert submitted["submitted_at"] is not None

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "submitted"


def test_submit_application_is_idempotent(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()

    first = client.post(f"/applications/{app_obj['id']}/submit").json()
    second = client.post(f"/applications/{app_obj['id']}/submit").json()

    # submitted_at unchanged on the second call.
    assert first["submitted_at"] == second["submitted_at"]
    assert second["status"] == "submitted"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "submitted"


def test_submit_application_404_when_missing(client):
    r = client.post("/applications/does-not-exist/submit")
    assert r.status_code == 404


def test_create_and_list_events_in_order(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()

    e1 = client.post(
        f"/applications/{app_obj['id']}/events",
        json={"event_type": "viewed", "notes": "first touch"},
    )
    assert e1.status_code == 201, e1.text

    e2 = client.post(
        f"/applications/{app_obj['id']}/events",
        json={"event_type": "noted", "notes": "follow-up"},
    )
    assert e2.status_code == 201

    listing = client.get(f"/applications/{app_obj['id']}/events").json()
    assert [e["event_type"] for e in listing] == ["viewed", "noted"]
    # Event_times are non-decreasing.
    times = [e["event_time"] for e in listing]
    assert times == sorted(times)


def test_events_endpoints_404_for_missing_application(client):
    r = client.post(
        "/applications/does-not-exist/events",
        json={"event_type": "viewed"},
    )
    assert r.status_code == 404

    r = client.get("/applications/does-not-exist/events")
    assert r.status_code == 404


# ---- Dashboard status fields --------------------------------------------


def test_new_application_dashboard_defaults(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    assert app_obj["status"] == "draft"
    assert app_obj["submission_status"] == "not_submitted"
    assert app_obj["email_status"] == "not_watching"
    assert app_obj["next_action"]  # non-empty string for any status
    assert app_obj["last_email_at"] is None


def test_submitted_application_has_submitted_submission_status(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    submitted = client.post(f"/applications/{app_obj['id']}/submit").json()
    assert submitted["submission_status"] == "submitted"
    # No emails attached yet; we're "watching" for one to arrive.
    assert submitted["email_status"] == "watching"
    assert submitted["next_action"] == "Waiting for email"


def test_mark_rejected_updates_status(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    r = client.post(f"/applications/{app_obj['id']}/mark-rejected")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rejected"
    assert body["timeline_stage"] == "rejected"
    assert body["next_action"] == "Rejected"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    assert any(e["event_type"] == "marked_rejected" for e in events)


def test_mark_rejected_is_idempotent(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    client.post(f"/applications/{app_obj['id']}/mark-rejected")
    client.post(f"/applications/{app_obj['id']}/mark-rejected")
    events = client.get(f"/applications/{app_obj['id']}/events").json()
    assert sum(1 for e in events if e["event_type"] == "marked_rejected") == 1


def test_mark_interview_updates_status(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    r = client.post(f"/applications/{app_obj['id']}/mark-interview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "interview"
    assert body["timeline_stage"] == "interview"
    assert body["next_action"] == "Interview response needed"

    events = client.get(f"/applications/{app_obj['id']}/events").json()
    assert any(e["event_type"] == "marked_interview" for e in events)


def test_mark_status_404_when_missing(client):
    assert client.post("/applications/does-not-exist/mark-rejected").status_code == 404
    assert (
        client.post("/applications/does-not-exist/mark-interview").status_code == 404
    )


def test_application_list_sorts_by_updated_at_with_priority(client):
    # Create three applications across three jobs.
    job_a = _job(client)
    job_b = _job(client)
    job_c = _job(client)
    app_a = client.post("/applications", json={"job_id": job_a["id"]}).json()
    app_b = client.post("/applications", json={"job_id": job_b["id"]}).json()
    app_c = client.post("/applications", json={"job_id": job_c["id"]}).json()

    # Mark one rejected (closed) and one as submitted (open). The remaining
    # draft application should sort above the rejected one even if rejected
    # was updated more recently, because closed states have lower priority.
    client.post(f"/applications/{app_b['id']}/submit")
    client.post(f"/applications/{app_c['id']}/mark-rejected")

    listing = client.get("/applications").json()
    ids_in_order = [row["id"] for row in listing]
    # Drafts and submitted come before rejected.
    assert ids_in_order.index(app_c["id"]) > ids_in_order.index(app_a["id"])
    assert ids_in_order.index(app_c["id"]) > ids_in_order.index(app_b["id"])


def test_application_email_status_reflects_classification(client):
    job = _job(client)
    app_obj = client.post("/applications", json={"job_id": job["id"]}).json()
    client.post(f"/applications/{app_obj['id']}/submit")
    client.post(
        f"/applications/{app_obj['id']}/email-links",
        json={
            "gmail_message_id": "manual:abc",
            "classified_status": "rejection",
        },
    )
    reloaded = client.get(f"/applications/{app_obj['id']}").json()
    # Recording a rejection email transitions Application.status to rejected.
    assert reloaded["status"] == "rejected"
    assert reloaded["email_status"] == "classified_rejection"
    assert reloaded["last_email_at"] is not None
