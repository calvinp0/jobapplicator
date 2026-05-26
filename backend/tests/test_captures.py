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


# ---- Firefox extension parity ----------------------------------------------
#
# The Firefox extension sends the same JobCaptureCreate payload as Chrome.
# These tests pin the cross-browser contract: the backend treats a capture
# from Firefox identically to one from Chrome, and rejects payloads missing
# the schema's required fields (external_url, source_platform, capture_method)
# regardless of which browser sent them.


def _firefox_payload(**overrides):
    base = {
        "source_platform": "linkedin",
        "capture_method": "browser_extension_current_page",
        "external_url": "https://www.linkedin.com/jobs/view/99",
        "external_job_id": "99",
        "company": "Firefox Co",
        "title": "Software Engineer",
        "location": "Remote",
        "description_text": "Ship Firefox extension support.",
        "application_method": "easy_apply",
        "raw_text": "Firefox Co — Software Engineer — Remote",
    }
    base.update(overrides)
    return base


def test_firefox_extension_capture_creates_capture(client):
    r = client.post("/captures", json=_firefox_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_platform"] == "linkedin"
    assert body["capture_method"] == "browser_extension_current_page"
    assert body["external_url"] == "https://www.linkedin.com/jobs/view/99"
    assert body["title"] == "Software Engineer"
    assert body["company"] == "Firefox Co"
    assert body["raw_text"] == "Firefox Co — Software Engineer — Remote"
    assert body["auto_confirmed"] is True
    assert body["job_id"]


def test_firefox_capture_payload_does_not_require_chrome_specific_fields(client):
    # The Chrome extension happens to be the only producer that has ever
    # exercised this endpoint. There must not be any latent Chrome-specific
    # required field that would block a Firefox capture from going through.
    payload = _firefox_payload()
    r = client.post("/captures", json=payload)
    assert r.status_code == 201, r.text


def test_capture_missing_external_url_returns_validation_error(client):
    payload = _firefox_payload()
    payload.pop("external_url")
    r = client.post("/captures", json=payload)
    assert r.status_code == 422, r.text


def test_firefox_capture_stored_url_title_and_page_text(client):
    r = client.post("/captures", json=_firefox_payload())
    capture_id = r.json()["id"]
    fetched = client.get(f"/captures/{capture_id}").json()
    assert fetched["external_url"] == "https://www.linkedin.com/jobs/view/99"
    assert fetched["title"] == "Software Engineer"
    assert fetched["raw_text"] == "Firefox Co — Software Engineer — Remote"
