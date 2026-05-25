from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .models import ClaudeRun
from .run_directory import EXPECTED_OUTPUTS


CLAUDE_BINARY_ENV = "JOBAPPLY_CLAUDE_BINARY"
CLAUDE_DRY_RUN_ENV = "JOBAPPLY_CLAUDE_DRY_RUN"
CLAUDE_EXTRA_ARGS_ENV = "JOBAPPLY_CLAUDE_EXTRA_ARGS"
CLAUDE_PERMISSION_MODE_ENV = "JOBAPPLY_CLAUDE_PERMISSION_MODE"
PROGRESS_HEARTBEAT_ENV = "JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS"

# Default permission mode for the non-interactive backend run. ``acceptEdits``
# auto-approves file writes inside the subprocess cwd (the run directory) so
# Claude can produce ``output/`` without operator approval. The write scope is
# bounded by ``cwd=<run_dir>``; Claude Code does not write outside cwd unless
# given ``--add-dir``, which the worker does not pass.
DEFAULT_PERMISSION_MODE = "acceptEdits"

RUN_LOG_FILENAME = "run.log"
PROMPT_RELPATH = Path("input") / "tailoring_prompt.md"
OUTPUT_DIRNAME = "output"
PROGRESS_DIRNAME = "progress"
PROGRESS_LOG_FILENAME = "progress.log"
PROGRESS_RELPATH = Path(PROGRESS_DIRNAME) / PROGRESS_LOG_FILENAME

# Default cap on lines returned by ``read_recent_log_lines`` and on bytes read
# from the log file. Keeps the response small for the polling UI and bounds
# memory use if a runaway Claude run produces a giant log.
DEFAULT_LOG_TAIL_LINES = 40
LOG_READ_MAX_BYTES = 256 * 1024

# Heartbeat tick interval for the worker's fallback progress writer (seconds).
# A value of 0 disables the heartbeat entirely (used by tests that don't want
# the extra thread).
DEFAULT_PROGRESS_HEARTBEAT_SECONDS = 15.0

# Cap user-facing progress lines so a runaway Claude write doesn't bloat the
# poll response. The runtime prompt asks for <=120 chars per line; this is a
# defensive hard cap on top of that.
PROGRESS_LINE_MAX_CHARS = 200

# Strip the common subset of ANSI escape codes (CSI/SGR) that Claude's stdout
# may carry. We intentionally do not parse OSC sequences — the simple regex
# below is enough to keep recent-activity lines readable in the UI.
_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def read_recent_log_lines(
    log_path: Path,
    *,
    max_lines: int = DEFAULT_LOG_TAIL_LINES,
    max_bytes: int = LOG_READ_MAX_BYTES,
) -> tuple[list[str], bool]:
    """Return the last ``max_lines`` non-empty lines from ``log_path``.

    Returns ``([], False)`` when the file does not exist. ``truncated`` is
    ``True`` when the file is larger than ``max_bytes`` (we only read the
    tail) or when more than ``max_lines`` non-empty lines exist.
    """
    if not log_path.is_file():
        return [], False
    size = log_path.stat().st_size
    truncated = size > max_bytes
    with log_path.open("rb") as f:
        if truncated:
            f.seek(size - max_bytes)
            # Drop a likely-partial first line after seeking mid-file.
            f.readline()
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    tail: deque[str] = deque(maxlen=max_lines)
    total_nonempty = 0
    for line in text.splitlines():
        cleaned = _ANSI_ESCAPE_RE.sub("", line).rstrip()
        if not cleaned:
            continue
        total_nonempty += 1
        tail.append(cleaned)
    if total_nonempty > max_lines:
        truncated = True
    return list(tail), truncated


