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
    if "claude_runs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("claude_runs")}
    if "llm_provider" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE claude_runs ADD COLUMN llm_provider "
                    "VARCHAR(32) NOT NULL DEFAULT 'claude_code'"
                )
            )
