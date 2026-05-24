from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from .test_claude_worker import (
    ALL_OUTPUTS,
    _seed_run,
    _write_fake_binary,
)


def _write_progress_writer_binary(
    tmp_path: Path,
    *,
    exit_code: int = 0,
    progress_lines: tuple[str, ...] = (),
    write_outputs: tuple[str, ...] = ALL_OUTPUTS,
) -> Path:
    """A fake Claude binary that also appends to ``progress/progress.log``.

    Mirrors ``_write_fake_binary`` but additionally exercises the progress
    contract: the binary appends each line in ``progress_lines`` to the
    progress file the worker created before launching.
    """
    binary = tmp_path / f"fake_claude_progress_{exit_code}"
    outputs_repr = repr(list(write_outputs))
    progress_repr = repr(list(progress_lines))
    body = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import os
        import sys
        from pathlib import Path

        cwd = Path.cwd()
        print(f"fake claude running in {{cwd}}", flush=True)
        out = cwd / "output"
        out.mkdir(parents=True, exist_ok=True)
        for name in {outputs_repr}:
            (out / name).write_bytes(f"content for {{name}}\\n".encode("utf-8"))
        progress = cwd / "progress" / "progress.log"
        progress.parent.mkdir(parents=True, exist_ok=True)
        with progress.open("a", encoding="utf-8") as f:
            for line in {progress_repr}:
                f.write(line + "\\n")
                f.flush()
        sys.exit({exit_code})
        """
    )
    binary.write_text(body, encoding="utf-8")
    binary.chmod(0o755)
    return binary


def test_progress_endpoint_returns_404_for_unknown_run(client):
    resp = client.get("/runs/does-not-exist/progress")
    assert resp.status_code == 404


def test_progress_endpoint_returns_empty_lines_when_file_missing(
    client, tmp_path, monkeypatch
):
    """Before the worker runs, ``progress/progress.log`` does not exist yet.
    The endpoint should return an empty list rather than 404 so the UI can
    keep its waiting state quietly."""
    run = _seed_run(client, tmp_path, monkeypatch)

    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run["id"]
    assert body["lines"] == []
    assert body["truncated"] is False


def test_progress_endpoint_returns_user_facing_phase_events(
    client, tmp_path, monkeypatch
):
    """A successful run whose fake Claude writes progress events should be
    able to read them back from the endpoint as plain user-facing lines."""
    run = _seed_run(client, tmp_path, monkeypatch)
    phases = (
        "Reading job description",
        "Reviewing master resume",
        "Drafting tailored resume markdown",
        "Validating required outputs",
    )
    binary = _write_progress_writer_binary(
        tmp_path,
        exit_code=0,
        progress_lines=phases,
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    # Disable the heartbeat so it doesn't interleave fake-elapsed lines into
    # the assertion below.
    monkeypatch.setenv("JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS", "0")

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text
    assert invoke.json()["status"] == "completed"

    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lines"] == list(phases)
    assert body["truncated"] is False
    # No worker `jobapply:` prefix on the user-facing feed.
    assert all("jobapply:" not in line for line in body["lines"])


def test_progress_endpoint_truncates_long_files(
    client, tmp_path, monkeypatch
):
    run = _seed_run(client, tmp_path, monkeypatch)
    progress_path = Path(run["run_dir"]) / "progress" / "progress.log"
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        "\n".join(f"phase {i}" for i in range(1000)) + "\n",
        encoding="utf-8",
    )

    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["truncated"] is True
    assert len(body["lines"]) <= 40
    # Most recent line is the file's tail.
    assert body["lines"][-1] == "phase 999"


def test_progress_endpoint_skips_blank_lines(client, tmp_path, monkeypatch):
    run = _seed_run(client, tmp_path, monkeypatch)
    progress_path = Path(run["run_dir"]) / "progress" / "progress.log"
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        "Reading job description\n\n\nDrafting tailored resume markdown\n   \n",
        encoding="utf-8",
    )
    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    assert resp.json()["lines"] == [
        "Reading job description",
        "Drafting tailored resume markdown",
    ]


def test_worker_truncates_progress_file_on_each_invocation(
    client, tmp_path, monkeypatch
):
    """A second invocation must not return progress lines from the first.
    The worker truncates ``progress/progress.log`` at the start of every run
    so stale phases from a prior failure don't bleed into the new run's UI."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_progress_writer_binary(
        tmp_path,
        exit_code=0,
        progress_lines=("Reading job description",),
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    monkeypatch.setenv("JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS", "0")

    first = client.post(f"/runs/{run['id']}/invoke")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "completed"

    resp1 = client.get(f"/runs/{run['id']}/progress")
    assert resp1.json()["lines"] == ["Reading job description"]

    # Second invocation writes a different phase. The progress file must be
    # truncated so we never see the first run's line again.
    binary2 = _write_progress_writer_binary(
        tmp_path,
        exit_code=0,
        progress_lines=("Drafting tailored resume markdown",),
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary2))

    second = client.post(f"/runs/{run['id']}/invoke")
    assert second.status_code == 200, second.text
    resp2 = client.get(f"/runs/{run['id']}/progress")
    assert resp2.json()["lines"] == ["Drafting tailored resume markdown"]


