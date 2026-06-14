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

from .. import gmail_settings, local_llm
from ..db import get_db
from ..llm_providers import list_providers
from ..local_reset import create_backup, reset_local_data
from ..resume_export import default_exports_root, project_relative_path
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


# ---- Experimental local LLM config (task 123) ------------------------


class LocalLLMTaskPolicy(BaseModel):
    """Static per-task policy metadata surfaced to the Settings UI."""

    task: str
    risk: str
    configurable: bool
    default_local: bool


class LocalLLMSettingsRead(BaseModel):
    """Sanitized snapshot of the experimental local LLM config.

    The optional API key is **never** returned in plaintext; the UI sees
    ``has_api_key`` plus a masked preview. ``task_policy`` carries the
    static risk metadata so the UI can label high-risk tasks.
    """

    enabled: bool
    provider: str
    base_url: str
    model: str
    # ``timeout_seconds`` is the user's explicit choice (``null`` when unset);
    # ``effective_timeout_seconds`` is the provider-aware value in force for
    # each local call (Ollama defaults to 180s, others 60s; task 130).
    timeout_seconds: int | None
    effective_timeout_seconds: int
    allowed_tasks: dict[str, bool]
    context_window_tokens: int
    reserved_output_tokens: int
    max_input_tokens: int
    num_ctx: int | None
    # Optional per-call output-token cap sent to the server as the
    # provider-native field (``num_predict`` for Ollama-native, ``max_tokens``
    # for OpenAI-compatible); ``null`` leaves the server at its own limit
    # (task 140).
    max_output_tokens: int | None
    # Reasoning control: ``strip_thinking`` (default), ``hide_thinking``, or
    # ``no_thinking`` (task 131).
    thinking_mode: str
    allow_compression: bool
    allow_fallback: bool
    abort_on_over_budget: bool
    has_api_key: bool
    api_key_preview: str
    updated_at: str | None
    task_policy: list[LocalLLMTaskPolicy]


class LocalLLMSettingsUpdate(BaseModel):
    """Request body for ``PUT /settings/local-llm``.

    ``api_key`` may be omitted; with ``preserve_existing_key`` set, any
    previously stored key is retained on update.
    """

    enabled: bool = False
    provider: str = local_llm.PROVIDER_OPENAI_COMPATIBLE
    base_url: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    # Omitted/``null`` means "not explicitly configured": the effective timeout
    # is then resolved provider-aware (Ollama 180s, others 60s; task 130).
    timeout_seconds: int | None = None
    allowed_tasks: dict[str, bool] = Field(default_factory=dict)
    context_window_tokens: int = local_llm.DEFAULT_CONTEXT_WINDOW_TOKENS
    reserved_output_tokens: int = local_llm.DEFAULT_RESERVED_OUTPUT_TOKENS
    max_input_tokens: int | None = None
    num_ctx: int | None = None
    # Optional output-token cap; ``None`` sends no cap (task 140).
    max_output_tokens: int | None = None
    # Omitted means the safe default (strip thinking before JSON parsing);
    # an unrecognized value is rejected by ``save_config`` (task 131).
    thinking_mode: str = local_llm.DEFAULT_THINKING_MODE
    allow_compression: bool = local_llm.DEFAULT_ALLOW_COMPRESSION
    allow_fallback: bool = local_llm.DEFAULT_ALLOW_FALLBACK
    abort_on_over_budget: bool = local_llm.DEFAULT_ABORT_ON_OVER_BUDGET
    api_key: str | None = None
    preserve_existing_key: bool = False


@router.get("/local-llm", response_model=LocalLLMSettingsRead)
def read_local_llm_settings() -> LocalLLMSettingsRead:
    return LocalLLMSettingsRead(**local_llm.get_settings_view())


@router.put("/local-llm", response_model=LocalLLMSettingsRead)
def update_local_llm_settings(
    payload: LocalLLMSettingsUpdate,
) -> LocalLLMSettingsRead:
    try:
        local_llm.save_config(
            enabled=payload.enabled,
            provider=payload.provider,
            base_url=payload.base_url,
            model=payload.model,
            timeout_seconds=payload.timeout_seconds,
            allowed_tasks=payload.allowed_tasks,
            context_window_tokens=payload.context_window_tokens,
            reserved_output_tokens=payload.reserved_output_tokens,
            max_input_tokens=payload.max_input_tokens,
            num_ctx=payload.num_ctx,
            max_output_tokens=payload.max_output_tokens,
            thinking_mode=payload.thinking_mode,
            allow_compression=payload.allow_compression,
            allow_fallback=payload.allow_fallback,
            abort_on_over_budget=payload.abort_on_over_budget,
            api_key=payload.api_key,
            preserve_existing_key=payload.preserve_existing_key,
        )
    except local_llm.LocalLLMValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LocalLLMSettingsRead(**local_llm.get_settings_view())


@router.delete("/local-llm", response_model=LocalLLMSettingsRead)
def delete_local_llm_settings() -> LocalLLMSettingsRead:
    local_llm.delete_config()
    return LocalLLMSettingsRead(**local_llm.get_settings_view())


# ---- Exports folder (task 122) ---------------------------------------


class ExportSettingsRead(BaseModel):
    """The app-managed exports folder shown on the Settings page.

    First implementation is read-only: the app owns
    ``candidate_context/exports/`` and surfaces the resolved path so the
    user knows where exported resumes land. ``path`` is project-relative
    when the folder lives under the project, else an absolute path.
    """

    path: str


@router.get("/exports", response_model=ExportSettingsRead)
def read_export_settings() -> ExportSettingsRead:
    return ExportSettingsRead(path=project_relative_path(default_exports_root()))


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
