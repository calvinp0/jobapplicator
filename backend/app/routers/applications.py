from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
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
    EMAIL_STATUS_SET,
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
# The vocabulary is pinned by docs/contracts/gmail_integration.md.
_EMAIL_CLASSIFICATION_TO_STATE = {
    "confirmation": "confirmation_found",
    "rejection": "classified_rejection",
    "next_step": "classified_interview",
    "offer": "classified_offer",
    "other": "classified_neutral",
}


def derive_email_status(
    application: Application, sorted_links: list[EmailLink]
) -> str:
    """Return one of ``EMAIL_STATUSES`` for ``application``.

    The contract for this derivation lives in
    ``docs/contracts/gmail_integration.md``. Only the manual-entry subset
    of the vocabulary is emitted today; ``no_match`` and ``error`` are
    reserved for the future Gmail-poll path.
    """
    if sorted_links:
        latest = sorted_links[0]
        classification = latest.classified_status
        if classification is None:
            return "needs_review"
        return _EMAIL_CLASSIFICATION_TO_STATE.get(classification, "email_received")
    if application.submitted_at is not None or application.status == "submitted":
        # Task 083: a Gmail application-search may have produced a
        # zero-classification outcome (``no_match`` or ``email_received``)
        # without writing an ``EmailLink`` row yet. Honor it when set.
        search_state = getattr(application, "email_search_state", None)
        if search_state in ("no_match", "email_received", "error"):
            return search_state
        return "watching"
    return "not_watching"


def derive_next_action(
    application: Application, sorted_links: list[EmailLink]
) -> str:
    """Return the dashboard "next action" hint for ``application``.

    The wording is Gmail-aware so the dashboard can communicate
    ``email_status`` without the user having to read the raw state.
    """
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
            if classification is None:
                return "Review detected email"
            if classification == "confirmation":
                return "Waiting for response"
            # Non-confirmation classified links indicate a decision-bearing
            # email that the user should triage.
            return "Review detected email"
        return "Waiting for email"
    if status == "approved":
        return "Ready to submit"
    if status == "generated":
        return "Review draft"
    return "Generate draft"


def build_default_gmail_tracking_state() -> dict:
    """Return the default-shaped Gmail-tracking dict for a new application.

    Mirrors the field list pinned by
    ``docs/contracts/gmail_integration.md``. Used by tests and any caller
    that wants to know the wire-shape default without touching the DB.
    """
    return {
        "email_status": "not_watching",
        "gmail_query": None,
        "last_gmail_check_at": None,
        "last_matched_email_at": None,
        "matched_email_count": 0,
        "latest_email_subject": None,
        "latest_email_from": None,
        "latest_email_snippet": None,
        "latest_email_classification": None,
        "latest_email_confidence": None,
        "latest_email_evidence": None,
    }


def is_valid_email_status(value: str) -> bool:
    """True iff ``value`` is one of ``EMAIL_STATUSES``."""
    return value in EMAIL_STATUS_SET


# Internal aliases kept for module callers that still reference the older
# private names. Public names above are the contract-stable surface.
_derive_email_status = derive_email_status
_derive_next_action = derive_next_action


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
    latest_link = sorted_links[0] if sorted_links else None
    last_email_at = None
    if latest_link is not None:
        last_email_at = latest_link.received_at or latest_link.created_at
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
            EmailLinkRead.model_validate(latest_link) if latest_link else None
        ),
        email_link_count=len(application.email_links),
        submission_status=_derive_submission_status(application),
        email_status=derive_email_status(application, sorted_links),
        next_action=derive_next_action(application, sorted_links),
        latest_run_id=latest_run.id if latest_run is not None else None,
        latest_run_status=latest_run.status if latest_run is not None else None,
        last_email_at=last_email_at,
        # Gmail tracking fields (docs/contracts/gmail_integration.md).
        gmail_query=application.gmail_query,
        last_gmail_check_at=application.last_gmail_check_at,
        last_matched_email_at=last_email_at,
        matched_email_count=len(application.email_links),
        latest_email_subject=latest_link.subject if latest_link else None,
        latest_email_from=latest_link.sender if latest_link else None,
        # ``snippet`` and ``evidence`` are reserved for the future Gmail
        # poll path; the EmailLink model does not persist them yet.
        latest_email_snippet=None,
        latest_email_classification=(
            latest_link.classified_status if latest_link else None
        ),
        latest_email_confidence=latest_link.confidence if latest_link else None,
        latest_email_evidence=None,
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


