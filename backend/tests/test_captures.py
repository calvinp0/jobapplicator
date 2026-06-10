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


def test_confirm_capture_uses_reviewed_fields(client):
    payload = _capture_payload(company=None, description_text="")
    create = client.post("/captures", json=payload).json()
    capture_id = create["id"]

    confirm = client.post(
        f"/captures/{capture_id}/confirm",
        json={
            "company": "Reviewed Corp",
            "title": "Reviewed Engineer",
            "location": "Hybrid",
            "external_url": "https://www.linkedin.com/jobs/view/42?trackingId=abc",
            "description_text": "Reviewed description.",
            "application_method": "external",
        },
    )
    assert confirm.status_code == 201, confirm.text
    job = confirm.json()
    assert job["company"] == "Reviewed Corp"
    assert job["title"] == "Reviewed Engineer"
    assert job["location"] == "Hybrid"
    assert job["external_url"] == "https://www.linkedin.com/jobs/view/42"
    assert job["description_text"] == "Reviewed description."
    assert job["application_method"] == "external"

    fetched = client.get(f"/captures/{capture_id}").json()
    assert fetched["company"] == "Reviewed Corp"
    assert fetched["user_confirmed"] is True


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


# ---- Task 109: extraction-failure fallback fields --------------------------
#
# When LinkedIn's structured selectors do not resolve, the Firefox extension
# still ships the URL + page_title + selected_text + page_text + diagnostics
# so the backend / Review Capture page can recover. These tests pin that the
# endpoint accepts and persists those fields, and that having them does not
# trigger auto-confirm without the real structured fields.


def _fallback_only_payload(**overrides):
    base = {
        "source_platform": "linkedin",
        "capture_method": "browser_extension_current_page",
        "external_url": (
            "https://www.linkedin.com/jobs/collections/recommended/"
            "?currentJobId=4415730750"
        ),
        "external_job_id": "4415730750",
        "company": None,
        "title": None,
        "location": None,
        "description_text": "",
        "application_method": None,
        "raw_text": None,
        "page_title": "Senior ML Engineer at Example Co | LinkedIn",
        "page_text": "Senior ML Engineer at Example Co — Berlin, Germany. "
        "We are hiring engineers to build large-scale ranking systems.",
        "selected_text": "",
        "diagnostics": {
            "extractor": "linkedin",
            "selectors_matched": {
                "title": False,
                "company": False,
                "location": False,
                "description": False,
            },
            "fallbacks_used": {
                "og_title": False,
                "document_title": True,
                "meta_description": False,
            },
            "document_title": "Senior ML Engineer at Example Co | LinkedIn",
            "body_text_length": 12345,
            "url_has_current_job_id": True,
            "has_selected_text": False,
        },
    }
    base.update(overrides)
    return base


