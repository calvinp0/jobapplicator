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