# ---- Gmail application search (task 083) ------------------------------

# All Gmail-related interaction goes through ``app.gmail_client``; the
# router stays thin so it does not pull google libraries into the import
# graph (the task-080 safety guard
# ``test_no_gmail_outbound_modules_imported`` enforces this).


class GmailApplicationSearchRequest(BaseModel):
    max_results: int = Field(default=10, ge=1)
    extra_terms: list[str] = Field(default_factory=list, max_length=10)
    include_ats_terms: bool = True


class GmailSearchCandidate(BaseModel):
    message_id: str | None = None
    thread_id: str | None = None
    subject: str | None = None
    from_: str | None = Field(default=None, alias="from")
    date: str | None = None
    snippet: str | None = None
    matched_signals: list[str] = Field(default_factory=list)
    match_score: float = 0.0

    model_config = {"populate_by_name": True}


class GmailApplicationSearchResponse(BaseModel):
    application_id: str
    gmail_connected: bool
    gmail_query: str | None = None
    count: int = 0
    candidates: list[GmailSearchCandidate] = Field(default_factory=list)
    message: str | None = None


@router.post(
    "/{application_id}/gmail/search",
    response_model=GmailApplicationSearchResponse,
)
def search_application_gmail(
    application_id: str,
    payload: GmailApplicationSearchRequest,
    db: Session = Depends(get_db),
) -> GmailApplicationSearchResponse:
    """Search Gmail (read-only) for messages that may relate to ``application_id``.

    This endpoint **does not** classify emails, modify the mailbox, or
    update the application's main outcome status. It returns candidate
    metadata + a deterministic match score; the user remains the final
    reviewer.
    """
    from .. import gmail_client
    from ..gmail_application_search import (
        ApplicationQueryInputs,
        MAX_APPLICATION_SEARCH_RESULTS,
        MatchInputs,
        build_application_query,
        safe_metadata,
        score_candidate,
    )

    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    job_obj = db.get(Job, app_obj.job_id)
    if job_obj is None:
        # Defensive: applications always reference a job in the schema,
        # but a corrupted row should not 500 the search.
        raise HTTPException(status_code=404, detail="job not found")

    # If Gmail is not connected, the contract says return a clear
    # message and do *not* mutate the application's email_status.
    status_info = gmail_client.get_status()
    if not status_info.get("connected"):
        return GmailApplicationSearchResponse(
            application_id=app_obj.id,
            gmail_connected=False,
            message="Connect Gmail before searching for application emails",
        )

    extra_terms = tuple(
        t.strip() for t in (payload.extra_terms or []) if t and t.strip()
    )
    inputs = ApplicationQueryInputs(
        company=job_obj.company,
        job_title=job_obj.title,
        submitted_at=app_obj.submitted_at,
        extra_terms=extra_terms,
        include_ats_terms=payload.include_ats_terms,
    )
    query = build_application_query(inputs)

    capped = min(
        int(payload.max_results),
        MAX_APPLICATION_SEARCH_RESULTS,
        gmail_client.MAX_TEST_SEARCH_RESULTS,
    )

    try:
        raw_messages: list[dict[str, Any]] = gmail_client.search_messages(
            query, capped
        )
    except gmail_client.GmailNotConnectedError:
        # Status check above said connected but the token disappeared.
        return GmailApplicationSearchResponse(
            application_id=app_obj.id,
            gmail_connected=False,
            gmail_query=query,
            message="Connect Gmail before searching for application emails",
        )
    except gmail_client.GmailDependencyError as exc:
        # Surface the dependency issue cleanly; do not change email_status.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception:  # pragma: no cover - defensive
        # Record the error outcome so the dashboard can surface it.
        app_obj.email_search_state = "error"
        app_obj.last_gmail_check_at = _utcnow()
        db.commit()
        raise

    match_inputs = MatchInputs(
        company=job_obj.company,
        job_title=job_obj.title,
        submitted_at=app_obj.submitted_at,
        extra_terms=extra_terms,
    )

    candidates: list[GmailSearchCandidate] = []
    for raw in raw_messages:
        meta = safe_metadata(raw)
        score, signals = score_candidate(meta, match_inputs)
        candidates.append(
            GmailSearchCandidate(
                message_id=meta.get("id"),
                thread_id=meta.get("thread_id"),
                subject=meta.get("subject"),
                **{"from": meta.get("from")},
                date=meta.get("date"),
                snippet=meta.get("snippet"),
                matched_signals=signals,
                match_score=round(score, 4),
            )
        )

    # Stable order: highest score first, then by original index (Gmail's
    # own newest-first order). Python sort is stable so equal-score
    # candidates retain Gmail's ordering.
    candidates.sort(key=lambda c: c.match_score, reverse=True)

    app_obj.last_gmail_check_at = _utcnow()
    app_obj.email_search_state = "email_received" if candidates else "no_match"
    db.commit()

    return GmailApplicationSearchResponse(
        application_id=app_obj.id,
        gmail_connected=True,
        gmail_query=query,
        count=len(candidates),
        candidates=candidates,
    )