def read_progress_lines(
    progress_path: Path,
    *,
    max_lines: int = DEFAULT_LOG_TAIL_LINES,
    max_bytes: int = LOG_READ_MAX_BYTES,
) -> tuple[list[str], bool]:
    """Return the last ``max_lines`` user-facing progress lines.

    Mirrors ``read_recent_log_lines`` but targets ``progress/progress.log``,
    which contains plain user-facing one-liners (no ``jobapply:`` prefix and
    no ANSI). Returns ``([], False)`` when the file does not yet exist so the
    polling UI can stay quiet before the first event.
    """
    if not progress_path.is_file():
        return [], False
    size = progress_path.stat().st_size
    truncated = size > max_bytes
    with progress_path.open("rb") as f:
        if truncated:
            f.seek(size - max_bytes)
            f.readline()
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lines.append(cleaned)
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    return lines, truncated


def _heartbeat_interval_seconds() -> float:
    """Return the heartbeat tick interval, or 0 to disable.

    ``0`` disables the heartbeat thread entirely (used by tests where the
    fake binary completes faster than any reasonable tick anyway).
    """
    raw = os.environ.get(PROGRESS_HEARTBEAT_ENV, "").strip()
    if not raw:
        return DEFAULT_PROGRESS_HEARTBEAT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_PROGRESS_HEARTBEAT_SECONDS
    return max(0.0, value)


def _append_progress_line(progress_path: Path, message: str) -> None:
    """Append one user-facing progress line. Best-effort: errors swallowed.

    The progress file is shared between the worker (heartbeats, dry-run) and
    Claude Code (phase events). Each writer opens-append-closes so a partial
    write never blocks the other writer for long.
    """
    text = message.replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return
    if len(text) > PROGRESS_LINE_MAX_CHARS:
        text = text[:PROGRESS_LINE_MAX_CHARS]
    try:
        with progress_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


class ClaudeWorkerError(RuntimeError):
    """Raised when the worker cannot even attempt to invoke Claude Code.

    Process-level failures (non-zero exit, missing binary) are recorded on
    the ``ClaudeRun`` row instead of raising.
    """


def default_claude_binary() -> str:
    return os.environ.get(CLAUDE_BINARY_ENV, "claude")


def is_dry_run() -> bool:
    return os.environ.get(CLAUDE_DRY_RUN_ENV, "").lower() in {"1", "true", "yes", "on"}


def _extra_args() -> list[str]:
    raw = os.environ.get(CLAUDE_EXTRA_ARGS_ENV, "").strip()
    return raw.split() if raw else []


def _permission_mode() -> str:
    raw = os.environ.get(CLAUDE_PERMISSION_MODE_ENV, "").strip()
    return raw or DEFAULT_PERMISSION_MODE


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_failure(db: Session, run: ClaudeRun, message: str) -> ClaudeRun:
    run.status = "failed"
    run.error_message = message
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def _missing_outputs(run_dir: Path) -> list[str]:
    """Return relative paths of required output files that are absent."""
    output_dir = run_dir / OUTPUT_DIRNAME
    missing: list[str] = []
    for filename in EXPECTED_OUTPUTS:
        if not (output_dir / filename).is_file():
            missing.append(f"{OUTPUT_DIRNAME}/{filename}")
    return missing


def _write_dry_run_outputs(run_dir: Path) -> None:
    """Populate ``output/`` with placeholder files so a dry-run is importable.

    Markdown placeholders are plain text; the DOCX is a minimal valid Word
    package so the open-file flow can hand it to the host application without
    a corrupt-file error.
    """
    output_dir = run_dir / OUTPUT_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tailored_resume.md").write_text(
        "# Dry-run tailored resume\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    (output_dir / "change_log.md").write_text(
        "# Change log\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    (output_dir / "claim_audit.md").write_text(
        "# Claim audit\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    _write_minimal_docx(output_dir / "tailored_resume.docx")


