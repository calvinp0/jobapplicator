from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest


CANDIDATE_FILES = (
    "candidate_profile.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)

EXPECTED_INPUT_FILES = {
    "job_description.md",
    "master_resume.md",
    "evidence_bank.md",
    "candidate_profile.md",
    "project_notes.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
    "tailoring_prompt.md",
}


@pytest.fixture()
def fixture_layout(tmp_path: Path) -> dict[str, Path]:
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\nstable content\n", encoding="utf-8")
    notes_dir = candidate_root / "project_notes"
    notes_dir.mkdir()
    (notes_dir / "alpha.md").write_text("alpha note\n", encoding="utf-8")
    (notes_dir / "beta.md").write_text("beta note\n", encoding="utf-8")

    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# Prompt\nRead inputs and write outputs.\n", encoding="utf-8"
    )

    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    return {
        "candidate_root": candidate_root,
        "prompts_root": prompts_root,
        "runs_root": runs_root,
    }


def _make_objects():
    from app.models import EvidenceBank, Job, MasterResume

    job = Job(
        id="job-1",
        source_platform="linkedin",
        external_url="https://example.com/job/1",
        company="Acme",
        title="ML Engineer",
        location="Remote",
        description_text="Build ML systems.",
        application_method="form",
    )
    resume = MasterResume(
        id="resume-1",
        name="main",
        content_markdown="# Master Resume\nExperience: ...\n",
    )
    evidence = EvidenceBank(
        id="evidence-1",
        name="main",
        content_markdown="# Evidence\nProject X: shipped.\n",
    )
    return job, resume, evidence


def test_create_run_directory_layout(fixture_layout):
    from app.run_directory import create_run_directory

    job, resume, evidence = _make_objects()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
    )

    assert info.run_dir.is_dir()
    assert (info.run_dir / "input").is_dir()
    assert (info.run_dir / "output").is_dir()
    assert (info.run_dir / "metadata.json").is_file()

    present = {p.name for p in (info.run_dir / "input").iterdir() if p.is_file()}
    assert present == EXPECTED_INPUT_FILES


def test_project_notes_concatenated_from_directory(fixture_layout):
    from app.run_directory import create_run_directory

    job, resume, evidence = _make_objects()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
    )
    notes = (info.run_dir / "input" / "project_notes.md").read_text(encoding="utf-8")
    assert "alpha note" in notes
    assert "beta note" in notes


def test_hashes_stable_across_runs(fixture_layout):
    from app.run_directory import create_run_directory

    job, resume, evidence = _make_objects()
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    a = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
        now=fixed_now,
    )
    b = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
        now=fixed_now,
    )
    assert a.run_id != b.run_id
    assert a.prompt_hash == b.prompt_hash
    assert a.input_hash == b.input_hash


def test_metadata_json_well_formed(fixture_layout):
    from app.run_directory import EXPECTED_OUTPUTS, create_run_directory

    job, resume, evidence = _make_objects()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
    )
    metadata = json.loads((info.run_dir / "metadata.json").read_text(encoding="utf-8"))

    required = {
        "run_id",
        "job_id",
        "master_resume_id",
        "capture_method",
        "created_at",
        "input_files",
        "expected_outputs",
        "prompt_hash",
        "input_hash",
    }
    assert required <= set(metadata.keys())
    assert metadata["run_id"] == info.run_id
    assert metadata["job_id"] == "job-1"
    assert metadata["master_resume_id"] == "resume-1"
    assert metadata["evidence_bank_id"] == "evidence-1"
    assert metadata["expected_outputs"] == list(EXPECTED_OUTPUTS)
    assert metadata["prompt_hash"] == info.prompt_hash
    assert metadata["input_hash"] == info.input_hash
    # Every input file should appear in the input_files map with a sha256 hex.
    assert set(metadata["input_files"].keys()) == EXPECTED_INPUT_FILES
    for digest in metadata["input_files"].values():
        assert len(digest) == 64
        int(digest, 16)  # parseable as hex


def test_evidence_bank_optional(fixture_layout):
    from app.run_directory import create_run_directory

    job, resume, _ = _make_objects()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=None,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
    )
    text = (info.run_dir / "input" / "evidence_bank.md").read_text(encoding="utf-8")
    assert "(none provided)" in text
    metadata = json.loads((info.run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["evidence_bank_id"] is None


def test_missing_candidate_context_errors(fixture_layout, tmp_path):
    from app.run_directory import RunDirectoryError, create_run_directory

    job, resume, _ = _make_objects()
    bare_candidate_root = tmp_path / "empty_candidate"
    bare_candidate_root.mkdir()  # exists but missing required files

    with pytest.raises(RunDirectoryError, match="candidate_profile.md"):
        create_run_directory(
            job=job,
            master_resume=resume,
            evidence_bank=None,
            candidate_context_root=bare_candidate_root,
            runs_root=fixture_layout["runs_root"],
            runtime_prompts_root=fixture_layout["prompts_root"],
        )


def test_post_run_missing_master_resume_returns_404(client, tmp_path, monkeypatch):
    # Prime a candidate context + prompts dir + runs dir so the router could
    # succeed if the resume existed.
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\n", encoding="utf-8")
    (candidate_root / "project_notes.md").write_text("notes\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text("# prompt\n", encoding="utf-8")
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

    resp = client.post(
        "/runs",
        json={"job_id": job["id"], "master_resume_id": "does-not-exist"},
    )
    assert resp.status_code == 404
    assert "master resume" in resp.json()["detail"].lower()


def test_post_run_creates_row_and_directory(client, tmp_path, monkeypatch):
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\n", encoding="utf-8")
    (candidate_root / "project_notes.md").write_text("notes\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text("# prompt\n", encoding="utf-8")
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
    body = resp.json()
    assert body["status"] == "created"
    assert body["prompt_hash"]
    assert body["input_hash"]
    run_dir = Path(body["run_dir"])
    assert run_dir.is_dir()
    assert (run_dir / "metadata.json").is_file()

    # GET endpoints round-trip
    listed = client.get("/runs").json()
    assert any(r["id"] == body["id"] for r in listed)
    one = client.get(f"/runs/{body['id']}").json()
    assert one["id"] == body["id"]

    # Cleanup the created run dir from outside tmp_path's auto-cleanup scope —
    # in this test it lives under tmp_path, so pytest will handle it.
    shutil.rmtree(run_dir, ignore_errors=True)
