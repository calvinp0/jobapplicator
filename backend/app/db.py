from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _database_url() -> str:
    return os.environ.get("JOBAPPLY_DATABASE_URL", "sqlite:///./jobapply.db")


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
