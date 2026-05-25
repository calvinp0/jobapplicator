"""Read-only Gmail OAuth + test-search endpoints (task 082).

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

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/gmail", tags=["gmail"])


class GmailStatusRead(BaseModel):
    connected: bool
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
