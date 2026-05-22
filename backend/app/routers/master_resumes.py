from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MasterResume
from ..schemas import MasterResumeCreate, MasterResumeRead

router = APIRouter(prefix="/master-resumes", tags=["master-resumes"])


@router.post("", response_model=MasterResumeRead, status_code=status.HTTP_201_CREATED)
def create_master_resume(payload: MasterResumeCreate, db: Session = Depends(get_db)) -> MasterResume:
    resume = MasterResume(**payload.model_dump())
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume


@router.get("", response_model=list[MasterResumeRead])
def list_master_resumes(db: Session = Depends(get_db)) -> list[MasterResume]:
    return list(db.query(MasterResume).order_by(MasterResume.created_at.desc()).all())


@router.get("/{resume_id}", response_model=MasterResumeRead)
def get_master_resume(resume_id: str, db: Session = Depends(get_db)) -> MasterResume:
    resume = db.get(MasterResume, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="master resume not found")
    return resume