def test_worker_heartbeat_emits_lines_when_claude_is_silent(
    client, tmp_path, monkeypatch
):
    """When Claude emits no progress events, the worker's heartbeat thread
    should still appear in ``progress/progress.log`` so the UI never feels
    frozen for the user."""
    run = _seed_run(client, tmp_path, monkeypatch)
    # A fake binary that sleeps long enough for at least one heartbeat tick
    # at the very short interval we configure below, then writes outputs
    # and exits cleanly.
    binary = tmp_path / "slow_fake_claude"
    binary.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os
            import sys
            import time
            from pathlib import Path

            time.sleep(0.6)
            cwd = Path.cwd()
            out = cwd / "output"
            out.mkdir(parents=True, exist_ok=True)
            for name in {list(ALL_OUTPUTS)!r}:
                (out / name).write_bytes(f"content for {{name}}\\n".encode("utf-8"))
            sys.exit(0)
            """
        ),
        encoding="utf-8",
    )
    binary.chmod(0o755)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    # Tick every 100ms; the binary above sleeps ~600ms, so we expect at
    # least one heartbeat line.
    monkeypatch.setenv("JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS", "0.1")

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text
    assert invoke.json()["status"] == "completed"

    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    lines = resp.json()["lines"]
    assert any(
        "Claude Code is running" in line and "seconds elapsed" in line
        for line in lines
    ), lines


def test_worker_heartbeat_disabled_with_zero_interval(
    client, tmp_path, monkeypatch
):
    """An explicit ``0`` for the heartbeat env disables the thread; a fast
    fake binary should produce an empty progress file."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))
    monkeypatch.setenv("JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS", "0")

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text

    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    assert resp.json()["lines"] == []


def test_dry_run_writes_user_facing_progress_lines(
    client, tmp_path, monkeypatch
):
    """A dry-run never invokes Claude, but the UI still needs something to
    show. The worker writes a small placeholder set of user-facing phases
    so the progress panel is non-empty even in dry-run mode."""
    run = _seed_run(client, tmp_path, monkeypatch)
    monkeypatch.setenv(
        "JOBAPPLY_CLAUDE_BINARY", str(tmp_path / "would_explode_if_used")
    )
    monkeypatch.setenv("JOBAPPLY_CLAUDE_DRY_RUN", "1")
    monkeypatch.setenv("JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS", "0")

    invoke = client.post(f"/runs/{run['id']}/invoke")
    assert invoke.status_code == 200, invoke.text
    assert invoke.json()["status"] == "completed"

    resp = client.get(f"/runs/{run['id']}/progress")
    assert resp.status_code == 200, resp.text
    lines = resp.json()["lines"]
    assert any("Preparing" in line for line in lines), lines
    assert any("Validating" in line for line in lines), lines
