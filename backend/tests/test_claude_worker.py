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


def test_invoke_run_logs_word_docx_tooling_requested(client, tmp_path, monkeypatch):
    """Worker must log that Word/DOCX tooling was requested for DOCX output.

    Tracking task 075: the runtime prompt asks Claude Code to prefer the
    Office Word MCP server (``word-document-server``), then the DOCX /
    Word document skill, then fall back to existing generation. The
    worker has no reliable cross-version way to detect MCP or skill
    installation, so it logs that each was requested and leaves
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
    assert "jobapply: Word/DOCX tooling requested for DOCX generation" in log_text
    assert "jobapply: Office Word MCP server requested if available" in log_text
    assert "jobapply: DOCX skill requested if available" in log_text
    # The worker should be honest that detection is not implemented rather
    # than claiming either capability is definitely installed.
    assert "jobapply: Office Word MCP availability unknown" in log_text
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


def _write_master_resume_docx(input_dir: Path) -> Path:
    """Create a small but valid master_resume.docx under ``input_dir``.

    Generated inline via python-docx so tests do not depend on a
    committed binary fixture.
    """
    from docx import Document

    doc = Document()
    doc.add_paragraph("Jane Doe", style="Title")
    doc.add_paragraph("Experience", style="Heading 1")
    doc.add_paragraph("Acme Corp — Staff Engineer", style="Heading 2")
    doc.add_paragraph("Built distributed systems.", style="List Bullet")
    path = input_dir / "master_resume.docx"
    doc.save(str(path))
    return path


def test_invoke_run_detects_and_extracts_master_resume_docx(
    client, tmp_path, monkeypatch
):
    """When a source DOCX is staged in input/, the worker must extract it
    before launching Claude and emit the documented run-log lines."""
    run = _seed_run(client, tmp_path, monkeypatch)
    input_dir = Path(run["run_dir"]) / "input"
    _write_master_resume_docx(input_dir)

    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"

    extracted = input_dir / "master_resume_extracted.md"
    assert extracted.is_file()
    extracted_text = extracted.read_text(encoding="utf-8")
    # Filename of the source DOCX must be recorded in the extracted markdown.
    assert "Source DOCX: input/master_resume.docx" in extracted_text
    assert "Jane Doe" in extracted_text

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "jobapply: checking for master resume DOCX" in log_text
    assert (
        "jobapply: found source resume DOCX=input/master_resume.docx"
        in log_text
    )
    assert (
        "jobapply: extracted source resume DOCX to "
        "input/master_resume_extracted.md"
    ) in log_text


def test_invoke_run_markdown_only_resume_still_runs(
    client, tmp_path, monkeypatch
):
    """Existing markdown-only flow must keep working — no DOCX, no
    extracted markdown, but the worker still completes the four-output
    contract and logs that it checked for a DOCX."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    input_dir = Path(run["run_dir"]) / "input"
    assert not (input_dir / "master_resume.docx").exists()

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"

    # No DOCX, so no extracted file should be created.
    assert not (input_dir / "master_resume_extracted.md").exists()
    assert not (input_dir / "master_resume_extraction_error.md").exists()

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "jobapply: checking for master resume DOCX" in log_text
    # The "found" line must NOT appear when no DOCX is present.
    assert "jobapply: found source resume DOCX" not in log_text

    # Output contract still satisfied.
    for name in ALL_OUTPUTS:
        assert (Path(body["run_dir"]) / "output" / name).is_file()


def test_invoke_run_extraction_failure_logs_and_continues_with_markdown(
    client, tmp_path, monkeypatch
):
    """A DOCX that python-docx cannot open must produce an error file and
    a failure log line — but with a markdown resume present, the run
    proceeds and Claude still runs against the markdown evidence."""
    run = _seed_run(client, tmp_path, monkeypatch)
    input_dir = Path(run["run_dir"]) / "input"
    # Stage an invalid DOCX (master_resume.md already exists from _seed_run).
    (input_dir / "master_resume.docx").write_bytes(b"not a real docx")

    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # markdown fallback exists, so the run still completes.
    assert body["status"] == "completed", body

    error_file = input_dir / "master_resume_extraction_error.md"
    assert error_file.is_file()
    assert "Source DOCX: input/master_resume.docx" in error_file.read_text(
        encoding="utf-8"
    )

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "jobapply: failed to extract source resume DOCX" in log_text


