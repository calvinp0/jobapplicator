from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Job, JobCapture
from ..schemas import (
    JobCaptureCreate,
    JobCaptureCreateResponse,
    JobCaptureRead,
    JobRead,
)

router = APIRouter(prefix="/captures", tags=["captures"])


# Fields required for a capture to skip manual review and auto-confirm into a
# Job. Location is intentionally excluded — remote roles legitimately omit it.
_AUTO_CONFIRM_REQUIRED_FIELDS = ("title", "company", "external_url", "description_text")


def _is_complete(capture: JobCapture) -> bool:
    for field_name in _AUTO_CONFIRM_REQUIRED_FIELDS:
        value = getattr(capture, field_name, None)
        if value is None or not str(value).strip():
            return False
    return True


def _find_job_by_url(db: Session, external_url: Optional[str]) -> Optional[Job]:
    if not external_url:
        return None
    return db.query(Job).filter(Job.external_url == external_url).first()


def _job_from_capture(capture: JobCapture) -> Job:
    assert capture.company is not None and capture.title is not None
    return Job(
        source_platform=capture.source_platform,
        external_url=capture.external_url,
        external_job_id=capture.external_job_id,
        company=capture.company.strip(),
        title=capture.title.strip(),
        location=capture.location.strip() if capture.location else None,
        description_text=capture.description_text.strip(),
        application_method=(
            capture.application_method.strip()
            if capture.application_method
            else None
        ),
        created_from_capture_id=capture.id,
    )


@router.post(
    "",
    response_model=JobCaptureCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_capture(
    payload: JobCaptureCreate, db: Session = Depends(get_db)
) -> JobCaptureCreateResponse:
    diagnostics_json = (
        json.dumps(payload.diagnostics, ensure_ascii=False)
        if payload.diagnostics is not None
        else None
    )

    capture = JobCapture(
        source_platform=payload.source_platform,
        capture_method=payload.capture_method,
        external_url=payload.external_url,
        external_job_id=payload.external_job_id,
        company=payload.company,
        title=payload.title,
        location=payload.location,
        description_text=payload.description_text or "",
        application_method=payload.application_method,
        raw_text=payload.raw_text,
        page_title=payload.page_title,
        page_text=payload.page_text,
        selected_text=payload.selected_text,
        diagnostics_json=diagnostics_json,
        captured_at=payload.captured_at or datetime.now(timezone.utc),
        user_confirmed=False,
    )
    db.add(capture)
    db.flush()

    auto_confirmed = False
    job_reused = False
    job_id: Optional[str] = None

    if _is_complete(capture):
        existing = _find_job_by_url(db, capture.external_url)
        if existing is not None:
            # Same URL captured before — reuse the existing Job rather than
            # producing a duplicate. We intentionally do not rewrite the
            # original Job.created_from_capture_id; the FK stays pointed at
            # whichever capture first promoted the URL.
            capture.user_confirmed = True
            job_id = existing.id
            job_reused = True
        else:
            job = _job_from_capture(capture)
            db.add(job)
            db.flush()
            capture.user_confirmed = True
            job_id = job.id
        auto_confirmed = True

    db.commit()
    db.refresh(capture)

    return JobCaptureCreateResponse.model_validate(
        {
            **JobCaptureRead.model_validate(capture).model_dump(),
            "job_id": job_id if job_id is not None else capture.job_id,
            "auto_confirmed": auto_confirmed,
            "job_reused": job_reused,
        }
    )


@router.get("", response_model=list[JobCaptureRead])
def list_captures(db: Session = Depends(get_db)) -> list[JobCapture]:
    return list(db.query(JobCapture).order_by(JobCapture.created_at.desc()).all())


@router.get("/{capture_id}", response_model=JobCaptureRead)
def get_capture(capture_id: str, db: Session = Depends(get_db)) -> JobCapture:
    capture = db.get(JobCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="capture not found")
    return capture


@router.post("/{capture_id}/confirm", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def confirm_capture(capture_id: str, db: Session = Depends(get_db)) -> Job:
    """Promote a JobCapture into a confirmed Job.

    Task 002 §"Capture Confirmation Behavior":
      1. Load the capture.
      2. Validate that company, title, description_text are present.
      3. Create a Job from the capture.
      4. Mark the capture as user_confirmed = True.
      5. Return the created job.

    Re-confirm behavior: if the capture is already confirmed, return the
    existing Job linked via created_from_capture_id (idempotent). If the
    invariant is broken (confirmed but no linked Job), 409.
    """
    capture = db.get(JobCapture, capture_id)
    if capture is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Capture not found"},
        )

    if capture.user_confirmed:
        existing_job = (
            db.query(Job)
            .filter(Job.created_from_capture_id == capture.id)
            .first()
        )
        if existing_job is None:
            # Fall back to URL-based lookup for captures that were
            # auto-confirmed against a pre-existing Job (dedup case) and
            # therefore have no created_from_capture_id pointing at them.
            existing_job = _find_job_by_url(db, capture.external_url)
        if existing_job is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Capture is marked confirmed but no linked job exists",
                    "capture_id": str(capture.id),
                },
            )
        return existing_job

    required_fields = {
        "company": capture.company,
        "title": capture.title,
        "description_text": capture.description_text,
    }
    missing_fields = [
        field_name
        for field_name, value in required_fields.items()
        if value is None or not str(value).strip()
    ]

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Missing required fields for capture confirmation",
                "missing_fields": missing_fields,
            },
        )

    job = _job_from_capture(capture)

    capture.user_confirmed = True
    db.add(job)
    db.commit()
    db.refresh(job)

    return job
