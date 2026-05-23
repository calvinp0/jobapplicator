from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationEvent, Job, ResumeVersion
from ..schemas import (
    APPLICATION_STATUS_SET,
    ApplicationCreate,
    ApplicationEventCreate,
    ApplicationEventRead,
    ApplicationRead,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


@router.post("/{application_id}/submit", response_model=ApplicationRead)
def submit_application(application_id: str, db: Session = Depends(get_db)) -> Application:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    # Idempotent: if already submitted, return the existing row without
    # creating a duplicate event or moving submitted_at.
    if app_obj.status == "submitted":
        return app_obj

    now = _utcnow()
    app_obj.status = "submitted"
    app_obj.submitted_at = now
    db.add(
        ApplicationEvent(
            application_id=app_obj.id,
            event_type="submitted",
            event_time=now,
            source="user",
        )
    )
    db.commit()
    db.refresh(app_obj)
    return app_obj


@router.post(
    "/{application_id}/events",
    response_model=ApplicationEventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_application_event(
    application_id: str,
    payload: ApplicationEventCreate,
    db: Session = Depends(get_db),
) -> ApplicationEvent:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    event = ApplicationEvent(
        application_id=app_obj.id,
        event_type=payload.event_type,
        notes=payload.notes,
        source=payload.source,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get(
    "/{application_id}/events",
    response_model=list[ApplicationEventRead],
)
def list_application_events(
    application_id: str, db: Session = Depends(get_db)
) -> list[ApplicationEvent]:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    return list(
        db.query(ApplicationEvent)
        .filter(ApplicationEvent.application_id == application_id)
        .order_by(ApplicationEvent.event_time.asc())
        .all()
    )
