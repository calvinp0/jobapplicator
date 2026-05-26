"""Safely back up and reset the local JobApplicator development database.

Run from the repo root, with the backend venv (or any env that can import
``app.db``) active:

    python scripts/backup_and_reset_db.py --dry-run
    python scripts/backup_and_reset_db.py --confirm-reset
    python scripts/backup_and_reset_db.py --confirm-reset --reseed-demo

The script is designed to be safe by default:

* It always creates a timestamped SQLite backup under
  ``backups/database/`` before doing anything destructive.
* It refuses to reset without ``--confirm-reset`` *or* an interactive
  ``yes`` / ``RESET`` confirmation on a TTY.
* It only touches the application database; candidate context, master
  resumes, evidence banks, Gmail tokens, and ``runs/`` are preserved
  unless explicit flags are passed (and even those flags only operate
  on well-known paths inside the repo).

The dry-run path performs no filesystem mutations.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups" / "database"

# Paths the reset path must never delete by default. These are documented
# in agent_tasks/094-add-safe-database-backup-and-reset.md and in
# docs/install.md under "Reset local database safely".
PRESERVED_PATHS: tuple[str, ...] = (
    "candidate_context/",
    "candidate_context/master_resumes/",
    "candidate_context/evidence_banks/",
    "candidate_context/project_notes/",
    "candidate_context/resume_variants/",
    "candidate_context/gmail/token.json",
    "candidate_context/settings/gmail_oauth.json",
    "runs/",
)

# Optional-deletion targets. Each maps a CLI flag to the repo-relative
# path it is allowed to touch. The script will refuse to delete anything
# outside this whitelist.
OPTIONAL_DELETE_TARGETS: dict[str, str] = {
    "--delete-runs": "runs",
    "--delete-gmail-token": "candidate_context/gmail/token.json",
    "--delete-local-gmail-config": "candidate_context/settings/gmail_oauth.json",
}


@dataclass(frozen=True)
class ResolvedDb:
    """Outcome of resolving the configured database URL."""

    url: str
    is_sqlite: bool
    sqlite_path: Path | None


def resolve_database(
    *,
    env: dict[str, str] | None = None,
    repo_root: Path | None = None,
) -> ResolvedDb:
    """Resolve the active database URL the same way ``app.db`` does.

    Reads ``JOBAPPLY_DATABASE_URL`` from ``env`` (defaults to
    ``os.environ``). For ``sqlite:///...`` URLs the resolved filesystem
    path is returned; other backends are reported with
    ``is_sqlite=False`` so callers can degrade gracefully.
    """
    environ = env if env is not None else os.environ
    root = repo_root if repo_root is not None else REPO_ROOT
    backend_default = root / "backend" / "jobapply.db"
    url = environ.get("JOBAPPLY_DATABASE_URL", f"sqlite:///{backend_default}")

    if not url.startswith("sqlite"):
        return ResolvedDb(url=url, is_sqlite=False, sqlite_path=None)

    # SQLAlchemy URL conventions:
    #   sqlite:///relative.db    -> relative to CWD ("relative.db")
    #   sqlite:////abs/path.db   -> absolute path ("/abs/path.db")
    # We strip the scheme prefix and inspect what remains.
    prefix = "sqlite:///"
    rest = url[len(prefix):] if url.startswith(prefix) else ""
    if rest.startswith("/"):
        sqlite_path = Path(rest).resolve()
    else:
        sqlite_path = (root / rest).resolve() if rest else None

    return ResolvedDb(url=url, is_sqlite=True, sqlite_path=sqlite_path)


def make_backup_path(
    db_path: Path,
    *,
    backup_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    """Build a timestamped backup file path under ``backup_dir``."""
    target_dir = backup_dir if backup_dir is not None else DEFAULT_BACKUP_DIR
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    stem = db_path.stem or "jobapply"
    suffix = db_path.suffix or ".sqlite3"
    return target_dir / f"{stem}_{timestamp}{suffix}"


def backup_sqlite(db_path: Path, backup_path: Path) -> Path:
    """Copy ``db_path`` to ``backup_path`` using SQLite's online backup API.

    Falls back to :func:`shutil.copy2` when the source is not a valid
    SQLite database file but does exist (e.g. an empty file from a never
    -started backend). The destination directory is created on demand.
    """
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file does not exist: {db_path}")

    try:
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(backup_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.DatabaseError:
        # File exists but is not a sqlite database — fall back to a
        # plain copy so the user still gets a snapshot.
        shutil.copy2(db_path, backup_path)
    return backup_path


def reset_sqlite(db_path: Path) -> list[Path]:
    """Remove the SQLite database file and its WAL/SHM siblings, if any.

    Returns the list of paths actually removed so callers can report
    them. Missing files are not an error.
    """
    removed: list[Path] = []
    for candidate in (
        db_path,
        db_path.with_suffix(db_path.suffix + "-wal") if db_path.suffix else Path(str(db_path) + "-wal"),
        db_path.with_suffix(db_path.suffix + "-shm") if db_path.suffix else Path(str(db_path) + "-shm"),
        Path(str(db_path) + "-journal"),
    ):
        if candidate.exists():
            candidate.unlink()
            removed.append(candidate)
    return removed


def reinitialize_schema() -> None:
    """Re-create empty tables by calling ``app.db.init_db``.

    Importing happens lazily so the script can also be used in
    environments where the backend isn't installed (dry runs, tests).
    """
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.db import init_db  # noqa: WPS433  (deliberate local import)

    init_db()


def run_seed_demo() -> int:
    """Invoke ``scripts/seed_demo_data.seed`` and return its exit code."""
    seed_script = REPO_ROOT / "scripts" / "seed_demo_data.py"
    if not seed_script.exists():
        print(f"WARNING: seed script not found at {seed_script}; skipping reseed.")
        return 0
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from scripts.seed_demo_data import seed  # noqa: WPS433

    return seed()


def _confirm_interactively(stream_in=sys.stdin, stream_out=sys.stdout) -> bool:
    """Prompt the user for an explicit ``RESET`` confirmation on a TTY.

    Returns ``True`` only if the user types ``RESET`` (case-sensitive)
    or ``yes``. Any other input — including EOF on a non-interactive
    pipe — is treated as a refusal.
    """
    if not stream_in.isatty():
        return False
    stream_out.write(
        "This will DELETE the local application database after backing it up.\n"
        "Type 'RESET' (uppercase) or 'yes' to continue, anything else to abort: "
    )
    stream_out.flush()
    try:
        answer = stream_in.readline().strip()
    except EOFError:
        return False
    return answer in {"RESET", "yes"}


def _delete_repo_path(rel_path: str, *, repo_root: Path | None = None) -> list[Path]:
    """Delete a single whitelisted repo-relative path. Returns what was removed."""
    root = repo_root if repo_root is not None else REPO_ROOT
    target = (root / rel_path).resolve()
    repo_resolved = root.resolve()
    try:
        target.relative_to(repo_resolved)
    except ValueError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Refusing to delete path outside repo: {target}") from exc

    if not target.exists():
        return []
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return [target]


def _print_preserved(preserved: Iterable[str]) -> None:
    print("Would preserve:")
    for path in preserved:
        print(f"  {path}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Back up and reset the local JobApplicator development database. "
            "Always creates a timestamped backup before destructive work."
        )
    )
    parser.add_argument(
        "--confirm-reset",
        action="store_true",
        help="Confirm a destructive reset without an interactive prompt.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what the script would do and exit without changes.",
    )
    parser.add_argument(
        "--reseed-demo",
        action="store_true",
        help="After reset, run scripts/seed_demo_data.py to load demo data.",
    )
    parser.add_argument(
        "--delete-runs",
        action="store_true",
        help="Also delete the runs/ directory. Off by default.",
    )
    parser.add_argument(
        "--delete-gmail-token",
        action="store_true",
        help="Also delete candidate_context/gmail/token.json. Off by default.",
    )
    parser.add_argument(
        "--delete-local-gmail-config",
        action="store_true",
        help=(
            "Also delete candidate_context/settings/gmail_oauth.json. "
            "Off by default."
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Override the backup directory (default: {DEFAULT_BACKUP_DIR}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    resolved = resolve_database()
    backup_path = (
        make_backup_path(resolved.sqlite_path, backup_dir=args.backup_dir)
        if resolved.sqlite_path is not None
        else None
    )

    if not resolved.is_sqlite:
        print(f"Database URL: {resolved.url}")
        print(
            "Non-SQLite backends are not supported by this script. "
            "Use the appropriate vendor backup/restore tool (e.g. "
            "pg_dump for Postgres) and document the path in docs/install.md."
        )
        return 2

    db_path = resolved.sqlite_path
    assert db_path is not None  # for type checkers; guarded by is_sqlite

    if args.dry_run:
        print(f"Database path: {db_path}")
        print(f"Backup path:   {backup_path}")
        print(f"Would reset:   {db_path}")
        _print_preserved(PRESERVED_PATHS)
        # Report optional deletes the user has asked for.
        opt_deletes = [
            flag
            for flag, _ in OPTIONAL_DELETE_TARGETS.items()
            if getattr(args, flag.lstrip("-").replace("-", "_"))
        ]
        if opt_deletes:
            print("Would additionally delete (via flags):")
            for flag in opt_deletes:
                print(f"  {flag} -> {OPTIONAL_DELETE_TARGETS[flag]}")
        if args.reseed_demo:
            print("Would reseed demo data via scripts/seed_demo_data.py.")
        return 0

    if not args.confirm_reset and not _confirm_interactively():
        print(
            "Aborting: reset requires --confirm-reset or an interactive "
            "'RESET'/'yes' confirmation. No changes were made."
        )
        return 1

    if not db_path.exists():
        print(
            f"Database file not found at {db_path}; nothing to back up. "
            "Re-initializing an empty schema."
        )
    else:
        backup_sqlite(db_path, backup_path)
        print(f"Backup written: {backup_path}")

    removed = reset_sqlite(db_path)
    for path in removed:
        print(f"Removed: {path}")

    reinitialize_schema()
    print(f"Re-initialized empty schema at: {db_path}")

    # Optional deletes after schema reset so a failed schema init aborts
    # before we touch unrelated files.
    for flag, rel_path in OPTIONAL_DELETE_TARGETS.items():
        attr = flag.lstrip("-").replace("-", "_")
        if getattr(args, attr):
            for path in _delete_repo_path(rel_path):
                print(f"Removed (via {flag}): {path}")

    seed_status = 0
    if args.reseed_demo:
        print("Reseeding demo data...")
        seed_status = run_seed_demo()

    print()
    print("Next steps:")
    print(f"  - Restore from backup:  cp {backup_path} {db_path}")
    print("  - Start the backend:    uvicorn app.main:app --reload "
          "--host 127.0.0.1 --port 8000")
    if not args.reseed_demo:
        print("  - Seed demo data:       python scripts/seed_demo_data.py")
    return seed_status


if __name__ == "__main__":
    raise SystemExit(main())