def test_invoke_run_extraction_failure_without_markdown_marks_failed(
    client, tmp_path, monkeypatch
):
    """If extraction fails and no markdown resume is on disk, the run
    must fail loudly — the worker has no usable evidence source for
    tailoring and must not silently launch Claude."""
    run = _seed_run(client, tmp_path, monkeypatch)
    input_dir = Path(run["run_dir"]) / "input"

    # Remove the auto-written master_resume.md so the only resume input is
    # the broken DOCX. Also clear the other accepted markdown names just
    # in case (none should be present in a default _seed_run).
    for name in (
        "master_resume.md",
        "resume.md",
        "base_resume.md",
        "original_resume.md",
    ):
        path = input_dir / name
        if path.exists():
            path.unlink()
    (input_dir / "master_resume.docx").write_bytes(b"not a real docx")

    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert "failed to extract source resume DOCX" in body["error_message"]
    assert "no markdown resume present" in body["error_message"]

    log_text = (Path(body["run_dir"]) / "run.log").read_text(encoding="utf-8")
    assert "jobapply: failed to extract source resume DOCX" in log_text


def test_runtime_prompt_references_extracted_markdown_and_mcp():
    """The shipped runtime prompt must reference the extracted markdown
    file the backend writes, and tell Claude to prefer the
    word-document-server MCP for DOCX work."""
    from pathlib import Path

    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "runtime_prompts"
        / "resume_tailoring.md"
    )
    text = prompt_path.read_text(encoding="utf-8")

    assert "input/master_resume_extracted.md" in text
    assert "word-document-server" in text
    # The non-interactive contract must still be present so a future
    # edit does not let the prompt drift back into asking questions.
    assert "Do not ask clarifying questions" in text
    assert "Do not wait for user input" in text
    # The prompt must distinguish DOCX (formatting) from extracted
    # markdown (evidence) so Claude treats them as complementary.
    assert "formatting" in text.lower()
    assert "evidence" in text.lower()


# ---------------------------------------------------------------------------
# Task 079: hardened Word MCP Python env + non-interactive Claude contract
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _word_mcp_doc_text() -> str:
    return (_repo_root() / "docs" / "office_word_mcp_setup.md").read_text(
        encoding="utf-8"
    )


def _install_doc_text() -> str:
    return (_repo_root() / "docs" / "install.md").read_text(encoding="utf-8")


def _runtime_prompt_text() -> str:
    return (
        _repo_root() / "runtime_prompts" / "resume_tailoring.md"
    ).read_text(encoding="utf-8")


def test_word_mcp_docs_recommend_explicit_virtualenv_python():
    """Both docs must walk the reader through Option A (virtualenv) and
    point Claude Code at the in-repo ``.venv`` interpreter rather than a
    PATH-derived ``python``."""
    for text in (_word_mcp_doc_text(), _install_doc_text()):
        lower = text.lower()
        assert "virtualenv" in lower or "venv" in lower
        assert "option a" in lower
        # The virtualenv Python path must appear with its OS-specific
        # interpreter name so a copy/paste user lands on the right
        # binary on either Linux/macOS or Windows.
        assert ".venv/bin/python" in text
        assert r".venv\Scripts\python.exe" in text


def test_word_mcp_docs_recommend_explicit_conda_python():
    """Option B (conda) must appear in both docs and resolve the
    interpreter via ``sys.executable`` so the registered path is the
    real env Python, not whatever ``python`` resolves to next shell."""
    for text in (_word_mcp_doc_text(), _install_doc_text()):
        lower = text.lower()
        assert "option b" in lower
        assert "conda create" in text
        assert "word-mcp" in text
        assert "sys.executable" in text


def test_word_mcp_docs_warn_against_system_python():
    """Docs must explicitly tell the reader not to register the MCP
    with bare ``python`` / ``python3`` on PATH."""
    for text in (_word_mcp_doc_text(), _install_doc_text()):
        # The warning must list both bare interpreter names so neither
        # is implied to be safe.
        lower = text.lower()
        assert "do not rely on" in lower
        # Both names must appear inside the file (covered by the conda
        # / venv setup blocks plus the warning).
        assert "python3" in text
        assert "PATH" in text


