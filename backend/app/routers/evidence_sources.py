"""``GET /evidence-sources`` — list selectable evidence sources for a run.

Combines DB-backed ``EvidenceBank`` rows with filesystem discoveries
from ``candidate_context/`` subfolders so the frontend's multi-select
picker can show real user files alongside the seeded demo evidence.
Sort order is documented in ``task 090``: filesystem entries first
(case-insensitive alphabetical), then non-demo DB rows, then the seeded
demo row last — so adding real files immediately hides the demo from
the top of the list without removing it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..evidence_source_discovery import (
    EvidenceSourceFile,
    default_candidate_context_root,
    list_filesystem_evidence_sources,
)
from ..file_import import (
    EVIDENCE_EXTENSIONS,
    FileImportError,
    save_imported_file,
)
from ..models import EvidenceBank
from ..schemas import EvidenceSourceRead, FileImportResult

router = APIRouter(prefix="/evidence-sources", tags=["evidence-sources"])

DEMO_EVIDENCE_BANK_NAME = "Demo Evidence Bank"


def _filesystem_read(record: EvidenceSourceFile) -> EvidenceSourceRead:
    return EvidenceSourceRead(
        id=record.id,
        name=record.name,
        source_type=record.source_type,
        source_format=record.source_format,
        source="filesystem",
        source_path=record.source_path,
        updated_at=record.updated_at,
        is_demo=False,
    )


def _db_read(row: EvidenceBank) -> EvidenceSourceRead:
    return EvidenceSourceRead(
        id=row.id,
        name=row.name,
        source_type="evidence_bank",
        source_format="md",
        source="database",
        source_path=None,
        updated_at=row.updated_at,
        is_demo=row.name == DEMO_EVIDENCE_BANK_NAME,
    )


def _ordered(
    filesystem: Iterable[EvidenceSourceFile],
    db_rows: Iterable[EvidenceBank],
) -> list[EvidenceSourceRead]:
    out: list[EvidenceSourceRead] = [_filesystem_read(r) for r in filesystem]
    non_demo: list[EvidenceSourceRead] = []
    demo: list[EvidenceSourceRead] = []
    for row in db_rows:
        projected = _db_read(row)
        (demo if projected.is_demo else non_demo).append(projected)
    out.extend(non_demo)
    out.extend(demo)
    return out


@router.post(
    "/import-file",
    response_model=FileImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def import_evidence_source_file(
    file: UploadFile = File(...),
) -> FileImportResult:
    """Import an uploaded evidence file into ``candidate_context/evidence_banks/``.

    The file is validated, sanitized, and copied into the managed evidence
    folder so the app owns a stable copy. It is then discoverable by the
    same filesystem scan that powers the evidence-source list, so it is
    immediately available to tailoring runs without a DB row.
    """
    data = await file.read()
    evidence_dir = default_candidate_context_root() / "evidence_banks"
    try:
        imported = save_imported_file(
            evidence_dir,
            file.filename or "",
            data,
            EVIDENCE_EXTENSIONS,
        )
    except FileImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = next(
        (
            r
            for r in list_filesystem_evidence_sources()
            if r.absolute_path.resolve() == imported.stored_path.resolve()
        ),
        None,
    )
    if record is None:  # pragma: no cover - defensive; the file was just written
        raise HTTPException(
            status_code=500, detail="imported file could not be resolved"
        )

    return FileImportResult(
        id=record.id,
        name=imported.name,
        source_type=record.source_type,
        source_format=imported.source_format,
        original_filename=imported.original_filename,
        stored_path=record.source_path,
        imported_at=datetime.now(timezone.utc),
    )


@router.get("", response_model=list[EvidenceSourceRead])
def list_evidence_sources(db: Session = Depends(get_db)) -> list[EvidenceSourceRead]:
    db_rows = list(
        db.query(EvidenceBank).order_by(EvidenceBank.created_at.desc()).all()
    )
    filesystem = list_filesystem_evidence_sources()
    return _ordered(filesystem, db_rows)
