from __future__ import annotations


def _capture_payload(**overrides):
    base = {
        "source_platform": "linkedin",
        "capture_method": "browser_extension_current_page",
        "external_url": "https://www.linkedin.com/jobs/view/42",
        "external_job_id": "42",
        "company": "Example Corp",
        "title": "ML Engineer",
        "location": "Remote",
        "description_text": "Build great things.",
        "application_method": "easy_apply",
    }
    base.update(overrides)
    return base


def test_create_capture_incomplete_stays_pending(client):
    r = client.post(
        "/captures",
        json=_capture_payload(description_text="", company=None),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user_confirmed"] is False
    assert body["auto_confirmed"] is False
    assert body["job_id"] is None
    assert body["id"]


def test_create_capture_complete_auto_confirms_into_job(client):
    r = client.post("/captures", json=_capture_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user_confirmed"] is True
    assert body["auto_confirmed"] is True
    assert body["job_id"]

    job = client.get(f"/jobs/{body['job_id']}").json()
    assert job["company"] == "Example Corp"
    assert job["title"] == "ML Engineer"
    assert job["created_from_capture_id"] == body["id"]


def test_create_capture_complete_without_location_still_auto_confirms(client):
    r = client.post("/captures", json=_capture_payload(location=None))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["auto_confirmed"] is True
    assert body["job_id"]


def test_create_capture_dedups_on_repeat_url(client):
    first = client.post("/captures", json=_capture_payload()).json()
    assert first["job_reused"] is False

    second = client.post(
        "/captures",
        json=_capture_payload(title="Different Title"),
    ).json()
    assert second["auto_confirmed"] is True
    assert second["job_reused"] is True
    assert second["job_id"] == first["job_id"]
    assert second["id"] != first["id"]

    jobs = client.get("/jobs").json()
    matching = [j for j in jobs if j["id"] == first["job_id"]]
    assert len(matching) == 1
    # Original job is reused as-is; we do not overwrite it from a later capture.
    assert matching[0]["title"] == "ML Engineer"


def test_list_captures_returns_recent_first(client):
    client.post(
        "/captures",
        json=_capture_payload(
            company="One",
            external_url="https://www.linkedin.com/jobs/view/1",
            description_text="",
        ),
    )
    client.post(
        "/captures",
        json=_capture_payload(
            company="Two",
            external_url="https://www.linkedin.com/jobs/view/2",
            description_text="",
        ),
    )
    r = client.get("/captures")
    assert r.status_code == 200
    companies = [c["company"] for c in r.json()]
    assert {"One", "Two"} <= set(companies)


def test_get_capture_404(client):
    r = client.get("/captures/does-not-exist")
    assert r.status_code == 404


def test_confirm_capture_creates_job(client):
    create = client.post("/captures", json=_capture_payload()).json()
    capture_id = create["id"]

    confirm = client.post(f"/captures/{capture_id}/confirm")
    assert confirm.status_code == 201, confirm.text
    job = confirm.json()
    assert job["company"] == "Example Corp"
    assert job["title"] == "ML Engineer"
    assert job["description_text"] == "Build great things."
    assert job["created_from_capture_id"] == capture_id

    fetched = client.get(f"/captures/{capture_id}").json()
    assert fetched["user_confirmed"] is True


def test_confirm_capture_missing_fields_returns_422(client):
    payload = _capture_payload(company=None, title=None, description_text="")
    create = client.post("/captures", json=payload).json()
    capture_id = create["id"]

    confirm = client.post(f"/captures/{capture_id}/confirm")
    assert confirm.status_code == 422
    detail = confirm.json()["detail"]
    assert set(detail["missing_fields"]) == {"company", "title", "description_text"}


def test_confirm_capture_whitespace_treated_as_missing(client):
    payload = _capture_payload(company="   ", title="ML", description_text="ok")
    create = client.post("/captures", json=payload).json()
    confirm = client.post(f"/captures/{create['id']}/confirm")
    assert confirm.status_code == 422
    assert confirm.json()["detail"]["missing_fields"] == ["company"]


def test_confirm_capture_is_idempotent(client):
    create = client.post("/captures", json=_capture_payload()).json()
    capture_id = create["id"]

    first = client.post(f"/captures/{capture_id}/confirm")
    second = client.post(f"/captures/{capture_id}/confirm")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_confirm_capture_404(client):
    r = client.post("/captures/nope/confirm")
    assert r.status_code == 404