def test_word_mcp_docs_avoid_hardcoded_user_paths():
    """No primary command may bake in a developer-specific home path.

    The docs may *describe* such paths in prose (e.g. "paths look like
    /home/<user>/..."), but real shell snippets must use portable
    placeholders or shell variables.
    """
    for path_str, text in (
        ("docs/office_word_mcp_setup.md", _word_mcp_doc_text()),
        ("docs/install.md", _install_doc_text()),
    ):
        # Literal "/home/calvin" / "C:\Users\Calvin" must never appear —
        # those are the most likely hardcoded leak from a local install.
        assert "/home/calvin" not in text, (
            f"{path_str} contains a hardcoded /home/calvin path"
        )
        assert "C:\\Users\\Calvin" not in text, (
            f"{path_str} contains a hardcoded C:\\Users\\Calvin path"
        )
        # Portable variables must be present.
        assert "$WORD_MCP_DIR" in text
        assert "$WORD_MCP_PYTHON" in text
        assert "$WORD_MCP_SERVER" in text


def test_word_mcp_docs_include_linux_macos_verification_commands():
    """Linux/macOS setup must include ``test -x``/``test -f`` checks so
    the reader can confirm the venv Python and server entrypoint are
    actually on disk before registering the MCP."""
    for text in (_word_mcp_doc_text(), _install_doc_text()):
        assert 'test -x "$WORD_MCP_PYTHON"' in text
        assert 'test -f "$WORD_MCP_SERVER"' in text
        # The echo lines surfacing the resolved paths must be present so
        # the user can sanity-check before copying into ``claude mcp add``.
        assert 'echo "$WORD_MCP_PYTHON"' in text
        assert 'echo "$WORD_MCP_SERVER"' in text


def test_word_mcp_docs_include_windows_powershell_verification_commands():
    """Windows PowerShell setup must include ``Test-Path`` checks and
    the matching ``Write-Host`` lines for the same sanity-check pass."""
    for text in (_word_mcp_doc_text(), _install_doc_text()):
        assert "Test-Path $WORD_MCP_PYTHON" in text
        assert "Test-Path $WORD_MCP_SERVER" in text
        assert "Write-Host $WORD_MCP_PYTHON" in text
        assert "Write-Host $WORD_MCP_SERVER" in text


def test_word_mcp_docs_include_claude_mcp_registration_with_placeholders():
    """The ``claude mcp add`` snippet must use the resolved variables so
    a copy/paste reader does not have to guess interpreter paths."""
    for text in (_word_mcp_doc_text(), _install_doc_text()):
        assert "claude mcp add word-document-server" in text
        # The registration block must reference both the explicit
        # interpreter and server-script variables, not bare ``python``.
        assert '"$WORD_MCP_PYTHON"' in text
        assert '"$WORD_MCP_SERVER"' in text
        # Help reference for version-specific flag drift.
        assert "claude mcp add --help" in text


def test_runtime_prompt_blocks_permission_and_clarifying_questions():
    """The runtime prompt must explicitly refuse every shape of
    permission/clarifying prompt a backend run could hang on."""
    text = _runtime_prompt_text()
    for phrase in (
        "non-interactive",
        "Do not ask clarifying questions",
        "Do not wait for user input",
        "Do not ask the user whether to apply changes",
        "Do not ask for permission to edit the resume",
    ):
        assert phrase in text, f"missing phrase: {phrase!r}"


def test_runtime_prompt_grants_run_directory_edit_permission():
    """The prompt must tell Claude the task contract already grants
    permission to create/edit files inside the run directory, so it
    does not stop to ask."""
    text = _runtime_prompt_text()
    assert (
        "task contract already grants permission to create and edit "
        "files inside this run directory"
    ) in text


def test_runtime_prompt_restricts_writes_to_run_directory():
    """The prompt must scope writes to the run directory only — the
    worker enforces this via ``cwd``, but the prompt must reinforce it
    so Claude doesn't drift into project-level edits."""
    text = _runtime_prompt_text()
    assert "Only write inside this run directory" in text
