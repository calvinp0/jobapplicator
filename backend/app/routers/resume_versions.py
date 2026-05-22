from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ResumeVersion
from ..run_import import RunImportError, approve_resume_version
from ..schemas import ResumeVersionRead

router = APIRouter(prefix="/resume-versions", tags=["resume-versions"])


@router.get("", response_model=list[ResumeVersionRead])
def list_resume_versions(db: Session = Depends(get_db)) -> list[ResumeVersion]:
    return list(
        db.query(ResumeVersion).order_by(ResumeVersion.created_at.desc()).all()
    )


@router.get("/{version_id}", response_model=ResumeVersionRead)
def get_resume_version(version_id: str, db: Session = Depends(get_db)) -> ResumeVersion:
    version = db.get(ResumeVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="resume version not found")
    return version


@router.post("/{version_id}/approve", response_model=ResumeVersionRead)
def approve_version(version_id: str, db: Session = Depends(get_db)) -> ResumeVersion:
    try:
        return approve_resume_version(version_id, db)
    except RunImportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
