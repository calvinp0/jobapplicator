from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest


CANDIDATE_FILES = (
    "candidate_profile.md",
    "project_notes.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)


def _write_fake_binary(
    tmp_path: Path,
    *,
    exit_code: int = 0,
    extra_body: str = "",
) -> Path:
    """Write an executable Python script that imitates Claude Code.

    Writes a marker file (``where_am_i.txt``) recording the subprocess cwd,
    a plausible output file, then exits with ``exit_code``.
    """
    binary = tmp_path / f"fake_claude_{exit_code}"
    body = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import os
        import sys
        from pathlib import Path

        cwd = Path.cwd()
        print(f"fake claude running in {{cwd}}", flush=True)
        print(f"argv={{sys.argv!r}}", flush=True)
        (cwd / "where_am_i.txt").write_text(str(cwd) + "\\n", encoding="utf-8")
        out = cwd / "output"
        out.mkdir(parents=True, exist_ok=True)
        (out / "tailored_resume.md").write_text("# tailored resume\\n", encoding="utf-8")
        (out / "change_log.md").write_text("# change log\\n", encoding="utf-8")
        {extra_body}
        sys.exit({exit_code})
        """
    )
    binary.write_text(body, encoding="utf-8")
    binary.chmod(0o755)
    return binary


def _seed_run(client, tmp_path: Path, monkeypatch) -> dict:
    """Create the supporting files and POST /runs to get a real run row."""
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


def test_invoke_run_success_transitions_status(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    assert run["status"] == "created"
    assert run["started_at"] is None
    assert run["completed_at"] is None

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "completed"
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["error_message"] is None

    run_dir = Path(body["run_dir"])
    log_path = run_dir / "run.log"
    assert log_path.is_file()
    assert log_path.stat().st_size > 0
    log_text = log_path.read_text(encoding="utf-8")
    assert "fake claude running in" in log_text

    # Output files Claude was supposed to write.
    assert (run_dir / "output" / "tailored_resume.md").is_file()


def test_invoke_run_failure_records_error(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=3)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "failed"
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["error_message"]
    assert "3" in body["error_message"]

    run_dir = Path(body["run_dir"])
    assert (run_dir / "run.log").stat().st_size > 0


def test_invoke_run_subprocess_cwd_is_run_dir(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    run_dir = Path(body["run_dir"]).resolve()
    marker = run_dir / "where_am_i.txt"
    assert marker.is_file()
    recorded = Path(marker.read_text(encoding="utf-8").strip()).resolve()
    assert recorded == run_dir
    # Make sure the subprocess did NOT run from the project root or backend dir.
    assert recorded != Path.cwd().resolve()


def test_invoke_run_missing_binary_marks_failed(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    monkeypatch.setenv(
        "JOBAPPLY_CLAUDE_BINARY", str(tmp_path / "definitely_not_a_binary")
    )

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "failed"
    assert body["error_message"]
    assert "claude binary not found" in body["error_message"]


def test_invoke_run_unknown_id_returns_404(client, tmp_path, monkeypatch):
    # Need the env to be valid enough for the route to import, though it
    # short-circuits before touching the subprocess.
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post("/runs/does-not-exist/invoke")
    assert resp.status_code == 404
    assert "claude run" in resp.json()["detail"].lower()


def test_invoke_run_dry_run_skips_subprocess(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    # Binary points at something that would fail if actually executed.
    monkeypatch.setenv(
        "JOBAPPLY_CLAUDE_BINARY", str(tmp_path / "would_explode_if_used")
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_DRY_RUN", "1")

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "completed"
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["error_message"] is None

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "dry-run" in log_text


def test_invoke_run_missing_prompt_marks_failed(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    prompt_path = Path(run["run_dir"]) / "input" / "tailoring_prompt.md"
    prompt_path.unlink()

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert "tailoring prompt not found" in body["error_message"]


def test_invoke_does_not_mutate_resume_versions(client, tmp_path, monkeypatch):
    """The worker only records run lifecycle; it must not create ResumeVersion rows."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # output_hash stays empty — that's task 008's job.
    assert body["output_hash"] is None
