"""Experimental local LLM operational endpoints (task 123).

The persisted config lives under ``/settings/local-llm`` (see
:mod:`app.routers.settings`). This router hosts the *operational* surface:
a connection test and a small, bounded, experimental resume-suggestions
endpoint. Both honor the task policy in :mod:`app.local_llm` — the
suggestions endpoint refuses to run when the user has not opted the local
provider into the ``resume_suggestions`` task.

Nothing here drives the high-risk ``auto`` resume-tailoring flow; that
remains a Claude Code (CLI) concern per ADR-009. These endpoints never
overwrite a stored resume — they return suggestions for the user to
review.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import local_llm


router = APIRouter(prefix="/llm/local", tags=["local-llm"])
logger = logging.getLogger(__name__)


# ---- Test connection -------------------------------------------------


class LocalLLMTestRequest(BaseModel):
    """Optional overrides for a connection test.

    Any field left unset falls back to the persisted config, so the UI can
    test either the saved settings or unsaved edits. ``preserve_existing_key``
    defaults to true so a test of unsaved edits still uses the stored key.
    """

    base_url: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    context_window_tokens: int | None = None
    reserved_output_tokens: int | None = None
    max_input_tokens: int | None = None
    num_ctx: int | None = None
    api_key: str | None = None
    provider: str | None = None
    preserve_existing_key: bool = True


class LocalLLMTestResult(BaseModel):
    ok: bool
    message: str
    model: str
    provider: str
    latency_ms: int | None = None
    error: str | None = None
    # Connection-error classification (task 136). ``error_kind`` is a stable
    # machine value: ``none`` on success, else ``endpoint_unavailable``,
    # ``bad_url``, ``model_not_installed``, or ``unexpected``. ``installed_models``
    # lists the models the server reports installed (Ollama-native only; empty
    # for the OpenAI-compatible surface, which cannot list models).
    error_kind: str | None = None
    installed_models: list[str] = Field(default_factory=list)
    context_window_tokens: int
    max_input_tokens: int
    # Server-context detection (task 127). ``server_reported_context_tokens``
    # is the model server's own context length when it could be read (Ollama
    # only); ``context_verified`` is true only when that read succeeded;
    # ``context_warning`` explains why the context could not be verified.
    server_reported_context_tokens: int | None = None
    context_verified: bool = False
    context_warning: str | None = None


def _config_with_overrides(
    config: local_llm.LocalLLMConfig, payload: LocalLLMTestRequest
) -> local_llm.LocalLLMConfig:
    """Overlay any provided request overrides onto the stored config.

    Shared by the connection-test and model-listing endpoints so the UI can
    operate on unsaved edits with one consistent override rule. A field left
    unset falls back to the persisted config; an empty API key keeps the
    stored key unless ``preserve_existing_key`` is false.
    """
    overrides: dict[str, Any] = {}
    if payload.base_url is not None:
        overrides["base_url"] = payload.base_url.strip()
    if payload.model is not None:
        overrides["model"] = payload.model.strip()
    if payload.timeout_seconds is not None:
        overrides["timeout_seconds"] = payload.timeout_seconds
    if payload.provider is not None:
        overrides["provider"] = payload.provider.strip()
    if payload.context_window_tokens is not None:
        overrides["context_window_tokens"] = payload.context_window_tokens
    if payload.reserved_output_tokens is not None:
        overrides["reserved_output_tokens"] = payload.reserved_output_tokens
    if payload.max_input_tokens is not None:
        overrides["max_input_tokens"] = payload.max_input_tokens
    elif (
        payload.context_window_tokens is not None
        or payload.reserved_output_tokens is not None
    ):
        overrides["max_input_tokens"] = None
    if payload.num_ctx is not None:
        overrides["num_ctx"] = payload.num_ctx
    incoming_key = (payload.api_key or "").strip()
    if incoming_key:
        overrides["api_key"] = incoming_key
    elif not payload.preserve_existing_key:
        overrides["api_key"] = None

    return replace(config, **overrides)


@router.post("/test-connection", response_model=LocalLLMTestResult)
def test_local_llm_connection(
    payload: LocalLLMTestRequest | None = None,
) -> LocalLLMTestResult:
    """Send a minimal prompt to the configured local endpoint."""
    payload = payload or LocalLLMTestRequest()
    config = local_llm.get_config()
    config = _config_with_overrides(config, payload)
    budget = config.context_budget

    client = local_llm.LocalLLMClient(config)
    # Diagnose *why* a test fails instead of echoing a raw transport error: for
    # the Ollama-native provider this lists installed models first (so a missing
    # model is reported as such, not as a 404) and classifies every failure into
    # a stable ``error_kind`` (task 136).
    diagnosis = client.diagnose_connection()

    # Best-effort: ask the server what context it is actually running. This
    # never raises — an unreachable or OpenAI-compatible server degrades to
    # ``context_verified = False`` with an explanatory warning.
    detection = local_llm.detect_server_context(config)

    if diagnosis.ok:
        message = (
            "Connected — model responded. "
            f"Configured context window: {budget.context_window_tokens} tokens. "
            f"Usable input budget: {budget.max_input_tokens} tokens."
        )
        if detection.context_verified:
            message += (
                " Server-reported context: "
                f"{detection.server_reported_context_tokens} tokens."
            )
    else:
        # The diagnosis message already reflects the classified failure class
        # (endpoint unavailable / wrong URL / model not installed).
        message = diagnosis.message
    return LocalLLMTestResult(
        ok=diagnosis.ok,
        message=message,
        model=diagnosis.model,
        provider=diagnosis.provider,
        latency_ms=diagnosis.latency_ms,
        error=diagnosis.error,
        error_kind=diagnosis.error_kind,
        installed_models=diagnosis.installed_models,
        context_window_tokens=budget.context_window_tokens,
        max_input_tokens=budget.max_input_tokens,
        server_reported_context_tokens=detection.server_reported_context_tokens,
        context_verified=detection.context_verified,
        context_warning=(
            None if detection.context_verified else detection.note
        ),
    )


# ---- List installed models (task 135) --------------------------------


class LocalLLMModelsResult(BaseModel):
    """Installed-model listing for a local endpoint.

    ``ok`` is true only when the listing actually succeeded; ``models`` is the
    list of installed model names (empty otherwise). ``error`` / ``error_kind``
    explain a failure or that the OpenAI-compatible surface does not support
    model listing (``error_kind == "unsupported"``).
    """

    provider: str
    ok: bool
    models: list[str]
    error: str | None = None
    error_kind: str | None = None


@router.get("/models", response_model=LocalLLMModelsResult)
def list_local_llm_models(
    base_url: str | None = None,
    provider: str | None = None,
) -> LocalLLMModelsResult:
    """List the models installed on the configured local endpoint.

    Installed-model detection is **Ollama-native only** (it queries the native
    ``/api/tags`` endpoint). Optional ``base_url`` / ``provider`` query
    overrides let the UI list models for unsaved edits, mirroring the
    test-connection override rule. Transport failures and the unsupported
    OpenAI-compatible surface are reported via ``error`` / ``error_kind``
    rather than raising.
    """
    config = local_llm.get_config()
    config = _config_with_overrides(
        config, LocalLLMTestRequest(base_url=base_url, provider=provider)
    )
    result = local_llm.LocalLLMClient(config).list_models()
    return LocalLLMModelsResult(
        provider=result.provider,
        ok=result.ok,
        models=result.models,
        error=result.error,
        error_kind=result.error_kind,
    )


# ---- Explicit model pull (task 137) ----------------------------------


class LocalLLMPullRequest(BaseModel):
    """Request body for an explicit, operator-initiated model pull.

    ``model`` is **required** — there is no "pull whatever is configured"
    behaviour; the caller must name the model to install. Optional
    ``provider`` / ``base_url`` / ``api_key`` overrides mirror the
    test-connection rule so the UI can pull against unsaved edits, and the
    refusal for a non-Ollama provider is evaluated against the resolved
    (overridden) config.
    """

    model: str = Field(..., min_length=1)
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    preserve_existing_key: bool = True


def _pull_event_stream(
    client: local_llm.LocalLLMClient, model: str
) -> Iterator[bytes]:
    """Yield the newline-delimited JSON (NDJSON) progress stream for a pull.

    The shape is documented in ``docs/llm_providers.md``. Three event types,
    one JSON object per line:

    - ``{"type": "advisory", "model", "provider", "message"}`` — emitted first;
      ``message`` is the disk/VRAM-unknown advisory.
    - ``{"type": "progress", "status", "completed", "total", "digest"}`` — one
      per streamed progress update from the server.
    - ``{"type": "result", "ok", "error", "error_kind"}`` — emitted last;
      summarises whether the pull succeeded.

    This is a sync generator, so Starlette iterates it in a threadpool and the
    blocking pull never stalls the event loop.
    """
    advisory = {
        "type": "advisory",
        "model": model,
        "provider": client.provider_id,
        "message": local_llm.PULL_DISK_VRAM_ADVISORY,
    }
    yield (json.dumps(advisory) + "\n").encode("utf-8")

    error: str | None = None
    error_kind: str | None = None
    try:
        for progress in client.iter_pull_model(model):
            event = {
                "type": "progress",
                "status": progress.status,
                "completed": progress.completed,
                "total": progress.total,
                "digest": progress.digest,
            }
            yield (json.dumps(event) + "\n").encode("utf-8")
            if progress.error and error is None:
                error = progress.error
                error_kind = local_llm.ENDPOINT_ERROR_UNEXPECTED
    except Exception as exc:  # noqa: BLE001 - classified into the result line
        error_kind, error = local_llm.classify_endpoint_error(
            exc, base_url=client.config.base_url
        )

    result = {
        "type": "result",
        "ok": error is None,
        "error": error,
        "error_kind": error_kind,
    }
    yield (json.dumps(result) + "\n").encode("utf-8")


@router.post("/pull")
def pull_local_llm_model(payload: LocalLLMPullRequest) -> StreamingResponse:
    """Explicitly pull (install) a model on the configured Ollama server.

    This is the **only** path that triggers a model pull — pulling never
    happens as a side effect of test-connection, preflight, tailoring, or
    startup. The UI (task 139) is responsible for gating it behind a
    confirmation dialog.

    The model name is required in the body. Pulling is **Ollama-native only**:
    the endpoint refuses (HTTP 409) unless the persisted provider is Ollama or
    an explicit ``provider=ollama`` override is supplied. On the happy path it
    returns an NDJSON progress stream (see :func:`_pull_event_stream`) whose
    first line is an advisory that the backend cannot verify the model will fit
    the host's disk/VRAM.
    """
    model = payload.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="A model name is required.")

    config = local_llm.get_config()
    config = _config_with_overrides(
        config,
        LocalLLMTestRequest(
            base_url=payload.base_url,
            provider=payload.provider,
            api_key=payload.api_key,
            preserve_existing_key=payload.preserve_existing_key,
        ),
    )
    if config.provider != local_llm.PROVIDER_OLLAMA:
        raise HTTPException(
            status_code=409,
            detail=(
                "Pulling a model is only supported for the Ollama-native "
                "provider. Select the Ollama provider (or pass "
                "provider=ollama) to install a model."
            ),
        )

    client = local_llm.LocalLLMClient(config)
    return StreamingResponse(
        _pull_event_stream(client, model),
        media_type="application/x-ndjson",
        headers={
            # Surface the disk/VRAM advisory on the response itself, so a
            # client that does not parse the stream still sees the warning.
            "X-Pull-Advisory": local_llm.PULL_DISK_VRAM_ADVISORY,
        },
    )


# ---- Experimental resume suggestions ---------------------------------

class SuggestResumeEditsRequest(BaseModel):
    job_description: str = Field(..., min_length=1)
    resume_excerpt: str = Field(..., min_length=1)
    max_suggestions: int = Field(default=5, ge=1, le=20)


class SuggestResumeEditsResult(BaseModel):
    experimental: bool
    provider: str
    model: str
    schema_valid: bool
    fallback_used: bool
    suggestions: list[dict[str, Any]]
    error: str | None = None


@router.post("/suggest-resume-edits", response_model=SuggestResumeEditsResult)
def suggest_resume_edits(
    payload: SuggestResumeEditsRequest,
) -> SuggestResumeEditsResult:
    """Experimental: draft bounded resume-edit suggestions locally.

    Refuses to run unless the user has enabled the local provider for the
    ``resume_suggestions`` task. Output is marked experimental, schema is
    validated, and nothing is written to any stored resume — the user
    reviews the suggestions.
    """
    config = local_llm.get_config()
    if not local_llm.local_allowed_for_task(
        local_llm.TASK_RESUME_SUGGESTIONS, config
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Local LLM is not enabled for resume suggestions. Enable it "
                "under Settings → LLM Providers (experimental)."
            ),
        )

    job, job_compressed = _compact_text_for_resume_suggestions(
        payload.job_description, max_chars=4000
    )
    resume, resume_compressed = _compact_text_for_resume_suggestions(
        payload.resume_excerpt, max_chars=4000
    )
    if job_compressed or resume_compressed:
        logger.info(
            "jobapply: deterministic compression used for local resume_suggestions input"
        )
    system = (
        "You are an assistant that proposes small, evidence-grounded resume "
        "edits. Only suggest changes supported by the candidate's existing "
        "resume text — never invent experience, employers, dates, or metrics. "
        "Respond with a single JSON object."
    )
    user = (
        "Job description:\n"
        f"{job}\n\n"
        "Candidate resume excerpt:\n"
        f"{resume}\n\n"
        f"Propose up to {payload.max_suggestions} suggestions. Reply with a "
        'JSON object of the form {"suggestions": [{"target": "...", '
        '"suggestion": "...", "rationale": "..."}]}. Each suggestion must be '
        "supported by the resume excerpt."
    )

    client = local_llm.LocalLLMClient(config)
    result = client.chat_json(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        required_fields=["suggestions"],
        task=local_llm.TASK_RESUME_SUGGESTIONS,
    )

    suggestions: list[dict[str, Any]] = []
    if result.schema_valid and isinstance(result.parsed, dict):
        raw = result.parsed.get("suggestions")
        if isinstance(raw, list):
            suggestions = [s for s in raw if isinstance(s, dict)][
                : payload.max_suggestions
            ]

    return SuggestResumeEditsResult(
        experimental=True,
        provider=result.provider,
        model=result.model,
        schema_valid=bool(result.schema_valid),
        fallback_used=result.fallback_used,
        suggestions=suggestions,
        error=result.error,
    )


def _compact_text_for_resume_suggestions(
    text: str, *, max_chars: int
) -> tuple[str, bool]:
    """Named deterministic compression for experimental suggestion inputs."""
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(normalized) <= max_chars:
        return normalized, False
    head = normalized[: max_chars // 2].rsplit("\n", 1)[0]
    tail = normalized[-(max_chars // 2) :].split("\n", 1)[-1]
    return (
        f"{head}\n\n"
        "[deterministic compression: middle omitted for local LLM budget]\n\n"
        f"{tail}"
    ).strip(), True
