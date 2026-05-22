from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, Job, ResumeVersion
from ..schemas import APPLICATION_STATUS_SET, ApplicationCreate, ApplicationRead

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, db: Session = Depends(get_db)) -> Application:
    if payload.status not in APPLICATION_STATUS_SET:
        raise HTTPException(status_code=422, detail=f"invalid status: {payload.status}")
    if db.get(Job, payload.job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    if payload.resume_version_id is not None and db.get(ResumeVersion, payload.resume_version_id) is None:
        raise HTTPException(status_code=404, detail="resume version not found")

    application = Application(
        job_id=payload.job_id,
        resume_version_id=payload.resume_version_id,
        status=payload.status,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.get("", response_model=list[ApplicationRead])
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    return list(db.query(Application).order_by(Application.created_at.desc()).all())


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(application_id: str, db: Session = Depends(get_db)) -> Application:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")
    return app_obj
