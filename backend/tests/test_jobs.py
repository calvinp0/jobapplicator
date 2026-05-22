def _job_payload(**overrides):
    base = {
        "source_platform": "linkedin",
        "external_url": "https://www.linkedin.com/jobs/view/1",
        "external_job_id": "1",
        "company": "Acme",
        "title": "Engineer",
        "location": "Remote",
        "description_text": "Do work.",
        "application_method": "easy_apply",
    }
    base.update(overrides)
    return base


def test_create_job_directly(client):
    r = client.post("/jobs", json=_job_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["company"] == "Acme"
    assert body["created_from_capture_id"] is None


def test_get_job_404(client):
    assert client.get("/jobs/no").status_code == 404
