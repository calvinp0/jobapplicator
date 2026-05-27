from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

def _default_database_url() -> str:
    backend_dir = Path(__file__).resolve().parents[1]
    db_path = backend_dir / "jobapply.db"
    return f"sqlite:///{db_path}"


def _database_url() -> str:
    return os.environ.get("JOBAPPLY_DATABASE_URL", _default_database_url())


engine = create_engine(
    _database_url(),
    future=True,
    connect_args={"check_same_thread": False} if _database_url().startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table declared on Base.metadata for a fresh local DB.

    Importing app.models registers all model classes (including
    RevisionFeedback, added in task 044) on Base.metadata before create_all
    runs, so a fresh SQLite file initialized via this function contains the
    revision-feedback storage from ADR-008 without a manual migration step.
    """

    from . import models  # noqa: F401  (side-effect: registers tables)

    Base.metadata.create_all(bind=engine)
    ensure_runtime_columns()


def ensure_runtime_columns() -> None:
    """Add columns that post-date the initial schema to existing tables.

    ``Base.metadata.create_all`` only creates missing tables; it does not
    add missing columns to tables that already exist. The project runs on
    SQLite without alembic, so we issue idempotent ``ALTER TABLE ADD
    COLUMN`` statements here and call this helper from both ``init_db()``
    and the FastAPI app's startup path. New columns must carry a SQL-level
    default so existing rows backfill cleanly.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "claude_runs" in table_names:
        existing = {col["name"] for col in inspector.get_columns("claude_runs")}
        if "llm_provider" not in existing:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE claude_runs ADD COLUMN llm_provider "
                        "VARCHAR(32) NOT NULL DEFAULT 'claude_code'"
                    )
                )
    if "applications" in table_names:
        existing_app_cols = {col["name"] for col in inspector.get_columns("applications")}
        # Backfill for task 080. New columns are nullable so pre-existing
        # rows load without further work; see docs/contracts/gmail_integration.md.
        if "gmail_query" not in existing_app_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE applications ADD COLUMN gmail_query TEXT")
                )
        if "last_gmail_check_at" not in existing_app_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE applications "
                        "ADD COLUMN last_gmail_check_at DATETIME"
                    )
                )
        # Backfill for task 083. Stores the most recent
        # application-aware Gmail-search outcome so ``email_status``
        # derivation can emit ``no_match`` / ``email_received`` without
        # waiting for an EmailLink row to land.
        if "email_search_state" not in existing_app_cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE applications "
                        "ADD COLUMN email_search_state VARCHAR(32)"
                    )
                )
    if "job_captures" in table_names:
        existing_capture_cols = {
            col["name"] for col in inspector.get_columns("job_captures")
        }
        # Backfill for task 109 (Firefox LinkedIn capture extraction).
        # All columns are nullable so existing rows load without further
        # migration steps. ``diagnostics_json`` is plain TEXT — the router
        # serializes/deserializes the dict.
        for col_name, ddl in (
            ("page_title", "ALTER TABLE job_captures ADD COLUMN page_title TEXT"),
            ("page_text", "ALTER TABLE job_captures ADD COLUMN page_text TEXT"),
            (
                "selected_text",
                "ALTER TABLE job_captures ADD COLUMN selected_text TEXT",
            ),
            (
                "diagnostics_json",
                "ALTER TABLE job_captures ADD COLUMN diagnostics_json TEXT",
            ),
            # Task 110: canonical/source URL split. Both nullable so
            # captures from before the canonicalizer landed still load.
            (
                "source_url",
                "ALTER TABLE job_captures ADD COLUMN source_url VARCHAR(2048)",
            ),
            (
                "canonical_url",
                "ALTER TABLE job_captures ADD COLUMN canonical_url VARCHAR(2048)",
            ),
        ):
            if col_name not in existing_capture_cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
    if "jobs" in table_names:
        existing_job_cols = {col["name"] for col in inspector.get_columns("jobs")}
        # Task 110: Jobs carry the same canonical/source URL pair as the
        # capture they were promoted from so the workspace UI can show the
        # clean URL while keeping the original recoverable.
        for col_name, ddl in (
            ("source_url", "ALTER TABLE jobs ADD COLUMN source_url VARCHAR(2048)"),
            (
                "canonical_url",
                "ALTER TABLE jobs ADD COLUMN canonical_url VARCHAR(2048)",
            ),
        ):
            if col_name not in existing_job_cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
    if "email_links" in table_names:
        existing_link_cols = {
            col["name"] for col in inspector.get_columns("email_links")
        }
        # Backfill for task 093 (manual Gmail email linking). All columns
        # are nullable / boolean-with-default so pre-existing rows load
        # without further migration steps.
        for col_name, ddl in (
            ("snippet", "ALTER TABLE email_links ADD COLUMN snippet TEXT"),
            (
                "match_method",
                "ALTER TABLE email_links ADD COLUMN match_method VARCHAR(32)",
            ),
            (
                "match_score",
                "ALTER TABLE email_links ADD COLUMN match_score FLOAT",
            ),
            (
                "linked_by_user",
                "ALTER TABLE email_links ADD COLUMN linked_by_user "
                "BOOLEAN NOT NULL DEFAULT 0",
            ),
            (
                "evidence_json",
                "ALTER TABLE email_links ADD COLUMN evidence_json TEXT",
            ),
        ):
            if col_name not in existing_link_cols:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