def _write_minimal_docx(path: Path) -> None:
    """Write a minimal Word-openable .docx (a zip with the three required parts)."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/>'
        '</Relationships>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>Dry-run placeholder tailored resume.</w:t></w:r></w:p></w:body>'
        '</w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    path.write_bytes(buf.getvalue())


def _run_heartbeat(
    progress_path: Path,
    stop_event: threading.Event,
    interval_seconds: float,
) -> None:
    """Write periodic 'still running' lines to ``progress/progress.log``.

    Runs on a background thread alongside the Claude subprocess. Stops as
    soon as the parent sets ``stop_event`` (which it does when the process
    exits). The first tick fires after ``interval_seconds`` so a fast run
    that completes inside the first interval gets no heartbeat lines at all.
    """
    start = time.monotonic()
    while not stop_event.wait(interval_seconds):
        elapsed = int(time.monotonic() - start)
        _append_progress_line(
            progress_path,
            f"Claude Code is running — {elapsed} seconds elapsed",
        )


def _append_progress(log_path: Path, message: str) -> None:
    """Append a worker-owned progress line to ``run.log``.

    These ``jobapply:`` lines interleave with the raw Claude subprocess output
    so the frontend can show meaningful progress even when Claude is silent.
    Failures to write are swallowed — progress logging must not affect run
    lifecycle.
    """
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"jobapply: {message}\n")
    except OSError:
        pass


def invoke_claude_run(
    run_id: str,
    db: Session,
    *,
    claude_binary: Optional[str] = None,
) -> ClaudeRun:
    """Invoke Claude Code synchronously for a previously created run.

    The backend records lifecycle (status, started_at, completed_at,
    error_message) on the ``ClaudeRun`` row. The subprocess only sees the
    run directory as its working directory and must not touch the DB.
    """
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise ClaudeWorkerError(f"claude run not found: {run_id}")

    run_dir = Path(run.run_dir)
    if not run_dir.is_dir():
        return _record_failure(
            db,
            run,
            f"run directory does not exist: {run_dir}",
        )

    prompt_file = run_dir / PROMPT_RELPATH
    if not prompt_file.is_file():
        return _record_failure(
            db,
            run,
            f"tailoring prompt not found: {prompt_file}",
        )

    output_dir = run_dir / OUTPUT_DIRNAME
    # Defensive: create_run_directory already mkdir's this, but ensure it
    # exists at launch time so Claude can write outputs even if the directory
    # was removed between create and invoke. The cwd=run_dir + acceptEdits
    # combination only auto-approves writes; it does not create directories.
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_dir / RUN_LOG_FILENAME
    # Truncate any prior log so progress lines start fresh per invocation.
    log_path.write_text("", encoding="utf-8")
    _append_progress(log_path, "preparing tailoring inputs")

    # Per docs/contracts/claude_run_directory.md the user-facing progress feed
    # lives at ``progress/progress.log``. The directory is (re-)created and the
    # file truncated on every invocation so the UI starts from a clean slate.
    progress_dir = run_dir / PROGRESS_DIRNAME
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / PROGRESS_LOG_FILENAME
    progress_path.write_text("", encoding="utf-8")

    run.status = "running"
    run.started_at = _now()
    run.completed_at = None
    run.error_message = None
    db.commit()

    if is_dry_run():
        _append_progress(log_path, "dry-run mode: skipping Claude subprocess")
        # Mirror the user-facing phases so the UI's progress panel still has
        # something meaningful to show during a dry-run smoke test.
        for line in (
            "Preparing tailoring inputs",
            "Writing placeholder tailored resume",
            "Validating required outputs",
        ):
            _append_progress_line(progress_path, line)
        _write_dry_run_outputs(run_dir)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"[dry-run] skipped Claude subprocess at {_now().isoformat()}\n"
                "[dry-run] wrote placeholder output files\n"
            )
        _append_progress(log_path, "validating output files")
        _append_progress(log_path, "output contract satisfied")
        run.status = "completed"
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
        return run

    binary = claude_binary or default_claude_binary()
    permission_mode = _permission_mode()
    # ``--print`` is the documented non-interactive switch: Claude reads the
    # prompt from stdin (or argv) and exits after producing output, instead of
    # opening an interactive REPL. Passing the prompt file path as a positional
    # argument made Claude treat it as a conversational starter ("what should I
    # do with this?") rather than executing the contract, so we route the
    # prompt's contents through stdin instead.
    argv = [
        binary,
        "--print",
        "--permission-mode",
        permission_mode,
        *_extra_args(),
    ]

    try:
        prompt_text = prompt_file.read_text(encoding="utf-8")
    except OSError as exc:
        _append_progress(log_path, f"failed to read prompt file: {exc}")
        _append_progress(log_path, "marking run failed")
        return _record_failure(
            db,
            run,
            f"failed to read prompt file {prompt_file}: {exc}",
        )

    _append_progress(log_path, "launching Claude Code in non-interactive mode")
    _append_progress(log_path, f"prompt file={PROMPT_RELPATH}")
    _append_progress(log_path, f"launching Claude Code with cwd={run_dir}")
    _append_progress(log_path, f"permission mode={permission_mode}")
    _append_progress(log_path, f"output directory={output_dir}")
    heartbeat_interval = _heartbeat_interval_seconds()
    heartbeat_stop = threading.Event()
    heartbeat_thread: Optional[threading.Thread] = None
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"$ {' '.join(argv)}  (cwd={run_dir})\n"
            )
            log.flush()
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=str(run_dir),
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError as exc:
                _append_progress(log_path, f"claude binary not found: {binary}")
                _append_progress(log_path, "marking run failed")
                return _record_failure(
                    db,
                    run,
                    f"claude binary not found: {binary} ({exc})",
                )
            except OSError as exc:
                _append_progress(log_path, f"failed to launch claude binary {binary}")
                _append_progress(log_path, "marking run failed")
                return _record_failure(
                    db,
                    run,
                    f"failed to launch claude binary {binary}: {exc}",
                )
            _append_progress(log_path, "Claude Code process started")
            # Feed the prompt to Claude via stdin and close it immediately so
            # Claude knows there's no more input coming. Large prompts can
            # exceed ARG_MAX if passed as argv, and stdin keeps the prompt out
            # of the process listing. A BrokenPipe means Claude exited before
            # reading the full prompt — recoverable, the wait() below records
            # the exit code.
            if process.stdin is not None:
                try:
                    process.stdin.write(prompt_text.encode("utf-8"))
                except (BrokenPipeError, OSError):
                    pass
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            if heartbeat_interval > 0:
                heartbeat_thread = threading.Thread(
                    target=_run_heartbeat,
                    args=(progress_path, heartbeat_stop, heartbeat_interval),
                    daemon=True,
                )
                heartbeat_thread.start()
            try:
                returncode = process.wait()
            finally:
                heartbeat_stop.set()
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=2.0)
    except OSError as exc:
        _append_progress(log_path, f"failed to write run log: {exc}")
        _append_progress(log_path, "marking run failed")
        return _record_failure(
            db,
            run,
            f"failed to write run log: {exc}",
        )

    _append_progress(
        log_path, f"Claude Code process exited with code {returncode}"
    )

    if returncode != 0:
        _append_progress(log_path, "marking run failed")
        run.status = "failed"
        run.error_message = (
            f"claude exited with code {returncode}; see {log_path}"
        )
    else:
        _append_progress(log_path, "validating output files")
        missing = _missing_outputs(run_dir)
        if missing:
            for path in missing:
                _append_progress(log_path, f"missing expected output file: {path}")
            _append_progress(log_path, "marking run failed")
            run.status = "failed"
            run.error_message = "expected output file missing: " + ", ".join(missing)
        else:
            _append_progress(log_path, "output contract satisfied")
            run.status = "completed"
            run.error_message = None
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run
