"""Read-only Gmail OAuth + test-search + sync endpoints.

These routes are the only HTTP surface that touches Gmail. They are
**strictly read-only**: the contract in
``docs/contracts/gmail_integration.md`` forbids any send/archive/delete/
label operation, and there are no routes here that perform any of those
actions.

The routes import :mod:`app.gmail_client` lazily inside each handler so
``app.main`` can be imported without the optional google libraries
installed (and so the task-080 safety guard
``test_no_gmail_outbound_modules_imported`` keeps passing).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Application, ApplicationEvent, EmailLink, Job


router = APIRouter(prefix="/gmail", tags=["gmail"])

# Per-application sync caps (task 086). The defaults match the task
# spec; the upper bounds keep a single sync call bounded so the user
# cannot accidentally hammer Gmail's quota.
SYNC_MAX_APPLICATIONS_DEFAULT = 25
SYNC_MAX_APPLICATIONS_CEILING = 50
SYNC_MAX_RESULTS_PER_APPLICATION_DEFAULT = 10
SYNC_MAX_RESULTS_PER_APPLICATION_CEILING = 10

# Applications in these statuses are candidates for the manual sync.
# Mirrors the include list in the task spec, mapped onto the project's
# existing ``APPLICATION_STATUSES`` vocabulary. ``response_received`` is
# the project equivalent of the spec's ``email_received`` lane.
SYNC_INCLUDED_STATUSES: frozenset[str] = frozenset(
    {"submitted", "response_received", "interview"}
)

# Terminal/closed statuses that are excluded by default. With
# ``include_terminal=true`` the sync considers everything except
# ``withdrawn`` (which is sticky and must never be auto-changed) and the
# pre-submission lanes (``draft`` / ``generated`` / ``approved``).
SYNC_TERMINAL_STATUSES: frozenset[str] = frozenset({"rejected", "offer"})

# Pre-submission lanes never sync; the spec lists ``draft`` and the
# project's ``approved`` lane is the spec's ``ready_to_submit`` (the
# spec says only sync it when explicitly marked as watching, but
# nothing in the project explicitly marks ``approved`` as watching, so
# we exclude it for now).
SYNC_NEVER_SYNC_STATUSES: frozenset[str] = frozenset(
    {"draft", "generated", "approved"}
)


class GmailStatusRead(BaseModel):
    connected: bool
    configured: bool
    missing_config: list[str]
    email: str | None
    scopes: list[str]
    token_path_configured: bool
    last_checked_at: str | None


class GmailAuthUrlRead(BaseModel):
    auth_url: str
    scope: str


class GmailTestSearchRequest(BaseModel):
    query: str = Field(default="newer_than:7d", max_length=512)
    max_results: int = Field(default=5, ge=1)


class GmailMessageMetadata(BaseModel):
    id: str | None
    thread_id: str | None
    subject: str | None
    from_: str | None = Field(default=None, alias="from")
    date: str | None
    snippet: str | None

    model_config = {"populate_by_name": True}


class GmailTestSearchResponse(BaseModel):
    connected: bool
    query: str
    count: int
    messages: list[GmailMessageMetadata]


@router.get("/status", response_model=GmailStatusRead)
def gmail_status() -> GmailStatusRead:
    from .. import gmail_client

    return GmailStatusRead(**gmail_client.get_status())


@router.get("/auth-url", response_model=GmailAuthUrlRead)
def gmail_auth_url() -> GmailAuthUrlRead:
    from .. import gmail_client

    try:
        payload = gmail_client.build_auth_url()
    except gmail_client.GmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "gmail_oauth_not_configured",
                "message": str(exc),
                "missing": list(exc.missing),
            },
        ) from exc
    except gmail_client.GmailScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except gmail_client.GmailDependencyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return GmailAuthUrlRead(**payload)


@router.get("/oauth/callback", response_class=HTMLResponse)
def gmail_oauth_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,  # noqa: ARG001 — accepted for OAuth spec compliance
) -> HTMLResponse:
    from .. import gmail_client

    if error:
        return HTMLResponse(
            f"<h1>Gmail connection failed</h1><p>{error}</p>",
            status_code=400,
        )
    if not code:
        raise HTTPException(status_code=400, detail="missing 'code' parameter")

    try:
        gmail_client.exchange_code(code)
    except gmail_client.GmailNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except gmail_client.GmailScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except gmail_client.GmailDependencyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return HTMLResponse(
        "<h1>Gmail connected</h1>"
        "<p>You can close this window and return to the app.</p>"
    )


@router.post("/test-search", response_model=GmailTestSearchResponse)
def gmail_test_search(payload: GmailTestSearchRequest) -> GmailTestSearchResponse:
    from .. import gmail_client

    capped = min(payload.max_results, gmail_client.MAX_TEST_SEARCH_RESULTS)
    try:
        messages: list[dict[str, Any]] = gmail_client.search_messages(
            payload.query, capped
        )
    except gmail_client.GmailNotConnectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except gmail_client.GmailDependencyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return GmailTestSearchResponse(
        connected=True,
        query=payload.query,
        count=len(messages),
        messages=[GmailMessageMetadata(**m) for m in messages],
    )


# ---- Manual application sync (task 086) -------------------------------


class GmailSyncEvidence(BaseModel):
    field_: str = Field(alias="field")
    text: str
    reason: str

    model_config = {"populate_by_name": True}


class GmailSyncApplicationResult(BaseModel):
    application_id: str
    job_title: str | None
    company: str | None
    previous_email_status: str
    new_email_status: str
    previous_application_status: str
    new_application_status: str
    matched_email_count: int = 0
    classification: str | None = None
    confidence: float | None = None
    evidence: list[GmailSyncEvidence] = Field(default_factory=list)
    application_status_changed: bool = False
    gmail_query: str | None = None
    skipped_reason: str | None = None


class GmailSyncApplicationsRequest(BaseModel):
    """Body for ``POST /gmail/sync-applications``.

    Defaults mirror the task spec. ``classify`` toggles whether matched
    candidates are run through the deterministic classifier;
    ``include_terminal`` opts the sync into terminal lanes (``rejected``,
    ``offer``) but ``withdrawn`` is *always* skipped because it is sticky.
    """

    max_applications: int = Field(
        default=SYNC_MAX_APPLICATIONS_DEFAULT,
        ge=1,
        le=SYNC_MAX_APPLICATIONS_CEILING,
    )
    max_results_per_application: int = Field(
        default=SYNC_MAX_RESULTS_PER_APPLICATION_DEFAULT,
        ge=1,
        le=SYNC_MAX_RESULTS_PER_APPLICATION_CEILING,
    )
    classify: bool = True
    include_terminal: bool = False


class GmailSyncApplicationsResponse(BaseModel):
    gmail_connected: bool
    checked_count: int = 0
    updated_count: int = 0
    no_match_count: int = 0
    needs_review_count: int = 0
    results: list[GmailSyncApplicationResult] = Field(default_factory=list)
    message: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _select_applications_for_sync(
    db: Session, *, include_terminal: bool, limit: int
) -> list[Application]:
    allowed = set(SYNC_INCLUDED_STATUSES)
    if include_terminal:
        allowed |= SYNC_TERMINAL_STATUSES
    return list(
        db.query(Application)
        .options(selectinload(Application.email_links))
        .filter(Application.status.in_(allowed))
        .order_by(Application.updated_at.desc())
        .limit(limit)
        .all()
    )


@router.post(
    "/sync-applications",
    response_model=GmailSyncApplicationsResponse,
)
def sync_applications(
    payload: GmailSyncApplicationsRequest,
    db: Session = Depends(get_db),
) -> GmailSyncApplicationsResponse:
    """Manually sync Gmail for all relevant applications.

    Read-only Gmail use only (no send/archive/delete/label/modify).
    User-triggered; never started automatically. Terminal applications
    are excluded by default. ``withdrawn`` applications are *always*
    excluded from status changes regardless of ``include_terminal``.
    """
    from .. import gmail_client
    from ..gmail_application_classifier import (
        LABEL_TO_APPLICATION_STATUS,
        LABEL_TO_EMAIL_LINK_STATUS,
        LABEL_TO_EMAIL_STATUS,
        candidate_from_metadata,
        classify_candidate,
    )
    from ..gmail_application_search import (
        ApplicationQueryInputs,
        MAX_APPLICATION_SEARCH_RESULTS,
        MatchInputs,
        build_application_query,
        safe_metadata,
        score_candidate,
    )
    from ..routers.applications import (
        _EMAIL_SIDE_EFFECTS,
        _find_existing_email_link,
        _sorted_email_links,
        derive_email_status,
    )

    status_info = gmail_client.get_status()
    if not status_info.get("connected"):
        return GmailSyncApplicationsResponse(
            gmail_connected=False,
            message="Connect Gmail before syncing applications",
        )

    max_apps = min(int(payload.max_applications), SYNC_MAX_APPLICATIONS_CEILING)
    max_per_app = min(
        int(payload.max_results_per_application),
        SYNC_MAX_RESULTS_PER_APPLICATION_CEILING,
        MAX_APPLICATION_SEARCH_RESULTS,
        gmail_client.MAX_TEST_SEARCH_RESULTS,
    )

    applications = _select_applications_for_sync(
        db, include_terminal=payload.include_terminal, limit=max_apps
    )

    results: list[GmailSyncApplicationResult] = []
    updated_count = 0
    no_match_count = 0
    needs_review_count = 0

    for app_obj in applications:
        job_obj = db.get(Job, app_obj.job_id)
        previous_app_status = app_obj.status
        previous_email_status = derive_email_status(
            app_obj, _sorted_email_links(app_obj.email_links)
        )

        # ``withdrawn`` is sticky — skip entirely, never auto-change.
        if app_obj.status == "withdrawn":
            results.append(
                GmailSyncApplicationResult(
                    application_id=app_obj.id,
                    job_title=job_obj.title if job_obj else None,
                    company=job_obj.company if job_obj else None,
                    previous_email_status=previous_email_status,
                    new_email_status=previous_email_status,
                    previous_application_status=previous_app_status,
                    new_application_status=previous_app_status,
                    matched_email_count=len(app_obj.email_links),
                    skipped_reason="withdrawn",
                )
            )
            continue

        if job_obj is None:
            results.append(
                GmailSyncApplicationResult(
                    application_id=app_obj.id,
                    job_title=None,
                    company=None,
                    previous_email_status=previous_email_status,
                    new_email_status=previous_email_status,
                    previous_application_status=previous_app_status,
                    new_application_status=previous_app_status,
                    matched_email_count=len(app_obj.email_links),
                    skipped_reason="job_missing",
                )
            )
            continue

        query_inputs = ApplicationQueryInputs(
            company=job_obj.company,
            job_title=job_obj.title,
            submitted_at=app_obj.submitted_at,
            extra_terms=(),
            include_ats_terms=True,
        )
        query = build_application_query(query_inputs)

        try:
            raw_messages: list[dict[str, Any]] = gmail_client.search_messages(
                query, max_per_app
            )
        except gmail_client.GmailNotConnectedError:
            return GmailSyncApplicationsResponse(
                gmail_connected=False,
                message="Connect Gmail before syncing applications",
            )
        except gmail_client.GmailDependencyError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception:  # pragma: no cover - defensive
            app_obj.email_search_state = "error"
            app_obj.last_gmail_check_at = _utcnow()
            db.commit()
            raise

        match_inputs = MatchInputs(
            company=job_obj.company,
            job_title=job_obj.title,
            submitted_at=app_obj.submitted_at,
        )

        scored: list[tuple[float, list[str], dict[str, Any]]] = []
        for raw in raw_messages:
            meta = safe_metadata(raw)
            score, signals = score_candidate(meta, match_inputs)
            scored.append((score, signals, meta))
        scored.sort(key=lambda x: x[0], reverse=True)

        app_obj.last_gmail_check_at = _utcnow()
        classification_label: str | None = None
        confidence_value: float | None = None
        evidence_items: list[GmailSyncEvidence] = []
        new_app_status = previous_app_status
        new_email_status = previous_email_status

        if not scored:
            app_obj.email_search_state = "no_match"
            no_match_count += 1
            db.flush()
            new_email_status = derive_email_status(
                app_obj, _sorted_email_links(app_obj.email_links)
            )
        else:
            app_obj.email_search_state = "email_received"
            db.flush()

            if payload.classify:
                top_score, _signals, top_meta = scored[0]
                candidate = candidate_from_metadata(top_meta)
                result = classify_candidate(candidate)
                classification_label = result.classification
                confidence_value = round(result.confidence, 4)
                evidence_items = [
                    GmailSyncEvidence(
                        field=e.field, text=e.text, reason=e.reason
                    )
                    for e in result.evidence
                ]

                email_status_label = LABEL_TO_EMAIL_STATUS[classification_label]
                email_link_status = LABEL_TO_EMAIL_LINK_STATUS[
                    classification_label
                ]
                message_id = top_meta.get("id")
                if email_link_status is not None and message_id:
                    rules = _EMAIL_SIDE_EFFECTS[email_link_status]
                    existing = _find_existing_email_link(
                        db, app_obj.id, message_id
                    )
                    if existing is None:
                        link = EmailLink(
                            application_id=app_obj.id,
                            gmail_message_id=message_id,
                            gmail_thread_id=top_meta.get("thread_id"),
                            subject=top_meta.get("subject"),
                            sender=top_meta.get("from"),
                            received_at=None,
                            classified_status=email_link_status,
                            confidence=result.confidence,
                        )
                        db.add(link)
                        target = rules["target_status"]
                        if (
                            target is not None
                            and app_obj.status not in rules["blocked_by"]
                        ):
                            app_obj.status = target
                        db.add(
                            ApplicationEvent(
                                application_id=app_obj.id,
                                event_type=rules["event_type"],
                                source="email",
                                notes=f"sync:{classification_label}",
                            )
                        )
                        db.flush()

                new_app_status = app_obj.status
                new_email_status = email_status_label
                if email_status_label == "needs_review":
                    needs_review_count += 1
            else:
                new_email_status = derive_email_status(
                    app_obj, _sorted_email_links(app_obj.email_links)
                )

        if (
            new_app_status != previous_app_status
            or new_email_status != previous_email_status
        ):
            updated_count += 1

        results.append(
            GmailSyncApplicationResult(
                application_id=app_obj.id,
                job_title=job_obj.title,
                company=job_obj.company,
                previous_email_status=previous_email_status,
                new_email_status=new_email_status,
                previous_application_status=previous_app_status,
                new_application_status=new_app_status,
                matched_email_count=len(scored),
                classification=classification_label,
                confidence=confidence_value,
                evidence=evidence_items,
                application_status_changed=(
                    new_app_status != previous_app_status
                ),
                gmail_query=query,
            )
        )

    db.commit()

    return GmailSyncApplicationsResponse(
        gmail_connected=True,
        checked_count=len(results),
        updated_count=updated_count,
        no_match_count=no_match_count,
        needs_review_count=needs_review_count,
        results=results,
    )
