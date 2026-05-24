"""HTTP-layer tests for the revision-feedback endpoint (task 045, ADR-008).

The endpoint at ``POST /resume-versions/{id}/revision-feedback`` performs
three actions atomically from the caller's perspective: insert a
``revision_feedbacks`` row, create a follow-up ``ClaudeRun``, and stage
``input/revision_feedback.md`` into the new run directory. These tests
cover the happy path, 404 on missing source draft, 422 on schema
violation, the join-row FK linking the feedback to the new run, and the
feedback file landing inside the new run's input dir.
"""

from __future__ import annotations

from pathlib import Path


CANDIDATE_FILES = (
    "candidate_profile.md",
    "project_notes.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)


def _prime_fs(tmp_path: Path, monkeypatch) -> Path:
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# Prompt\nRead inputs and write outputs.\n", encoding="utf-8"
    )
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    monkeypatch.setenv("JOBAPPLY_CANDIDATE_CONTEXT_ROOT", str(candidate_root))
    monkeypatch.setenv("JOBAPPLY_RUNTIME_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))
    return runs_root


def _seed_draft(client, tmp_path: Path, monkeypatch) -> dict:
    """Create a job + master resume + first-draft ResumeVersion via the API.

    Returns the imported resume_version dict so tests can submit feedback
    against a real prior draft.
    """
    _prime_fs(tmp_path, monkeypatch)

    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build things",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()

    run = client.post(
        "/runs",
        json={"job_id": job["id"], "master_resume_id": resume["id"]},
    ).json()

    run_dir = Path(run["run_dir"])
    out = run_dir / "output"
    out.mkdir(parents=True, exist_ok=True)
    for name in (
        "tailored_resume.docx",
        "tailored_resume.md",
        "change_log.md",
        "claim_audit.md",
    ):
        (out / name).write_bytes(f"content for {name}\n".encode("utf-8"))

    from app.db import SessionLocal
    from app.models import ClaudeRun

    db = SessionLocal()
    try:
        row = db.get(ClaudeRun, run["id"])
        assert row is not None
        row.status = "completed"
        db.commit()
    finally:
        db.close()

    version = client.post(f"/runs/{run['id']}/import").json()
    return version


def test_revision_feedback_happy_path_creates_row_run_and_file(
    client, tmp_path, monkeypatch
):
    draft = _seed_draft(client, tmp_path, monkeypatch)

    resp = client.post(
        f"/resume-versions/{draft['id']}/revision-feedback",
        json={
            "feedback_markdown": "Soften the executive framing in the summary.",
            "structured_flags": {"too_long": True},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # The response carries enough info for the frontend to route to the
    # new run: the join-row id, the source draft id, and the follow-up
    # ClaudeRun id.
    assert body["source_resume_version_id"] == draft["id"]
    assert body["followup_claude_run_id"]
    assert body["job_id"] == draft["job_id"]
    assert body["status"] == "created"
    assert body["feedback_markdown"].startswith("Soften")

    # The follow-up run exists and has its run directory populated.
    run = client.get(f"/runs/{body['followup_claude_run_id']}").json()
    assert run["status"] == "created"
    run_dir = Path(run["run_dir"])
    assert run_dir.is_dir()

    feedback_file = run_dir / "input" / "revision_feedback.md"
    assert feedback_file.is_file()
    contents = feedback_file.read_text(encoding="utf-8")
    assert f"source_resume_version_id: {draft['id']}" in contents
    assert "Soften the executive framing" in contents
    assert "too_long" in contents


def test_revision_feedback_creates_exactly_one_record_and_one_run(
    client, tmp_path, monkeypatch
):
    """One submission ⇒ one feedback row, one new ClaudeRun (separate from prior)."""
    draft = _seed_draft(client, tmp_path, monkeypatch)
    prior_run_id = draft["claude_run_id"]

    resp = client.post(
        f"/resume-versions/{draft['id']}/revision-feedback",
        json={"feedback_markdown": "Trim the second bullet."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # The new ClaudeRun is distinct from the run that produced the source draft.
    assert body["followup_claude_run_id"] != prior_run_id

    # FK link is populated (ADR-008's "join row" model).
    from app.db import SessionLocal
    from app.models import RevisionFeedback

    db = SessionLocal()
    try:
        rows = db.query(RevisionFeedback).all()
        assert len(rows) == 1
        only = rows[0]
        assert only.source_resume_version_id == draft["id"]
        assert only.followup_claude_run_id == body["followup_claude_run_id"]
        assert only.status == "created"
    finally:
        db.close()

    # Only one extra ClaudeRun was created (the prior + the follow-up).
    runs = client.get("/runs").json()
    assert len(runs) == 2
    follow_up_ids = {r["id"] for r in runs} - {prior_run_id}
    assert follow_up_ids == {body["followup_claude_run_id"]}


def test_revision_feedback_missing_source_draft_returns_404(
    client, tmp_path, monkeypatch
):
    _prime_fs(tmp_path, monkeypatch)

    resp = client.post(
        "/resume-versions/does-not-exist/revision-feedback",
        json={"feedback_markdown": "Anything."},
    )
    assert resp.status_code == 404
    assert "resume version" in resp.json()["detail"].lower()


def test_revision_feedback_empty_body_returns_422(client, tmp_path, monkeypatch):
    draft = _seed_draft(client, tmp_path, monkeypatch)

    resp = client.post(
        f"/resume-versions/{draft['id']}/revision-feedback",
        json={"feedback_markdown": ""},
    )
    assert resp.status_code == 422


def test_revision_feedback_missing_field_returns_422(client, tmp_path, monkeypatch):
    draft = _seed_draft(client, tmp_path, monkeypatch)

    resp = client.post(
        f"/resume-versions/{draft['id']}/revision-feedback",
        json={},
    )
    assert resp.status_code == 422


def test_revision_feedback_followup_run_input_dir_contains_expected_files(
    client, tmp_path, monkeypatch
):
    """The follow-up run dir has the standard input set PLUS revision_feedback.md."""
    draft = _seed_draft(client, tmp_path, monkeypatch)

    resp = client.post(
        f"/resume-versions/{draft['id']}/revision-feedback",
        json={"feedback_markdown": "Please tighten the bullets under Acme."},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    run = client.get(f"/runs/{body['followup_claude_run_id']}").json()
    input_dir = Path(run["run_dir"]) / "input"
    present = {p.name for p in input_dir.iterdir() if p.is_file()}

    expected = {
        "job_description.md",
        "master_resume.md",
        "evidence_bank.md",
        "candidate_profile.md",
        "project_notes.md",
        "skills_inventory.md",
        "tailoring_preferences.md",
        "resume_dos_and_donts.md",
        "tailoring_prompt.md",
        "revision_feedback.md",
    }
    assert present == expected
