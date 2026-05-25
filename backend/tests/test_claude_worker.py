from __future__ import annotations

import os
import shutil
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


ALL_OUTPUTS = (
    "tailored_resume.md",
    "tailored_resume.docx",
    "change_log.md",
    "claim_audit.md",
)


def _write_fake_binary(
    tmp_path: Path,
    *,
    exit_code: int = 0,
    write_outputs: tuple[str, ...] = ALL_OUTPUTS,
    extra_body: str = "",
) -> Path:
    """Write an executable Python script that imitates Claude Code.

    Writes a marker file (``where_am_i.txt``) recording the subprocess cwd,
    drains and records stdin to ``stdin_received.txt`` so tests can assert the
    worker piped the prompt contents in non-interactive mode, writes the
    requested subset of ``output/`` files, then exits with ``exit_code``.
    """
    binary = tmp_path / f"fake_claude_{exit_code}_{'_'.join(write_outputs) or 'none'}"
    outputs_repr = repr(list(write_outputs))
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
        try:
            stdin_blob = sys.stdin.read()
        except Exception:
            stdin_blob = ""
        (cwd / "stdin_received.txt").write_text(stdin_blob, encoding="utf-8")
        out = cwd / "output"
        out.mkdir(parents=True, exist_ok=True)
        for name in {outputs_repr}:
            (out / name).write_bytes(f"content for {{name}}\\n".encode("utf-8"))
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
        "# Prompt\n"
        "You are running inside a non-interactive backend job.\n"
        "Do not ask clarifying questions.\n"
        "Do the thing.\n",
        encoding="utf-8",
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

    # All required output files Claude was supposed to write.
    for name in ALL_OUTPUTS:
        assert (run_dir / "output" / name).is_file()


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
    # After ADR-009 the worker quotes the provider id, not the literal
    # string "claude", so a future provider-specific failure stays
    # distinguishable in logs.
    assert "binary not found" in body["error_message"]
    assert "'claude_code'" in body["error_message"]


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

    run_dir = Path(body["run_dir"])
    log_text = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "dry-run" in log_text

    # Dry-run must populate the full output contract so the run is importable.
    for name in ALL_OUTPUTS:
        assert (run_dir / "output" / name).is_file(), f"missing dry-run output: {name}"

    # The placeholder docx must be a real zip (Word package) so the open-file
    # flow can hand it to the host application without a corrupt-file error.
    import zipfile

    docx = run_dir / "output" / "tailored_resume.docx"
    assert zipfile.is_zipfile(docx)
    with zipfile.ZipFile(docx) as zf:
        names = set(zf.namelist())
    assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names


def test_invoke_run_zero_exit_with_missing_outputs_marks_failed(
    client, tmp_path, monkeypatch
):
    """Claude exit code 0 is not enough — the output contract must be satisfied."""
    run = _seed_run(client, tmp_path, monkeypatch)
    # Subprocess "succeeds" but only writes one of the four required files.
    binary = _write_fake_binary(
        tmp_path,
        exit_code=0,
        write_outputs=("tailored_resume.md",),
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "failed"
    assert body["completed_at"] is not None
    message = body["error_message"]
    assert "expected output file missing" in message
    # All three missing files must be named so the user can see what went wrong.
    for missing in (
        "output/tailored_resume.docx",
        "output/change_log.md",
        "output/claim_audit.md",
    ):
        assert missing in message, f"{missing!r} not in {message!r}"
    # The one file that was written must NOT be listed as missing.
    assert "output/tailored_resume.md" not in message


def test_invoke_run_zero_exit_with_all_outputs_marks_completed(
    client, tmp_path, monkeypatch
):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0, write_outputs=ALL_OUTPUTS)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["error_message"] is None


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


