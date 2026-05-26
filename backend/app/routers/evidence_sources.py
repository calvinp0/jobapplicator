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

from typing import Iterable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..evidence_source_discovery import (
    EvidenceSourceFile,
    list_filesystem_evidence_sources,
)
from ..models import EvidenceBank
from ..schemas import EvidenceSourceRead

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


@router.get("", response_model=list[EvidenceSourceRead])
def list_evidence_sources(db: Session = Depends(get_db)) -> list[EvidenceSourceRead]:
    db_rows = list(
        db.query(EvidenceBank).order_by(EvidenceBank.created_at.desc()).all()
    )
    filesystem = list_filesystem_evidence_sources()
    return _ordered(filesystem, db_rows)
