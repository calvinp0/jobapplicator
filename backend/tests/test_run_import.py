from __future__ import annotations

import os
from pathlib import Path

import pytest


CANDIDATE_FILES = (
    "candidate_profile.md",
    "project_notes.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)

EXPECTED_OUTPUTS = (
    "tailored_resume.docx",
    "tailored_resume.md",
    "change_log.md",
    "claim_audit.md",
    "ats_audit.md",
)


def _seed_run(client, tmp_path: Path, monkeypatch) -> dict:
    """Set up candidate context + prompts, create a job + master resume, POST /runs."""
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\nbody\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# Prompt\nDo the thing.\n", encoding="utf-8"
    )
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    monkeypatch.setenv("JOBAPPLY_CANDIDATE_CONTEXT_ROOT", str(candidate_root))
    monkeypatch.setenv("JOBAPPLY_RUNTIME_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))

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
    resp = client.post(
        "/runs",
        json={"job_id": job["id"], "master_resume_id": resume["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _write_outputs(run_dir: Path, *, skip: tuple[str, ...] = ()) -> None:
    out = run_dir / "output"
    out.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED_OUTPUTS:
        if name in skip:
            continue
        # Use distinct content per file so hashes differ.
        (out / name).write_bytes(f"content for {name}\n".encode("utf-8"))


def _mark_completed(run_id: str) -> None:
    """Flip the ClaudeRun row to 'completed' by talking to the same DB."""
    from app.db import SessionLocal
    from app.models import ClaudeRun

    db = SessionLocal()
    try:
        run = db.get(ClaudeRun, run_id)
        assert run is not None
        run.status = "completed"
        db.commit()
    finally:
        db.close()


def test_import_success_creates_resume_version(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    run_dir = Path(run["run_dir"])
    _write_outputs(run_dir)
    _mark_completed(run["id"])

    resp = client.post(f"/runs/{run['id']}/import")
    assert resp.status_code == 201, resp.text
    version = resp.json()

    assert version["job_id"] == run["job_id"]
    assert version["master_resume_id"] == run["master_resume_id"]
    assert version["claude_run_id"] == run["id"]
    assert version["version_number"] == 1
    assert version["source"] == "claude_run"
    assert version["approved_at"] is None
    assert version["content_hash"]
    assert version["content_markdown"] == "content for tailored_resume.md\n"
    assert version["docx_path"].endswith("tailored_resume.docx")
    # prompt_hash carried over from the run.
    assert version["prompt_hash"] == run["prompt_hash"]

    # Run row updated.
    run_after = client.get(f"/runs/{run['id']}").json()
    assert run_after["status"] == "imported"
    assert run_after["output_hash"]

    # Exactly one resume version row exists.
    listing = client.get("/resume-versions").json()
    assert len(listing) == 1
    assert listing[0]["id"] == version["id"]


def test_import_rejects_run_not_completed(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    _write_outputs(Path(run["run_dir"]))
    # Note: not marking the run completed.

    resp = client.post(f"/runs/{run['id']}/import")
    assert resp.status_code == 400, resp.text
    assert "completed" in resp.json()["detail"].lower()

    # No version row created.
    assert client.get("/resume-versions").json() == []


def test_import_fails_on_missing_output(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    _write_outputs(Path(run["run_dir"]), skip=("claim_audit.md",))
    _mark_completed(run["id"])

    resp = client.post(f"/runs/{run['id']}/import")
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "claim_audit.md" in detail
    assert "missing" in detail.lower()

    # No version row created.
    assert client.get("/resume-versions").json() == []
    # Run status unchanged.
    assert client.get(f"/runs/{run['id']}").json()["status"] == "completed"


def test_import_rejects_output_outside_run_dir(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    run_dir = Path(run["run_dir"])
    _write_outputs(run_dir)
    _mark_completed(run["id"])

    # Replace one output with a symlink pointing outside the run directory.
    escape_target = tmp_path / "escape.docx"
    escape_target.write_bytes(b"contents outside the sandbox\n")
    victim = run_dir / "output" / "tailored_resume.docx"
    victim.unlink()
    victim.symlink_to(escape_target)

    resp = client.post(f"/runs/{run['id']}/import")
    assert resp.status_code == 400, resp.text
    assert "outside" in resp.json()["detail"].lower()

    # No version row created.
    assert client.get("/resume-versions").json() == []


def test_import_increments_version_number_per_job_resume(client, tmp_path, monkeypatch):
    # First run.
    run1 = _seed_run(client, tmp_path, monkeypatch)
    _write_outputs(Path(run1["run_dir"]))
    _mark_completed(run1["id"])
    v1 = client.post(f"/runs/{run1['id']}/import").json()
    assert v1["version_number"] == 1

    # Second run for the same (job, master_resume) pair.
    resp = client.post(
        "/runs",
        json={
            "job_id": run1["job_id"],
            "master_resume_id": run1["master_resume_id"],
        },
    )
    assert resp.status_code == 201, resp.text
    run2 = resp.json()
    _write_outputs(Path(run2["run_dir"]))
    _mark_completed(run2["id"])
    v2 = client.post(f"/runs/{run2['id']}/import").json()
    assert v2["version_number"] == 2
    assert v2["id"] != v1["id"]

    # A different master_resume should restart numbering at 1.
    other_resume = client.post(
        "/master-resumes",
        json={"name": "other", "content_markdown": "# other\n"},
    ).json()
    resp = client.post(
        "/runs",
        json={"job_id": run1["job_id"], "master_resume_id": other_resume["id"]},
    )
    assert resp.status_code == 201, resp.text
    run3 = resp.json()
    _write_outputs(Path(run3["run_dir"]))
    _mark_completed(run3["id"])
    v3 = client.post(f"/runs/{run3['id']}/import").json()
    assert v3["version_number"] == 1


def test_approval_sets_timestamp_and_is_idempotent(client, tmp_path, monkeypatch):
    """First /approve sets approved_at; a second call leaves it unchanged.

    We intentionally chose idempotent re-approval (rather than 409) so that
    retries and UI double-submits are safe. The contract is: callers that
    care about distinguishing "newly approved" from "already approved" must
    compare ``approved_at`` before and after.
    """
    run = _seed_run(client, tmp_path, monkeypatch)
    _write_outputs(Path(run["run_dir"]))
    _mark_completed(run["id"])
    version = client.post(f"/runs/{run['id']}/import").json()
    assert version["approved_at"] is None

    first = client.post(f"/resume-versions/{version['id']}/approve")
    assert first.status_code == 200, first.text
    approved_at = first.json()["approved_at"]
    assert approved_at is not None

    # Re-approval is a no-op: same timestamp, no error.
    second = client.post(f"/resume-versions/{version['id']}/approve")
    assert second.status_code == 200, second.text
    assert second.json()["approved_at"] == approved_at

    # GET reflects the approved timestamp.
    fetched = client.get(f"/resume-versions/{version['id']}").json()
    assert fetched["approved_at"] == approved_at


def test_approve_unknown_id_returns_404(client, tmp_path, monkeypatch):
    resp = client.post("/resume-versions/does-not-exist/approve")
    assert resp.status_code == 404