def test_invoke_run_passes_default_permission_mode(client, tmp_path, monkeypatch):
    """Worker must pass ``--permission-mode acceptEdits`` so writes auto-approve."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    monkeypatch.delenv("JOBAPPLY_CLAUDE_PERMISSION_MODE", raising=False)

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    # The fake binary echoes its argv into the log via stdout.
    assert "--permission-mode" in log_text
    assert "acceptEdits" in log_text
    # The worker must use non-interactive (--print) mode so Claude doesn't
    # open a REPL.
    assert "--print" in log_text
    # Worker-owned progress lines record the non-interactive launch context.
    assert "jobapply: launching Claude Code in non-interactive mode" in log_text
    assert "jobapply: prompt file=input/tailoring_prompt.md" in log_text
    assert "jobapply: launching Claude Code with cwd=" in log_text
    assert "jobapply: permission mode=acceptEdits" in log_text
    assert "jobapply: output directory=" in log_text


def test_invoke_run_logs_docx_skill_requested(client, tmp_path, monkeypatch):
    """Worker must log that DOCX skill usage was requested for Word output.

    Tracking task 074: the runtime prompt asks Claude Code to use the
    DOCX / Word document skill when generating tailored_resume.docx. The
    worker has no reliable cross-version way to detect skill
    installation, so it logs that usage was requested and leaves
    availability unknown.
    """
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "jobapply: DOCX skill requested for Word output generation" in log_text
    # The worker should be honest that detection is not implemented rather
    # than claiming the skill is definitely installed.
    assert "jobapply: DOCX skill availability unknown" in log_text


def test_invoke_run_pipes_prompt_contents_via_stdin(client, tmp_path, monkeypatch):
    """Worker must pipe the prompt file contents to Claude, not the file path.

    The previous (broken) invocation passed the prompt file path as a
    conversational argument, which made Claude respond with "Let me know
    which direction" instead of executing the contract. Verify the worker
    now hands Claude the prompt body via stdin, and that the body still
    carries the non-interactive instructions from the runtime prompt.
    """
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"

    run_dir = Path(body["run_dir"])
    stdin_blob = (run_dir / "stdin_received.txt").read_text(encoding="utf-8")

    # The prompt body, not just the path, must reach the subprocess.
    prompt_text = (run_dir / "input" / "tailoring_prompt.md").read_text(
        encoding="utf-8"
    )
    assert stdin_blob == prompt_text
    # And the prompt body must carry the non-interactive contract so Claude
    # cannot drift back into "what do you want me to do?" mode.
    assert "non-interactive" in stdin_blob
    assert "Do not ask clarifying questions" in stdin_blob

    # The argv must NOT include the bare prompt path positional that caused
    # the original conversational drift.
    log_text = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "'input/tailoring_prompt.md'" not in log_text


def test_invoke_run_missing_outputs_marks_failed_under_print_mode(
    client, tmp_path, monkeypatch
):
    """Non-interactive launch must still enforce the output contract.

    A fake Claude that writes nothing (mimicking a run that drifted into a
    conversational response and produced no files) must result in
    ``failed`` even though the subprocess exits cleanly.
    """
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0, write_outputs=())
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    message = body["error_message"]
    for missing in (
        "output/tailored_resume.md",
        "output/tailored_resume.docx",
        "output/change_log.md",
        "output/claim_audit.md",
    ):
        assert missing in message


def test_invoke_run_permission_mode_env_override(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    monkeypatch.setenv("JOBAPPLY_CLAUDE_PERMISSION_MODE", "plan")

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "--permission-mode plan" in log_text
    assert "jobapply: permission mode=plan" in log_text
    assert "jobapply: permission mode=acceptEdits" not in log_text


def test_invoke_run_extra_args_still_passed(client, tmp_path, monkeypatch):
    """Existing JOBAPPLY_CLAUDE_EXTRA_ARGS contract is preserved alongside permission-mode."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    monkeypatch.setenv("JOBAPPLY_CLAUDE_EXTRA_ARGS", "--verbose")

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "--permission-mode" in log_text
    assert "--verbose" in log_text


def test_invoke_run_creates_output_dir_if_missing(client, tmp_path, monkeypatch):
    """Worker must (re-)create output/ before launching so writes don't fail."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    output_dir = Path(run["run_dir"]) / "output"
    assert output_dir.is_dir()
    shutil.rmtree(output_dir)
    assert not output_dir.exists()

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed", body
    assert output_dir.is_dir()
    for name in ALL_OUTPUTS:
        assert (output_dir / name).is_file()


def _seed_run_with_provider(
    client, tmp_path, monkeypatch, provider_id: str
) -> dict:
    """Variant of ``_seed_run`` that POSTs an explicit ``llm_provider``."""
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\nbody\n", encoding="utf-8")
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
        json={
            "job_id": job["id"],
            "master_resume_id": resume["id"],
            "llm_provider": provider_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_invoke_run_dry_run_preserves_codex_provider(
    client, tmp_path, monkeypatch
):
    """Per ADR-009 the persisted provider id survives a dry-run round trip.

    Dry-run skips the subprocess so we can verify the registry plumbing
    end-to-end without depending on a fake binary: the run is created
    with ``llm_provider=codex``, the column is persisted, ``metadata.json``
    records the same value, and dry-run still marks the run completed
    (providers are not consulted in dry-run mode).
    """
    import json

    run = _seed_run_with_provider(client, tmp_path, monkeypatch, "codex")
    assert run["llm_provider"] == "codex"

    metadata = json.loads(
        (Path(run["run_dir"]) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["llm_provider"] == "codex"

    monkeypatch.setenv("JOBAPPLY_CLAUDE_DRY_RUN", "1")
    monkeypatch.setenv(
        "JOBAPPLY_CODEX_BINARY", str(tmp_path / "would_explode_if_used")
    )
    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "completed"
    assert body["llm_provider"] == "codex"
    # Re-fetch to confirm the column is read back as codex after the
    # subprocess-less dry-run completes (the value is set at create-time
    # and must not be mutated by invoke).
    fetched = client.get(f"/runs/{run['id']}").json()
    assert fetched["llm_provider"] == "codex"


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
