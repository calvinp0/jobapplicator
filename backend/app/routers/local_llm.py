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

import logging
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, HTTPException
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
    context_window_tokens: int
    max_input_tokens: int


@router.post("/test-connection", response_model=LocalLLMTestResult)
def test_local_llm_connection(
    payload: LocalLLMTestRequest | None = None,
) -> LocalLLMTestResult:
    """Send a minimal prompt to the configured local endpoint."""
    payload = payload or LocalLLMTestRequest()
    config = local_llm.get_config()

    # Overlay any provided overrides onto the stored config.
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
    incoming_key = (payload.api_key or "").strip()
    if incoming_key:
        overrides["api_key"] = incoming_key
    elif not payload.preserve_existing_key:
        overrides["api_key"] = None

    config = replace(config, **overrides)
    budget = config.context_budget

    client = local_llm.LocalLLMClient(config)
    result = client.test_connection()
    if result.ok:
        message = (
            "Connected — model responded. "
            f"Configured context window: {budget.context_window_tokens} tokens. "
            f"Usable input budget: {budget.max_input_tokens} tokens."
        )
    else:
        message = "Connection failed."
    return LocalLLMTestResult(
        ok=result.ok,
        message=message,
        model=result.model,
        provider=result.provider,
        latency_ms=result.latency_ms,
        error=result.error,
        context_window_tokens=budget.context_window_tokens,
        max_input_tokens=budget.max_input_tokens,
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