# ---- Gmail application classification (task 084) ----------------------

# The classifier itself lives in :mod:`app.gmail_application_classifier`
# and only sees the safe-metadata fields (subject / from / date /
# snippet). Persisting an EmailLink from a classification result reuses
# the existing ``_EMAIL_SIDE_EFFECTS`` rules so terminal-status
# protection (``withdrawn`` is sticky, ``rejected`` blocks ``next_step``,
# etc.) stays in one place.


class GmailCandidateInput(BaseModel):
    """Safe-metadata view of a Gmail candidate.

    Mirrors the candidate shape returned by the task-083 search endpoint
    so the frontend (and ``curl``) can hand the same payload to the
    classify endpoint without reshaping it. Extra keys are ignored at
    the schema layer; full bodies are not accepted.
    """

    message_id: str | None = None
    thread_id: str | None = None
    subject: str | None = None
    from_: str | None = Field(default=None, alias="from")
    date: str | None = None
    snippet: str | None = None

    model_config = {"populate_by_name": True}


class GmailClassifyRequest(BaseModel):
    """Request body for ``POST /applications/{id}/gmail/classify``.

    Exactly one of ``candidate`` or ``message_id`` must be provided. The
    ``message_id`` form is reserved for a future task that persists
    candidates; today the endpoint short-circuits with a clear error
    because no candidates are stored.
    """

    message_id: str | None = None
    candidate: GmailCandidateInput | None = None
    classify_top_candidate: bool = False


class EvidenceRead(BaseModel):
    field_: str = Field(alias="field")
    text: str
    reason: str

    model_config = {"populate_by_name": True}


class GmailClassifyResponse(BaseModel):
    application_id: str
    message_id: str | None
    classification: str
    confidence: float
    email_status: str
    application_status: str
    evidence: list[EvidenceRead] = Field(default_factory=list)
    reason: str
    application_status_changed: bool = False
    email_link_id: str | None = None


