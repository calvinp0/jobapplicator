"""User-editable application settings.

Hosts the default-LLM-provider setting (ADR-009 / task 066) and the
persisted Gmail OAuth config (task 088). Both surfaces bundle their
current value with what the Settings page needs to render in one round
trip; for Gmail the response is sanitized so the client secret never
leaves the backend in plaintext.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import gmail_settings
from ..db import get_db
from ..llm_providers import list_providers
from ..local_reset import create_backup, reset_local_data
from ..schemas import LLMProviderRead
from ..settings import (
    UnknownLLMProviderError,
    get_default_llm_provider,
    set_default_llm_provider,
)


router = APIRouter(prefix="/settings", tags=["settings"])


class DefaultLLMProviderRead(BaseModel):
    default_provider: str
    available: list[LLMProviderRead]


class DefaultLLMProviderUpdate(BaseModel):
    default_provider: str


def _available_providers() -> list[LLMProviderRead]:
    return [
        LLMProviderRead(
            id=p.id,
            display_name=p.display_name,
            default_binary=p.default_binary,
            binary_env_var=p.binary_env_var,
        )
        for p in list_providers()
    ]


@router.get("/llm-provider", response_model=DefaultLLMProviderRead)
def read_default_llm_provider() -> DefaultLLMProviderRead:
    return DefaultLLMProviderRead(
        default_provider=get_default_llm_provider(),
        available=_available_providers(),
    )


@router.put("/llm-provider", response_model=DefaultLLMProviderRead)
def update_default_llm_provider(
    payload: DefaultLLMProviderUpdate,
) -> DefaultLLMProviderRead:
    try:
        set_default_llm_provider(payload.default_provider)
    except UnknownLLMProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DefaultLLMProviderRead(
        default_provider=get_default_llm_provider(),
        available=_available_providers(),
    )


# ---- Gmail OAuth config (task 088) -----------------------------------


class GmailOAuthSettingsRead(BaseModel):
    """Sanitized snapshot of the current Gmail OAuth config.

    The client secret is **never** returned in plaintext. ``source`` is
    one of ``"settings"``, ``"environment"``, or ``"none"`` so the UI
    can label where the active config came from. ``updated_at`` is the
    ISO-8601 timestamp from the persisted row (``null`` for env-loaded
    or unset configs).
    """

    configured: bool
    source: str
    google_client_id: str | None
    has_google_client_secret: bool
    google_client_secret_preview: str
    google_redirect_uri: str
    gmail_token_path: str
    updated_at: str | None


class GmailOAuthSettingsUpdate(BaseModel):
    """Request body for ``PUT /settings/gmail-oauth``.

    ``google_client_secret`` may be omitted (``None``) when
    ``preserve_existing_secret`` is true and a secret is already saved.
    All other fields are required.
    """

    google_client_id: str = Field(..., min_length=1)
    google_client_secret: str | None = Field(default=None)
    google_redirect_uri: str = Field(..., min_length=1)
    gmail_token_path: str | None = None
    preserve_existing_secret: bool = False


@router.get("/gmail-oauth", response_model=GmailOAuthSettingsRead)
def read_gmail_oauth_settings() -> GmailOAuthSettingsRead:
    return GmailOAuthSettingsRead(**gmail_settings.get_settings_view())


@router.put("/gmail-oauth", response_model=GmailOAuthSettingsRead)
def update_gmail_oauth_settings(
    payload: GmailOAuthSettingsUpdate,
) -> GmailOAuthSettingsRead:
    # Resolve the secret: an empty string is treated as "missing".
    incoming_secret = (payload.google_client_secret or "").strip()
    if not incoming_secret and payload.preserve_existing_secret:
        stored = gmail_settings.get_stored_config()
        if stored is None:
            raise HTTPException(
                status_code=400,
                detail="preserve_existing_secret was set but no saved secret exists",
            )
        incoming_secret = stored.google_client_secret

    try:
        gmail_settings.save_config(
            google_client_id=payload.google_client_id,
            google_client_secret=incoming_secret,
            google_redirect_uri=payload.google_redirect_uri,
            gmail_token_path=payload.gmail_token_path,
        )
    except gmail_settings.GmailSettingsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return GmailOAuthSettingsRead(**gmail_settings.get_settings_view())


@router.delete("/gmail-oauth", response_model=GmailOAuthSettingsRead)
def delete_gmail_oauth_settings() -> GmailOAuthSettingsRead:
    gmail_settings.delete_config()
    return GmailOAuthSettingsRead(**gmail_settings.get_settings_view())


# ---- Reset local data (task 121) -------------------------------------

# Required confirmation text. The endpoint refuses to do anything unless
# the client echoes this exact string, so a stray POST can never wipe
# data — the destructive intent has to be explicit.
RESET_CONFIRMATION = "RESET"


class ResetLocalDataRequest(BaseModel):
    """Body for ``POST /settings/reset-local-data``.

    ``confirmation`` must equal ``"RESET"`` exactly; any other value is
    rejected with a 400 before anything is deleted.
    """

    confirmation: str


class ResetLocalDataResponse(BaseModel):
    """Summary of a completed reset.

    ``backup_path`` is the project-relative location of the SQLite backup
    written before the reset (``null`` only when there was no SQLite file
    to back up). ``deleted`` maps each cleared category to its row count.
    """

    ok: bool
    backup_path: str | None
    deleted: dict[str, int]


@router.post("/reset-local-data", response_model=ResetLocalDataResponse)
def reset_local_data_endpoint(
    payload: ResetLocalDataRequest, db: Session = Depends(get_db)
) -> ResetLocalDataResponse:
    """Back up, then delete local jobs/applications/runs/captures/drafts.

    Imported source material (master resumes, evidence banks, candidate
    context files) and Gmail tokens are preserved. A timestamped SQLite
    backup is written before anything is removed.
    """
    if payload.confirmation != RESET_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail="Confirmation text must be exactly 'RESET'.",
        )

    backup_path = create_backup()
    deleted = reset_local_data(db)
    return ResetLocalDataResponse(
        ok=True, backup_path=backup_path, deleted=deleted
    )
