from __future__ import annotations

from pathlib import Path

from .test_claude_worker import (
    ALL_OUTPUTS,
    _seed_run,
    _write_fake_binary,
)


def test_run_log_endpoint_returns_404_for_unknown_run(client):
    resp = client.get("/runs/does-not-exist/log")
    assert resp.status_code == 404


def test_run_log_endpoint_returns_empty_lines_when_log_missing(
    client, tmp_path, monkeypatch
):
    run = _seed_run(client, tmp_path, monkeypatch)
    # No invoke yet — run.log does not exist.
    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run["id"]
    assert body["lines"] == []
    assert body["truncated"] is False


def test_run_log_endpoint_returns_worker_progress_milestones(
    client, tmp_path, monkeypatch
):
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0, write_outputs=ALL_OUTPUTS)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text

    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    joined = "\n".join(body["lines"])

    # The user-visible milestones the task contract requires.
    assert "jobapply: preparing tailoring inputs" in joined
    assert "jobapply: launching Claude Code" in joined
    assert "jobapply: Claude Code process started" in joined
    assert "jobapply: Claude Code process exited with code 0" in joined
    assert "jobapply: validating output files" in joined
    assert "jobapply: output contract satisfied" in joined

    # Subprocess stdout interleaves with the milestones.
    assert any("fake claude running in" in line for line in body["lines"])


def test_run_log_endpoint_surfaces_missing_output_milestones(
    client, tmp_path, monkeypatch
):
    """A zero-exit run that fails the output contract must report the
    missing-file milestones in run.log so the UI can show why."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(
        tmp_path,
        exit_code=0,
        write_outputs=("tailored_resume.md",),
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text
    assert invoke.json()["status"] == "failed"

    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    joined = "\n".join(resp.json()["lines"])

    assert "jobapply: validating output files" in joined
    assert (
        "jobapply: missing expected output file: output/tailored_resume.docx"
        in joined
    )
    assert (
        "jobapply: missing expected output file: output/change_log.md" in joined
    )
    assert (
        "jobapply: missing expected output file: output/claim_audit.md" in joined
    )
    assert (
        "jobapply: missing expected output file: output/ats_audit.md" in joined
    )
    assert "jobapply: marking run failed" in joined


def test_run_log_endpoint_truncates_long_logs(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    # Write a long log directly; the endpoint must cap what it returns.
    log_path = Path(run["run_dir"]) / "run.log"
    log_path.write_text(
        "\n".join(f"line {i}" for i in range(1000)) + "\n",
        encoding="utf-8",
    )

    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["truncated"] is True
    assert len(body["lines"]) <= 40
    # Last line of the file is the most recent.
    assert body["lines"][-1] == "line 999"


def test_run_log_endpoint_strips_ansi_escape_codes(
    client, tmp_path, monkeypatch
):
    run = _seed_run(client, tmp_path, monkeypatch)
    log_path = Path(run["run_dir"]) / "run.log"
    log_path.write_text(
        "\x1b[31mclaude: reading job description\x1b[0m\n"
        "jobapply: validating output files\n",
        encoding="utf-8",
    )
    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "claude: reading job description" in body["lines"]
    # No raw escape bytes leak into the response.
    joined = "".join(body["lines"])
    assert "\x1b" not in joined
    assert "[31m" not in joined


def test_run_log_endpoint_skips_blank_lines(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    log_path = Path(run["run_dir"]) / "run.log"
    log_path.write_text("first\n\n\nsecond\n   \nthird\n", encoding="utf-8")

    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    assert resp.json()["lines"] == ["first", "second", "third"]


def test_dry_run_writes_worker_milestones(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    monkeypatch.setenv(
        "JOBAPPLY_CLAUDE_BINARY", str(tmp_path / "would_explode_if_used")
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_DRY_RUN", "1")

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text

    resp = client.get(f"/runs/{run['id']}/log")
    assert resp.status_code == 200, resp.text
    joined = "\n".join(resp.json()["lines"])
    assert "jobapply: preparing tailoring inputs" in joined
    assert "jobapply: output contract satisfied" in joined
