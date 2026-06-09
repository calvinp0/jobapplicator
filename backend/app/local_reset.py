"""In-app reset of local JobApplicator data (task 121).

``scripts/backup_and_reset_db.py`` (task 094) is the CLI tool for wiping
the local database, but it deletes the SQLite *file* and reinitializes
the schema — fine for a stopped backend, unsafe for a running one that
holds an open connection. This module is the in-app equivalent: it backs
the database up first, then clears application rows through the live
SQLAlchemy session and removes the matching generated run artifacts.

Safety guarantees mirror the CLI tool:

* A timestamped SQLite backup is always written before anything is
  deleted (when the DB is a real SQLite file).
* Only application rows are removed. Master resumes, evidence banks,
  candidate context files, and Gmail tokens are left untouched.
* On-disk cleanup is restricted to directories *inside* the configured
  runs root — a run row whose ``run_dir`` points outside the project is
  never deleted.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .db import _database_url
from .models import (
    Application,
    ApplicationEvent,
    ClaudeRun,
    EmailLink,
    Job,
    JobCapture,
    ResumeVersion,
    RevisionFeedback,
)
from .run_directory import default_runs_root


def _project_root() -> Path:
    # backend/app/local_reset.py -> backend/app -> backend -> repo root
    return Path(__file__).resolve().parents[2]


def _backups_dir() -> Path:
    """Where reset backups are written.

    Overridable via ``JOBAPPLY_BACKUPS_ROOT`` (tests point this at a temp
    dir). Defaults to ``backups/database`` at the repo root, matching the
    location used by ``scripts/backup_and_reset_db.py``.
    """
    explicit = os.environ.get("JOBAPPLY_BACKUPS_ROOT")
    if explicit:
        return Path(explicit)
    return _project_root() / "backups" / "database"


def _sqlite_path_from_url(url: str) -> Optional[Path]:
    """Resolve a ``sqlite:///`` URL to a filesystem path, or ``None``."""
    if not url.startswith("sqlite"):
        return None
    prefix = "sqlite:///"
    rest = url[len(prefix):] if url.startswith(prefix) else ""
    if not rest:
        return None
    if rest.startswith("/"):
        return Path(rest)
    return _project_root() / rest


def create_backup(now: Optional[datetime] = None) -> Optional[str]:
    """Back up the active SQLite database before a destructive reset.

    Returns a project-relative backup path on success, or ``None`` when
    the database is not a SQLite file or does not exist yet (nothing to
    back up). Uses SQLite's online backup API so it is safe to call while
    the backend holds an open connection.
    """
    db_path = _sqlite_path_from_url(_database_url())
    if db_path is None or not db_path.exists():
        return None

    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d_%H%M%S")
    backups_dir = _backups_dir()
    backups_dir.mkdir(parents=True, exist_ok=True)
    suffix = db_path.suffix or ".db"
    dest = backups_dir / f"reset-{timestamp}-{db_path.stem}{suffix}"

    try:
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.DatabaseError:
        # File exists but isn't a valid SQLite db — still snapshot it.
        shutil.copy2(db_path, dest)

    try:
        return str(dest.resolve().relative_to(_project_root().resolve()))
    except ValueError:
        return str(dest)


# Tables cleared by a reset, in a FK-safe order (children before parents).
# Master resumes and evidence banks are intentionally absent: imported
# source material survives a reset.
_RESET_MODELS: tuple[tuple[str, type], ...] = (
    ("application_events", ApplicationEvent),
    ("email_links", EmailLink),
    ("revision_feedbacks", RevisionFeedback),
    ("applications", Application),
    ("resume_versions", ResumeVersion),
    ("claude_runs", ClaudeRun),
    ("jobs", Job),
    ("job_captures", JobCapture),
)


def _clean_run_dirs(run_dirs: list[str]) -> None:
    """Remove generated run directories that live inside the runs root.

    A ``run_dir`` resolving outside the configured runs root is skipped,
    so a reset can never delete arbitrary external files.
    """
    runs_root = default_runs_root().resolve()
    for raw in run_dirs:
        if not raw:
            continue
        target = Path(raw).resolve()
        try:
            target.relative_to(runs_root)
        except ValueError:
            continue  # outside the runs root — never touch it
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)


def reset_local_data(db: Session) -> dict[str, int]:
    """Delete local application rows and generated run artifacts.

    Returns a summary of how many rows were deleted per logical category.
    """
    # Capture run directories before the rows disappear so we can clean
    # the matching artifacts on disk afterwards.
    run_dirs = [run.run_dir for run in db.query(ClaudeRun).all()]

    counts: dict[str, int] = {}
    for key, model in _RESET_MODELS:
        counts[key] = db.query(model).count()
        db.query(model).delete(synchronize_session=False)
    db.commit()

    _clean_run_dirs(run_dirs)

    return {
        "applications": counts["applications"],
        "jobs": counts["jobs"],
        "runs": counts["claude_runs"],
        "captures": counts["job_captures"],
        "resume_versions": counts["resume_versions"],
    }