@router.post(
    "/{application_id}/gmail/classify",
    response_model=GmailClassifyResponse,
)
def classify_application_gmail(
    application_id: str,
    payload: GmailClassifyRequest,
    db: Session = Depends(get_db),
) -> GmailClassifyResponse:
    """Classify a Gmail candidate email against ``application_id``.

    The classifier is deterministic (phrase tables + precedence) and
    only inspects the safe-metadata fields the contract allows. When a
    classification results in a ``classified_status`` that maps onto the
    smaller ``EmailLink`` vocabulary, the endpoint writes an EmailLink
    row so the existing side-effect rules in
    ``application_status.md`` apply (and so ``withdrawn`` stays sticky).
    """
    from ..gmail_application_classifier import (
        LABEL_TO_APPLICATION_STATUS,
        LABEL_TO_EMAIL_LINK_STATUS,
        LABEL_TO_EMAIL_STATUS,
        candidate_from_metadata,
        classify_candidate,
    )

    app_obj = db.get(Application, application_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="application not found")

    if payload.candidate is None:
        # Task 083 does not persist candidates today, so ``message_id``
        # and ``classify_top_candidate`` cannot be honored without a
        # candidate payload. Surface a clear error rather than guessing.
        if payload.message_id or payload.classify_top_candidate:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Candidate metadata is required; the project does not "
                    "persist Gmail search candidates yet. Run "
                    "POST /applications/{id}/gmail/search and pass the "
                    "candidate metadata to this endpoint."
                ),
            )
        raise HTTPException(
            status_code=422,
            detail="missing 'candidate' metadata",
        )

    candidate_meta = payload.candidate.model_dump(by_alias=True)
    candidate = candidate_from_metadata(candidate_meta)
    result = classify_candidate(candidate)

    classification = result.classification
    email_status_label = LABEL_TO_EMAIL_STATUS[classification]
    email_link_status = LABEL_TO_EMAIL_LINK_STATUS[classification]
    proposed_app_status = LABEL_TO_APPLICATION_STATUS[classification]

    application_status_changed = False
    email_link_row_id: str | None = None
    pre_status = app_obj.status

    # ``withdrawn`` is sticky regardless of classifier output.
    if app_obj.status == "withdrawn":
        email_link_status = None
        proposed_app_status = None

    if email_link_status is not None and payload.candidate.message_id:
        # Reuse the existing EmailLink side-effect rules so terminal
        # statuses behave consistently with the manual-entry flow.
        rules = _EMAIL_SIDE_EFFECTS[email_link_status]
        existing = _find_existing_email_link(
            db, application_id, payload.candidate.message_id
        )
        if existing is None:
            link = EmailLink(
                application_id=app_obj.id,
                gmail_message_id=payload.candidate.message_id,
                gmail_thread_id=payload.candidate.thread_id,
                subject=payload.candidate.subject,
                sender=payload.candidate.from_,
                received_at=None,
                classified_status=email_link_status,
                confidence=result.confidence,
            )
            db.add(link)
            target_status = rules["target_status"]
            if (
                target_status is not None
                and app_obj.status not in rules["blocked_by"]
            ):
                app_obj.status = target_status
            db.add(
                ApplicationEvent(
                    application_id=app_obj.id,
                    event_type=rules["event_type"],
                    source="email",
                    notes=f"classifier:{classification}",
                )
            )
            db.flush()
            email_link_row_id = link.id
        else:
            email_link_row_id = existing.id

    app_obj.last_gmail_check_at = _utcnow()
    db.commit()
    db.refresh(app_obj)

    if app_obj.status != pre_status:
        application_status_changed = True

    # Surface the email_status the classifier *intends*. The persisted
    # ``derive_email_status`` may be coarser (e.g. ``classified_interview``
    # vs ``classified_assessment``) until the contract grows additional
    # ``EmailLink.classified_status`` values; the response uses the
    # contract's full vocabulary so the UI / curl user sees the
    # classifier's actual intent.
    return GmailClassifyResponse(
        application_id=app_obj.id,
        message_id=payload.candidate.message_id,
        classification=classification,
        confidence=round(result.confidence, 4),
        email_status=email_status_label,
        application_status=app_obj.status,
        evidence=[
            EvidenceRead(field=e.field, text=e.text, reason=e.reason)
            for e in result.evidence
        ],
        reason=result.reason,
        application_status_changed=application_status_changed,
        email_link_id=email_link_row_id,
    )
