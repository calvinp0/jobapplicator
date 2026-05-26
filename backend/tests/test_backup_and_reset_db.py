"""Tests for ``scripts/backup_and_reset_db.py``.

These tests exercise the script's pure helpers and CLI surface against
a temporary SQLite database, never touching the real
``backend/jobapply.db``.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backup_and_reset_db as br  # noqa: E402  (post-sys.path import)


def _make_sqlite_with_row(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE marker (k TEXT PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO marker VALUES ('hello', 'world')")
        conn.commit()
    finally:
        conn.close()


def test_resolve_database_defaults_to_backend_path(tmp_path):
    resolved = br.resolve_database(env={}, repo_root=tmp_path)
    assert resolved.is_sqlite is True
    assert resolved.sqlite_path == (tmp_path / "backend" / "jobapply.db").resolve()


def test_resolve_database_honors_env_absolute_path(tmp_path):
    db = tmp_path / "custom.db"
    resolved = br.resolve_database(
        env={"JOBAPPLY_DATABASE_URL": f"sqlite:///{db}"},
        repo_root=tmp_path,
    )
    assert resolved.is_sqlite is True
    assert resolved.sqlite_path == db.resolve()


def test_resolve_database_reports_non_sqlite(tmp_path):
    resolved = br.resolve_database(
        env={"JOBAPPLY_DATABASE_URL": "postgresql+psycopg://u:p@h/db"},
        repo_root=tmp_path,
    )
    assert resolved.is_sqlite is False
    assert resolved.sqlite_path is None


def test_make_backup_path_uses_stem_and_timestamp(tmp_path):
    db = tmp_path / "jobapply.db"
    backup_dir = tmp_path / "backups"
    fixed = datetime(2026, 5, 26, 12, 15, 30)
    path = br.make_backup_path(db, backup_dir=backup_dir, now=fixed)
    assert path == backup_dir / "jobapply_2026-05-26_121530.db"


def test_backup_sqlite_creates_readable_copy(tmp_path):
    db = tmp_path / "jobapply.db"
    _make_sqlite_with_row(db)
    backup_path = tmp_path / "backups" / "snap.db"

    result = br.backup_sqlite(db, backup_path)
    assert result == backup_path
    assert backup_path.exists()

    conn = sqlite3.connect(str(backup_path))
    try:
        row = conn.execute("SELECT v FROM marker WHERE k='hello'").fetchone()
    finally:
        conn.close()
    assert row == ("world",)


def test_reset_sqlite_removes_db_and_sidecars(tmp_path):
    db = tmp_path / "jobapply.db"
    wal = Path(str(db) + "-wal")
    shm = Path(str(db) + "-shm")
    _make_sqlite_with_row(db)
    wal.write_text("wal")
    shm.write_text("shm")

    removed = br.reset_sqlite(db)
    assert not db.exists()
    assert not wal.exists()
    assert not shm.exists()
    assert set(removed) == {db, wal, shm}


def test_dry_run_does_not_modify_database(tmp_path, monkeypatch, capsys):
    db = tmp_path / "jobapply.db"
    _make_sqlite_with_row(db)
    monkeypatch.setenv("JOBAPPLY_DATABASE_URL", f"sqlite:///{db}")
    backup_dir = tmp_path / "backups"

    exit_code = br.main(["--dry-run", "--backup-dir", str(backup_dir)])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "Database path:" in out
    assert "Backup path:" in out
    assert "Would reset:" in out
    assert "Would preserve:" in out
    assert "candidate_context/" in out
    assert "runs/" in out

    # Nothing was written.
    assert db.exists()
    assert not backup_dir.exists()

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT v FROM marker WHERE k='hello'").fetchone()
    finally:
        conn.close()
    assert row == ("world",)


def test_reset_requires_confirmation(tmp_path, monkeypatch, capsys):
    db = tmp_path / "jobapply.db"
    _make_sqlite_with_row(db)
    monkeypatch.setenv("JOBAPPLY_DATABASE_URL", f"sqlite:///{db}")
    # Force the interactive prompt to refuse.
    monkeypatch.setattr(br, "_confirm_interactively", lambda *a, **k: False)

    exit_code = br.main(["--backup-dir", str(tmp_path / "backups")])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Aborting" in out
    # Database untouched.
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT v FROM marker WHERE k='hello'").fetchone()
    finally:
        conn.close()
    assert row == ("world",)


def test_backup_created_before_reset(tmp_path, monkeypatch, capsys):
    db = tmp_path / "jobapply.db"
    _make_sqlite_with_row(db)
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("JOBAPPLY_DATABASE_URL", f"sqlite:///{db}")
    # Stub out schema re-init so the test does not need the full backend.
    monkeypatch.setattr(br, "reinitialize_schema", lambda: None)

    exit_code = br.main(
        ["--confirm-reset", "--backup-dir", str(backup_dir)]
    )
    assert exit_code == 0

    assert not db.exists(), "reset should have deleted the active DB"
    # Exactly one backup file should now exist and be readable.
    backups = list(backup_dir.glob("jobapply_*.db"))
    assert len(backups) == 1
    conn = sqlite3.connect(str(backups[0]))
    try:
        row = conn.execute("SELECT v FROM marker WHERE k='hello'").fetchone()
    finally:
        conn.close()
    assert row == ("world",)


def test_candidate_context_and_runs_preserved_by_default(
    tmp_path, monkeypatch
):
    # Build a fake repo with the protected paths populated.
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    db = repo / "backend" / "jobapply.db"
    _make_sqlite_with_row(db)

    cc = repo / "candidate_context"
    (cc / "master_resumes").mkdir(parents=True)
    (cc / "master_resumes" / "resume.md").write_text("# resume")
    (cc / "gmail").mkdir()
    (cc / "gmail" / "token.json").write_text("{}")
    (cc / "settings").mkdir()
    (cc / "settings" / "gmail_oauth.json").write_text("{}")

    runs = repo / "runs"
    runs.mkdir()
    (runs / "demo-run-0001").mkdir()
    (runs / "demo-run-0001" / "output.txt").write_text("ok")

    monkeypatch.setattr(br, "REPO_ROOT", repo)
    monkeypatch.setattr(br, "BACKEND_ROOT", repo / "backend")
    monkeypatch.setattr(br, "DEFAULT_BACKUP_DIR", repo / "backups" / "database")
    monkeypatch.setenv("JOBAPPLY_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(br, "reinitialize_schema", lambda: None)

    exit_code = br.main(["--confirm-reset"])
    assert exit_code == 0

    assert (cc / "master_resumes" / "resume.md").exists()
    assert (cc / "gmail" / "token.json").exists()
    assert (cc / "settings" / "gmail_oauth.json").exists()
    assert (runs / "demo-run-0001" / "output.txt").exists()


def test_optional_flags_delete_only_targeted_paths(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    db = repo / "backend" / "jobapply.db"
    _make_sqlite_with_row(db)

    cc = repo / "candidate_context"
    (cc / "gmail").mkdir(parents=True)
    (cc / "gmail" / "token.json").write_text("{}")
    (cc / "settings").mkdir()
    (cc / "settings" / "gmail_oauth.json").write_text("{}")
    (cc / "master_resumes").mkdir()
    (cc / "master_resumes" / "resume.md").write_text("# resume")

    runs = repo / "runs"
    runs.mkdir()
    (runs / "x").mkdir()
    (runs / "x" / "f").write_text("y")

    monkeypatch.setattr(br, "REPO_ROOT", repo)
    monkeypatch.setattr(br, "BACKEND_ROOT", repo / "backend")
    monkeypatch.setattr(br, "DEFAULT_BACKUP_DIR", repo / "backups" / "database")
    monkeypatch.setenv("JOBAPPLY_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(br, "reinitialize_schema", lambda: None)

    exit_code = br.main(
        [
            "--confirm-reset",
            "--delete-runs",
            "--delete-gmail-token",
            "--delete-local-gmail-config",
        ]
    )
    assert exit_code == 0

    # Targeted paths gone.
    assert not (cc / "gmail" / "token.json").exists()
    assert not (cc / "settings" / "gmail_oauth.json").exists()
    assert not runs.exists()
    # Master resumes untouched.
    assert (cc / "master_resumes" / "resume.md").exists()


def test_reseed_demo_invokes_seed(tmp_path, monkeypatch):
    db = tmp_path / "jobapply.db"
    _make_sqlite_with_row(db)
    monkeypatch.setenv("JOBAPPLY_DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setattr(br, "reinitialize_schema", lambda: None)

    calls: list[int] = []

    def fake_seed() -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(br, "run_seed_demo", fake_seed)

    exit_code = br.main(
        [
            "--confirm-reset",
            "--reseed-demo",
            "--backup-dir",
            str(tmp_path / "backups"),
        ]
    )
    assert exit_code == 0
    assert calls == [1]


def test_non_sqlite_backend_is_rejected_gracefully(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(
        "JOBAPPLY_DATABASE_URL", "postgresql+psycopg://u:p@h/db"
    )
    exit_code = br.main(["--dry-run"])
    out = capsys.readouterr().out
    assert exit_code == 2
    assert "Non-SQLite" in out


def test_delete_repo_path_refuses_outside_repo(tmp_path):
    with pytest.raises(RuntimeError):
        br._delete_repo_path("../outside", repo_root=tmp_path)