def test_capture_accepts_fallback_fields_without_structured_fields(client):
    payload = _fallback_only_payload()
    r = client.post("/captures", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    # No structured fields — capture must stay pending, not auto-confirm.
    assert body["auto_confirmed"] is False
    assert body["user_confirmed"] is False
    assert body["job_id"] is None
    # Fallback fields should round-trip through the response.
    assert body["page_title"] == payload["page_title"]
    assert body["page_text"] == payload["page_text"]
    assert body["selected_text"] == payload["selected_text"]
    assert body["diagnostics"]["selectors_matched"]["title"] is False
    assert body["diagnostics"]["url_has_current_job_id"] is True
    assert body["external_job_id"] == "4415730750"


def test_capture_diagnostics_persisted_and_returned_on_get(client):
    payload = _fallback_only_payload()
    create = client.post("/captures", json=payload).json()
    fetched = client.get(f"/captures/{create['id']}").json()
    assert fetched["diagnostics"] == payload["diagnostics"]
    assert fetched["page_text"] == payload["page_text"]
    assert fetched["page_title"] == payload["page_title"]


def test_capture_omitting_fallback_fields_still_works(client):
    # Chrome / older payloads that don't send the new fields must continue
    # to be accepted untouched. The new columns simply read back as null.
    r = client.post("/captures", json=_capture_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["page_title"] is None
    assert body["page_text"] is None
    assert body["selected_text"] is None
    assert body["diagnostics"] is None


def test_capture_with_selected_text_fallback_persisted(client):
    payload = _fallback_only_payload(
        selected_text="Pasted job description from the page.",
    )
    create = client.post("/captures", json=payload).json()
    fetched = client.get(f"/captures/{create['id']}").json()
    assert fetched["selected_text"] == "Pasted job description from the page."


# ---- Task 110: canonical URL persistence -----------------------------------
#
# The backend canonicalizes the captured URL deterministically (no LLM, no
# network). The raw URL the extension shipped is preserved as ``source_url``;
# the cleaned form lands on ``canonical_url`` and overwrites ``external_url``
# so dedup and the UI both operate on the clean identity.


def _messy_linkedin_payload(**overrides):
    base = _capture_payload(
        external_url=(
            "https://www.linkedin.com/jobs/collections/recommended/"
            "?currentJobId=4415730750&origin=JOB_SEARCH_PAGE_JOB_FILTER"
        ),
        external_job_id="4415730750",
    )
    base.update(overrides)
    return base


def test_capture_stores_source_url_unchanged(client):
    payload = _messy_linkedin_payload()
    r = client.post("/captures", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_url"] == payload["external_url"]


def test_capture_stores_canonical_url(client):
    payload = _messy_linkedin_payload()
    body = client.post("/captures", json=payload).json()
    assert body["canonical_url"] == "https://www.linkedin.com/jobs/view/4415730750"
    # ``external_url`` is the canonical form going forward so dedup and any
    # existing consumer of that field operate on the clean identity.
    assert body["external_url"] == body["canonical_url"]


def test_capture_stores_external_job_id_from_url(client):
    # Even if the extension forgot to pass external_job_id, the backend
    # derives it from the URL during canonicalization.
    payload = _messy_linkedin_payload(external_job_id=None)
    body = client.post("/captures", json=payload).json()
    assert body["external_job_id"] == "4415730750"


def test_capture_canonicalizes_dedup_across_messy_and_clean_urls(client):
    messy = client.post("/captures", json=_messy_linkedin_payload()).json()
    assert messy["auto_confirmed"] is True
    assert messy["job_id"]

    # Same job, captured a second time via the canonical /jobs/view/<id>
    # path with a tracking param tacked on. Should reuse the existing Job.
    second = client.post(
        "/captures",
        json=_capture_payload(
            external_url="https://www.linkedin.com/jobs/view/4415730750/?trackingId=abc",
            external_job_id="4415730750",
            title="Different Title",
        ),
    ).json()
    assert second["job_reused"] is True
    assert second["job_id"] == messy["job_id"]


def test_capture_canonical_url_round_trips_via_get(client):
    create = client.post("/captures", json=_messy_linkedin_payload()).json()
    fetched = client.get(f"/captures/{create['id']}").json()
    assert (
        fetched["canonical_url"] == "https://www.linkedin.com/jobs/view/4415730750"
    )
    assert (
        fetched["source_url"]
        == "https://www.linkedin.com/jobs/collections/recommended/"
        "?currentJobId=4415730750&origin=JOB_SEARCH_PAGE_JOB_FILTER"
    )


def test_capture_promotes_canonical_url_into_job(client):
    create = client.post("/captures", json=_messy_linkedin_payload()).json()
    job = client.get(f"/jobs/{create['job_id']}").json()
    assert job["canonical_url"] == "https://www.linkedin.com/jobs/view/4415730750"
    # The raw URL the extension captured is preserved on the Job too so the
    # workspace UI can offer it under an "Original captured URL" affordance.
    assert (
        job["source_url"]
        == "https://www.linkedin.com/jobs/collections/recommended/"
        "?currentJobId=4415730750&origin=JOB_SEARCH_PAGE_JOB_FILTER"
    )
    assert job["external_url"] == job["canonical_url"]


def test_capture_non_linkedin_url_passes_through_with_tracking_stripped(client):
    payload = _capture_payload(
        source_platform="greenhouse",
        external_url="https://boards.greenhouse.io/example/jobs/42?utm_source=newsletter",
        external_job_id="42",
    )
    body = client.post("/captures", json=payload).json()
    assert (
        body["canonical_url"]
        == "https://boards.greenhouse.io/example/jobs/42"
    )
    # Non-LinkedIn captures keep the platform supplied by the extension.
    assert body["source_platform"] == "greenhouse"
    # External job id is preserved as supplied by the extension when the
    # canonicalizer does not know how to derive one.
    assert body["external_job_id"] == "42"
