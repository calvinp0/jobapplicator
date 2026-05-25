from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import (
    Application,
    ApplicationEvent,
    ClaudeRun,
    EmailLink,
    Job,
    ResumeVersion,
)
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


def _derive_submission_status(application: Application) -> str:
    if application.submitted_at is not None or application.status not in {
        "draft",
        "generated",
        "approved",
    }:
        # Once an application is in a post-submission state (or carries a
        # submitted_at timestamp), treat it as submitted from the dashboard's
        # perspective. Everything still in draft/generated/approved is
        # "not_submitted".
        return "submitted"
    return "not_submitted"


# Mapping from EmailLink.classified_status to the dashboard email state.
_EMAIL_CLASSIFICATION_TO_STATE = {
    "confirmation": "classified_neutral",
    "rejection": "classified_rejection",
    "next_step": "classified_positive",
    "offer": "classified_positive",
    "other": "classified_neutral",
}


def _derive_email_status(
    application: Application, sorted_links: list[EmailLink]
) -> str:
    if sorted_links:
        latest = sorted_links[0]
        classification = latest.classified_status
        if classification is None:
            return "needs_review"
        return _EMAIL_CLASSIFICATION_TO_STATE.get(classification, "email_received")
    # No emails attached yet. If we know the user submitted, we're "watching"
    # for a response; otherwise we are not watching yet.
    if application.submitted_at is not None or application.status == "submitted":
        return "watching"
    return "not_watching"


def _derive_next_action(
    application: Application, sorted_links: list[EmailLink]
) -> str:
    status = application.status
    if status == "withdrawn":
        return "Withdrawn"
    if status == "rejected":
        return "Rejected"
    if status == "offer":
        return "Respond to offer"
    if status == "interview":
        return "Interview response needed"
    if status == "response_received":
        return "Review response"
    if status == "submitted":
        if sorted_links:
            latest = sorted_links[0]
            classification = latest.classified_status
            if classification in {"rejection", "next_step", "offer"}:
                return "Review detected email"
            if classification == "confirmation":
                return "Waiting for response"
            return "Review detected email"
        return "Waiting for email"
    if status == "approved":
        return "Ready to submit"
    if status == "generated":
        return "Review draft"
    # draft and any unexpected status fall through here.
    return "Generate draft"


def _latest_run_for_application(
    application: Application, db: Session
) -> Optional[ClaudeRun]:
    # Prefer the run that produced the linked resume version; otherwise fall
    # back to the most recent run for the job. The fallback keeps the
    # "latest run" surface meaningful for applications created before a
    # resume version was approved/linked.
    if application.resume_version_id is not None:
        version = db.get(ResumeVersion, application.resume_version_id)
        if version is not None and version.claude_run_id is not None:
            run = db.get(ClaudeRun, version.claude_run_id)
            if run is not None:
                return run
    return (
        db.query(ClaudeRun)
        .filter(ClaudeRun.job_id == application.job_id)
        .order_by(ClaudeRun.created_at.desc())
        .first()
    )


def _build_application_read(
    application: Application, db: Optional[Session] = None
) -> ApplicationRead:
    sorted_links = _sorted_email_links(application.email_links)
    last_email_at = None
    if sorted_links:
        last_email_at = sorted_links[0].received_at or sorted_links[0].created_at
    latest_run = (
        _latest_run_for_application(application, db) if db is not None else None
    )
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
        submission_status=_derive_submission_status(application),
        email_status=_derive_email_status(application, sorted_links),
        next_action=_derive_next_action(application, sorted_links),
        latest_run_id=latest_run.id if latest_run is not None else None,
        latest_run_status=latest_run.status if latest_run is not None else None,
        last_email_at=last_email_at,
    )


# Sort priority for the Applications dashboard: rows still needing user
# action come first, then in-flight states, then closed states. Ties break on
# updated_at desc (handled at the query layer).
_DASHBOARD_PRIORITY = {
    "response_received": 0,
    "approved": 1,  # ready to submit
    "generated": 2,
    "draft": 3,
    "submitted": 4,
    "interview": 5,
    "offer": 6,
    "rejected": 7,
    "withdrawn": 8,
}


def _dashboard_sort_key(reads: list[ApplicationRead]) -> list[ApplicationRead]:
    def key(app: ApplicationRead) -> tuple:
        # Boost rows with a detected (non-confirmation) email up to the top
        # so the user sees them before regular submitted/draft items.
        link = app.last_email_link
        has_actionable_email = (
            link is not None
            and link.classified_status in {"rejection", "next_step", "offer"}
            and app.status not in {"rejected", "interview", "offer", "withdrawn"}
        )
        attention = 0 if has_actionable_email else 1
        priority = _DASHBOARD_PRIORITY.get(app.status, 99)
        updated_ts = _ensure_aware(app.updated_at)
        return (attention, priority, -updated_ts.timestamp())

    return sorted(reads, key=key)


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
    return _build_application_read(application, db)


@router.get("", response_model=list[ApplicationRead])
def list_applications(db: Session = Depends(get_db)) -> list[ApplicationRead]:
    apps = (
        db.query(Application)
        .options(selectinload(Application.email_links))
        .order_by(Application.updated_at.desc())
        .all()
    )
    reads = [_build_application_read(app_obj, db) for app_obj in apps]
    return _dashboard_sort_key(reads)


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: str, db: Session = Depends(get_db)
) -> ApplicationRead:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")
    return _build_application_read(app_obj, db)


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
        return _build_application_read(app_obj, db)

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
    return _build_application_read(app_obj, db)


def _mark_status(
    db: Session,
    application_id: str,
    new_status: str,
    event_type: str,
) -> ApplicationRead:
    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    # Idempotent: do not append a duplicate event when the application is
    # already in the requested status.
    if app_obj.status == new_status:
        return _build_application_read(app_obj, db)

    now = _utcnow()
    app_obj.status = new_status
    db.add(
        ApplicationEvent(
            application_id=app_obj.id,
            event_type=event_type,
            event_time=now,
            source="user",
        )
    )
    db.commit()
    db.refresh(app_obj)
    return _build_application_read(app_obj, db)


@router.post("/{application_id}/mark-rejected", response_model=ApplicationRead)
def mark_rejected(
    application_id: str, db: Session = Depends(get_db)
) -> ApplicationRead:
    return _mark_status(db, application_id, "rejected", "marked_rejected")


@router.post("/{application_id}/mark-interview", response_model=ApplicationRead)
def mark_interview(
    application_id: str, db: Session = Depends(get_db)
) -> ApplicationRead:
    return _mark_status(db, application_id, "interview", "marked_interview")


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
