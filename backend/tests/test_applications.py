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
