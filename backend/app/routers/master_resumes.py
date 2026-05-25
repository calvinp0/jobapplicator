from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..master_resume_discovery import (
    FilesystemMasterResume,
    list_filesystem_master_resumes,
    load_filesystem_master_resume_text,
    resolve_filesystem_master_resume,
)
from ..models import MasterResume
from ..schemas import MasterResumeCreate, MasterResumeRead

router = APIRouter(prefix="/master-resumes", tags=["master-resumes"])


# The seeded demo row is identified by name so its sort order (last,
# after filesystem-discovered resumes) is deterministic regardless of
# created_at jitter between seed runs.
DEMO_MASTER_RESUME_NAME = "Demo Master Resume"


def _filesystem_read(record: FilesystemMasterResume) -> MasterResumeRead:
    """Project a filesystem-discovered resume into the API read shape.

    ``content_markdown`` is intentionally left empty in the list
    response: the list view only needs metadata, and DOCX extraction is
    deferred to run-creation time so a folder with many DOCX files
    doesn't pay the python-docx import cost on every GET.
    """
    return MasterResumeRead(
        id=record.id,
        name=record.name,
        source_path=record.source_path,
        content_markdown="",
        created_at=record.updated_at,
        updated_at=record.updated_at,
        source="filesystem",
        source_format=record.source_format,
        is_demo=False,
    )


def _db_read(row: MasterResume) -> MasterResumeRead:
    return MasterResumeRead(
        id=row.id,
        name=row.name,
        source_path=row.source_path,
        content_markdown=row.content_markdown,
        created_at=row.created_at,
        updated_at=row.updated_at,
        source="database",
        source_format=None,
        is_demo=row.name == DEMO_MASTER_RESUME_NAME,
    )


def _ordered(
    filesystem: Iterable[FilesystemMasterResume],
    db_rows: Iterable[MasterResume],
) -> list[MasterResumeRead]:
    """Return filesystem entries first, then non-demo DB rows, then demo rows.

    Within each group, filesystem entries follow directory-sort order
    (alphabetical, case-insensitive) and DB rows keep created_at-desc.
    The demo seed is pushed to the tail so real files dominate the
    selector whenever they exist.
    """
    out: list[MasterResumeRead] = [_filesystem_read(r) for r in filesystem]
    non_demo: list[MasterResumeRead] = []
    demo: list[MasterResumeRead] = []
    for row in db_rows:
        projected = _db_read(row)
        (demo if projected.is_demo else non_demo).append(projected)
    out.extend(non_demo)
    out.extend(demo)
    return out


@router.post("", response_model=MasterResumeRead, status_code=status.HTTP_201_CREATED)
def create_master_resume(
    payload: MasterResumeCreate, db: Session = Depends(get_db)
) -> MasterResumeRead:
    resume = MasterResume(**payload.model_dump())
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return _db_read(resume)


@router.get("", response_model=list[MasterResumeRead])
def list_master_resumes(db: Session = Depends(get_db)) -> list[MasterResumeRead]:
    db_rows = list(
        db.query(MasterResume).order_by(MasterResume.created_at.desc()).all()
    )
    filesystem = list_filesystem_master_resumes()
    return _ordered(filesystem, db_rows)


@router.get("/{resume_id}", response_model=MasterResumeRead)
def get_master_resume(
    resume_id: str, db: Session = Depends(get_db)
) -> MasterResumeRead:
    fs_record = resolve_filesystem_master_resume(resume_id)
    if fs_record is not None:
        # For single-resume reads it's useful to surface the content so
        # callers can preview the file without a separate fetch. DOCX
        # extraction is best-effort: a malformed file still returns the
        # metadata, just with empty content.
        try:
            content = load_filesystem_master_resume_text(fs_record)
        except Exception:
            content = ""
        return MasterResumeRead(
            id=fs_record.id,
            name=fs_record.name,
            source_path=fs_record.source_path,
            content_markdown=content,
            created_at=fs_record.updated_at,
            updated_at=fs_record.updated_at,
            source="filesystem",
            source_format=fs_record.source_format,
            is_demo=False,
        )
    resume = db.get(MasterResume, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="master resume not found")
    return _db_read(resume)


def _now() -> datetime:
    return datetime.now(timezone.utc)
