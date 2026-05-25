from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Application, ApplicationEvent, EmailLink, Job, ResumeVersion
from ..schemas import (
    APPLICATION_STATUS_SET,
    EMAIL_CLASSIFIED_STATUS_SET,
    ApplicationCreate,
    ApplicationEventCreate,
    ApplicationEventRead,
    ApplicationRead,
    EmailLinkCreate,
    EmailLinkRead,
)

router = APIRouter(prefix="/applications", tags=["applications"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- Timeline derivation -------------------------------------------------

# Per docs/contracts/application_status.md and ADR-010, timeline stage is
# computed server-side from (Application.status, Application.submitted_at,
# attached EmailLink rows). The frontend must not re-derive it.
_STATUS_TO_STAGE = {
    "withdrawn": "withdrawn",
    "offer": "offer",
    "rejected": "rejected",
    "interview": "interview",
    "response_received": "response_received",
}

_NON_CONFIRMATION_SIGNALS = {"rejection", "next_step", "offer"}


def compute_timeline_stage(
    application: Application, email_links: Iterable[EmailLink]
) -> str:
    """Return the derived timeline stage for ``application``.

    Rules are applied in contract order; first matching rule wins.
    """
    mapped = _STATUS_TO_STAGE.get(application.status)
    if mapped is not None:
        return mapped

    if application.status == "submitted" or application.submitted_at is not None:
        classifications = {link.classified_status for link in email_links}
        has_confirmation = "confirmation" in classifications
        has_other_signal = bool(classifications & _NON_CONFIRMATION_SIGNALS)
        if has_confirmation and not has_other_signal:
            return "confirmation_received"
        return "sent"

    return "draft"


# Sort key matching the contract: rows with non-null received_at come first
# (newest first), then ties (and null-received rows) break on created_at desc.
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _email_link_sort_key(link: EmailLink) -> tuple:
    received_missing = link.received_at is None
    received_seconds = (
        -(_ensure_aware(link.received_at) - _EPOCH).total_seconds()
        if link.received_at is not None
        else 0.0
    )
    created_seconds = -(_ensure_aware(link.created_at) - _EPOCH).total_seconds()
    return (received_missing, received_seconds, created_seconds)


def _sorted_email_links(links: Iterable[EmailLink]) -> list[EmailLink]:
    return sorted(links, key=_email_link_sort_key)


def _build_application_read(application: Application) -> ApplicationRead:
    sorted_links = _sorted_email_links(application.email_links)
    return ApplicationRead(
        id=application.id,
        job_id=application.job_id,
        resume_version_id=application.resume_version_id,
        status=application.status,
        submitted_at=application.submitted_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
        timeline_stage=compute_timeline_stage(application, application.email_links),
        last_email_link=(
            EmailLinkRead.model_validate(sorted_links[0]) if sorted_links else None
        ),
        email_link_count=len(application.email_links),
    )


# ---- Application endpoints ----------------------------------------------


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate, db: Session = Depends(get_db)
) -> ApplicationRead:
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
    return _build_application_read(application)


@router.get("", response_model=list[ApplicationRead])
def list_applications(db: Session = Depends(get_db)) -> list[ApplicationRead]:
    apps = (
        db.query(Application)
        .options(selectinload(Application.email_links))
        .order_by(Application.created_at.desc())
        .all()
    )
    return [_build_application_read(app_obj) for app_obj in apps]


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: str, db: Session = Depends(get_db)
) -> ApplicationRead:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")
    return _build_application_read(app_obj)


@router.post("/{application_id}/submit", response_model=ApplicationRead)
def submit_application(
    application_id: str, db: Session = Depends(get_db)
) -> ApplicationRead:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    # Idempotent: if already submitted, return the existing row without
    # creating a duplicate event or moving submitted_at.
    if app_obj.status == "submitted":
        return _build_application_read(app_obj)

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
    return _build_application_read(app_obj)


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


# ---- EmailLink endpoints (per docs/contracts/application_status.md) ----

# Per the contract, recording an EmailLink may transition Application.status
# and always appends an ApplicationEvent. The mapping below pins
# (target_status, event_type) per classification. ``target_status = None``
# means: do not change status. ``blocked_by`` lists statuses that veto the
# transition (sticky cases like ``withdrawn``); when blocked, the event is
# still recorded but status stays put.
_EMAIL_SIDE_EFFECTS: dict[str, dict] = {
    "confirmation": {
        "target_status": None,
        "blocked_by": set(),
        "event_type": "email_confirmation_received",
    },
    "rejection": {
        "target_status": "rejected",
        "blocked_by": {"withdrawn"},
        "event_type": "email_rejection_received",
    },
    "next_step": {
        "target_status": "interview",
        "blocked_by": {"rejected", "withdrawn", "offer"},
        "event_type": "email_next_step_received",
    },
    "offer": {
        "target_status": "offer",
        "blocked_by": {"withdrawn"},
        "event_type": "email_offer_received",
    },
    "other": {
        "target_status": None,
        "blocked_by": set(),
        "event_type": "email_other_received",
    },
}


def _find_existing_email_link(
    db: Session, application_id: str, gmail_message_id: str
) -> Optional[EmailLink]:
    return (
        db.query(EmailLink)
        .filter(
            EmailLink.application_id == application_id,
            EmailLink.gmail_message_id == gmail_message_id,
        )
        .one_or_none()
    )


@router.post(
    "/{application_id}/email-links",
    response_model=EmailLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_email_link(
    application_id: str,
    payload: EmailLinkCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> EmailLinkRead:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    if payload.classified_status not in EMAIL_CLASSIFIED_STATUS_SET:
        raise HTTPException(
            status_code=422,
            detail=f"invalid classified_status: {payload.classified_status}",
        )

    # Idempotency on (application_id, gmail_message_id): if a row already
    # exists for the same logical message, return it with 200 and do not
    # append a duplicate event or re-apply the status change.
    existing = _find_existing_email_link(db, application_id, payload.gmail_message_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return EmailLinkRead.model_validate(existing)

    rules = _EMAIL_SIDE_EFFECTS[payload.classified_status]
    target_status = rules["target_status"]
    blocked_by = rules["blocked_by"]

    link = EmailLink(
        application_id=app_obj.id,
        gmail_message_id=payload.gmail_message_id,
        gmail_thread_id=payload.gmail_thread_id,
        subject=payload.subject,
        sender=payload.sender,
        received_at=payload.received_at,
        classified_status=payload.classified_status,
        confidence=payload.confidence,
    )
    db.add(link)

    if target_status is not None and app_obj.status not in blocked_by:
        app_obj.status = target_status

    db.add(
        ApplicationEvent(
            application_id=app_obj.id,
            event_type=rules["event_type"],
            source="email",
        )
    )

    db.commit()
    db.refresh(link)
    return EmailLinkRead.model_validate(link)


@router.get(
    "/{application_id}/email-links",
    response_model=list[EmailLinkRead],
)
def list_email_links(
    application_id: str, db: Session = Depends(get_db)
) -> list[EmailLinkRead]:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    links = (
        db.query(EmailLink)
        .filter(EmailLink.application_id == application_id)
        .all()
    )
    return [EmailLinkRead.model_validate(link) for link in _sorted_email_links(links)]
