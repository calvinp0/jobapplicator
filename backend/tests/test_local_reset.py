"""In-app reset of local data (task 121).

``POST /settings/reset-local-data`` backs up the SQLite database, then
clears local jobs/applications/runs/captures/drafts and the matching
generated run artifacts. It requires an explicit ``"RESET"`` confirmation
and must never delete files outside the project's runs root.
"""

from __future__ import annotations

import os
from pathlib import Path


def _complete_capture_payload(**overrides):
    payload = {
        "source_platform": "linkedin",
        "capture_method": "browser_extension_current_page",
        "external_url": "https://www.linkedin.com/jobs/view/987654321/",
        "company": "Acme",
        "title": "ML Engineer",
        "description_text": "Build models.",
    }
    payload.update(overrides)
    return payload


def test_reset_rejects_wrong_confirmation(client):
    resp = client.post(
        "/settings/reset-local-data", json={"confirmation": "nope"}
    )
    assert resp.status_code == 400
    assert "RESET" in resp.json()["detail"]


def test_reset_rejects_missing_confirmation(client):
    # No confirmation field at all -> request validation error.
    resp = client.post("/settings/reset-local-data", json={})
    assert resp.status_code == 422


def test_reset_succeeds_with_correct_confirmation(
    client, tmp_path, monkeypatch
):
    monkeypatch.setenv("JOBAPPLY_BACKUPS_ROOT", str(tmp_path / "backups"))

    # A complete capture auto-confirms into a job.
    created = client.post("/captures", json=_complete_capture_payload())
    assert created.status_code == 201, created.text
    assert client.get("/jobs").json()  # at least one job exists
    assert client.get("/captures").json()  # at least one capture exists

    resp = client.post(
        "/settings/reset-local-data", json={"confirmation": "RESET"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["deleted"]["jobs"] >= 1
    assert body["deleted"]["captures"] >= 1
    # A backup was written before the destructive step.
    assert body["backup_path"]
    assert os.path.exists(body["backup_path"])

    # Data is gone afterwards.
    assert client.get("/jobs").json() == []
    assert client.get("/captures").json() == []


def test_reset_does_not_delete_files_outside_project(
    client, tmp_path, monkeypatch
):
    monkeypatch.setenv("JOBAPPLY_BACKUPS_ROOT", str(tmp_path / "backups"))
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))

    inside = runs_root / "run-1"
    inside.mkdir()
    (inside / "artifact.txt").write_text("generated", encoding="utf-8")

    outside = tmp_path / "precious"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("do not delete", encoding="utf-8")

    # Insert run rows directly: one inside the runs root, one outside it.
    from app.db import SessionLocal
    from app.models import ClaudeRun, Job, MasterResume

    session = SessionLocal()
    try:
        job = Job(
            source_platform="linkedin",
            company="Acme",
            title="ML Engineer",
            description_text="build",
        )
        resume = MasterResume(name="m", content_markdown="x")
        session.add_all([job, resume])
        session.flush()
        session.add_all(
            [
                ClaudeRun(
                    job_id=job.id,
                    master_resume_id=resume.id,
                    run_dir=str(inside),
                    status="created",
                ),
                ClaudeRun(
                    job_id=job.id,
                    master_resume_id=resume.id,
                    run_dir=str(outside),
                    status="created",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    resp = client.post(
        "/settings/reset-local-data", json={"confirmation": "RESET"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"]["runs"] == 2

    # The run dir inside the runs root is cleaned up...
    assert not inside.exists()
    # ...but the directory outside the project is left completely untouched.
    assert outside.exists()
    assert sentinel.read_text(encoding="utf-8") == "do not delete"
