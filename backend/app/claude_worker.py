from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .models import ClaudeRun


CLAUDE_BINARY_ENV = "JOBAPPLY_CLAUDE_BINARY"
CLAUDE_DRY_RUN_ENV = "JOBAPPLY_CLAUDE_DRY_RUN"
CLAUDE_EXTRA_ARGS_ENV = "JOBAPPLY_CLAUDE_EXTRA_ARGS"

RUN_LOG_FILENAME = "run.log"
PROMPT_RELPATH = Path("input") / "tailoring_prompt.md"


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_failure(db: Session, run: ClaudeRun, message: str) -> ClaudeRun:
    run.status = "failed"
    run.error_message = message
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


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

    log_path = run_dir / RUN_LOG_FILENAME

    run.status = "running"
    run.started_at = _now()
    run.completed_at = None
    run.error_message = None
    db.commit()

    if is_dry_run():
        log_path.write_text(
            f"[dry-run] skipped Claude subprocess at {_now().isoformat()}\n",
            encoding="utf-8",
        )
        run.status = "completed"
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
        return run

    binary = claude_binary or default_claude_binary()
    argv = [binary, str(PROMPT_RELPATH), *_extra_args()]

    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(
                f"$ {' '.join(argv)}  (cwd={run_dir})\n"
            )
            log.flush()
            result = subprocess.run(
                argv,
                cwd=str(run_dir),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except FileNotFoundError as exc:
        return _record_failure(
            db,
            run,
            f"claude binary not found: {binary} ({exc})",
        )
    except OSError as exc:
        return _record_failure(
            db,
            run,
            f"failed to launch claude binary {binary}: {exc}",
        )

    if result.returncode == 0:
        run.status = "completed"
        run.error_message = None
    else:
        run.status = "failed"
        run.error_message = (
            f"claude exited with code {result.returncode}; see {log_path}"
        )
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run
