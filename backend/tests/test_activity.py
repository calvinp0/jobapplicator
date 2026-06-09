from __future__ import annotations

from datetime import datetime, timezone


def _seed_job_and_resume(session):
    """Insert a Job + MasterResume directly so runs can reference them.

    The activity endpoint only reads lifecycle state, so tests build run
    rows directly (rather than driving the worker) to pin exact statuses.
    """
    from app.models import Job, MasterResume

    job = Job(
        source_platform="linkedin",
        company="Example Aero Labs",
        title="Scientific Machine Learning Engineer",
        description_text="Build things.",
    )
    resume = MasterResume(name="main", content_markdown="# resume\n")
    session.add_all([job, resume])
    session.flush()
    return job, resume


def _add_run(session, job, resume, status, *, error_message=None):
    from app.models import ClaudeRun

    run = ClaudeRun(
        job_id=job.id,
        master_resume_id=resume.id,
        run_dir=f"runs/{status}-run",
        status=status,
        error_message=error_message,
    )
    if status in ("running", "completed", "failed", "imported"):
        run.started_at = datetime.now(timezone.utc)
    if status in ("completed", "failed", "imported"):
        run.completed_at = datetime.now(timezone.utc)
    session.add(run)
    session.flush()
    return run


def test_activity_empty_is_all_clear(client):
    resp = client.get("/activity")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == {
        "running_count": 0,
        "attention_count": 0,
        "pending_capture_count": 0,
    }
    assert body["items"] == []


def test_activity_returns_running_runs(client):
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        job, resume = _seed_job_and_resume(session)
        run = _add_run(session, job, resume, "running")
        session.commit()
        run_id = run.id
    finally:
        session.close()

    body = client.get("/activity").json()
    assert body["summary"]["running_count"] == 1
    running = [i for i in body["items"] if i["group"] == "running"]
    assert len(running) == 1
    item = running[0]
    assert item["id"] == run_id
    assert item["type"] == "tailoring_run"
    assert item["status"] == "running"
    assert item["title"] == "Tailoring resume"
    assert "Scientific Machine Learning Engineer" in item["subtitle"]
    assert item["href"] == f"/runs/{run_id}"


def test_activity_returns_failed_runs_as_attention(client):
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        job, resume = _seed_job_and_resume(session)
        run = _add_run(
            session,
            job,
            resume,
            "failed",
            error_message="Missing tailored_resume.json\nstack trace line",
        )
        session.commit()
        run_id = run.id
    finally:
        session.close()

    body = client.get("/activity").json()
    assert body["summary"]["attention_count"] == 1
    attention = [i for i in body["items"] if i["group"] == "attention"]
    assert len(attention) == 1
    item = attention[0]
    assert item["id"] == run_id
    assert item["status"] == "failed"
    assert item["title"] == "Tailoring failed"
    # Only the first line of the error surfaces in the popover row.
    assert item["detail"] == "Missing tailored_resume.json"
    assert item["href"] == f"/runs/{run_id}"


def test_activity_includes_pending_captures(client):
    capture = client.post(
        "/captures",
        json={
            "source_platform": "linkedin",
            "capture_method": "browser_extension_current_page",
            "external_url": "https://www.linkedin.com/jobs/view/99",
            # Intentionally incomplete (no company) so it stays pending.
            "title": "Research Engineer",
            "description_text": "",
        },
    ).json()
    assert capture["user_confirmed"] is False

    body = client.get("/activity").json()
    assert body["summary"]["pending_capture_count"] == 1
    assert body["summary"]["attention_count"] == 1
    pending = [i for i in body["items"] if i["type"] == "pending_capture"]
    assert len(pending) == 1
    item = pending[0]
    assert item["group"] == "attention"
    assert item["title"] == "Capture needs review"
    assert item["href"] == f"/captures/{capture['id']}"


def test_activity_items_carry_valid_hrefs(client):
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        job, resume = _seed_job_and_resume(session)
        _add_run(session, job, resume, "running")
        _add_run(session, job, resume, "failed", error_message="boom")
        _add_run(session, job, resume, "completed")
        session.commit()
    finally:
        session.close()

    body = client.get("/activity").json()
    assert body["items"], "expected at least one activity item"
    for item in body["items"]:
        assert item["href"].startswith("/runs/") or item["href"].startswith(
            "/captures/"
        )
        # Every href points at a concrete id, never a bare prefix.
        assert item["href"].rsplit("/", 1)[-1]


def test_activity_completed_runs_land_in_recent(client):
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        job, resume = _seed_job_and_resume(session)
        _add_run(session, job, resume, "completed")
        session.commit()
    finally:
        session.close()

    body = client.get("/activity").json()
    assert body["summary"]["running_count"] == 0
    assert body["summary"]["attention_count"] == 0
    recent = [i for i in body["items"] if i["group"] == "recent"]
    assert len(recent) == 1
    assert recent[0]["title"] == "Tailoring complete"
