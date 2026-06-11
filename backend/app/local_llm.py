"""Experimental local LLM provider support (task 123).

This module is deliberately *separate* from the CLI provider registry in
:mod:`app.llm_providers`. ADR-009 scopes that registry to CLI workers that
drive the high-risk ``auto`` resume-tailoring flow and explicitly excludes
hosted/HTTP-API providers. The local LLM here is an opt-in, experimental
subsystem for *low-risk* tasks (job-description summary, ATS keyword
extraction, email classification, and — experimentally — resume
suggestions). It must never silently take over full resume tailoring,
claim auditing, or recruiter review; Claude Code remains the default for
those (see :data:`TASK_RISK` and :func:`local_allowed_for_task`).

The subsystem has three parts:

1. **Config + persistence** — a :class:`LocalLLMConfig` stored as JSON in
   the existing :class:`~app.models.AppSetting` key/value table, mirroring
   the masking pattern from :mod:`app.gmail_settings` so an optional API
   key never leaves the backend in plaintext.
2. **Task policy** — :func:`local_allowed_for_task` and friends decide,
   for each task, whether the local provider may run it. High-risk tasks
   default to Claude Code and require an explicit per-task opt-in.
3. **Client** — :class:`LocalLLMClient`, a tiny OpenAI-compatible chat
   client built on the standard library (``urllib``) with JSON-schema
   validation and a single repair retry. No new dependency is added.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .context_budget import (
    ContextBudget,
    build_context_budget,
    check_context_budget,
)
from .db import SessionLocal
from .llm_providers import CLAUDE_CODE_PROVIDER_ID
from .models import AppSetting


logger = logging.getLogger(__name__)


LOCAL_LLM_SETTING_KEY = "local_llm_config"

API_KEY_PREVIEW_MASK = "•" * 8  # 8 bullets, matches gmail_settings

# Supported local provider modes. ``openai_compatible`` covers most local
# servers (vLLM, LM Studio, llama.cpp's server, and Ollama's ``/v1``
# OpenAI-compatible surface); it speaks ``POST {base_url}/chat/completions``.
# ``ollama`` is the native-Ollama mode and speaks ``POST {base_url}/api/chat``
# at the server root — the two providers use different endpoints and request
# shapes (task 129).
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_OLLAMA = "ollama"
SUPPORTED_PROVIDER_MODES = (PROVIDER_OPENAI_COMPATIBLE, PROVIDER_OLLAMA)

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT_SECONDS = 60
# Ollama-native models often pay a large first-token / model-load cost on a
# cold start, so a freshly loaded model can take well over a minute to answer
# the first preflight task. The 60s default cuts those off and silently forces
# the deterministic fallback on every run, making the local provider look
# "broken" when it is merely cold. When the user has *not* explicitly
# configured a timeout, the Ollama-native provider therefore gets a longer
# default; an explicit user value always overrides it (task 130).
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 180
DEFAULT_CONTEXT_WINDOW_TOKENS = 8192
DEFAULT_RESERVED_OUTPUT_TOKENS = 1200
DEFAULT_MAX_INPUT_TOKENS = 6500
DEFAULT_ALLOW_COMPRESSION = True
DEFAULT_ALLOW_FALLBACK = True
DEFAULT_ABORT_ON_OVER_BUDGET = False


# ---- Task policy -----------------------------------------------------
#
# Task ids are the canonical strings recorded in run metadata. The risk
# tier controls the *default* config and whether a task is configurable at
# all. Defaults keep every high-risk output on Claude Code; the user must
# deliberately opt a high-risk task into the local provider.

TASK_JOB_SUMMARY = "job_summary"
TASK_ATS_KEYWORDS = "ats_keywords"
# Task 124 added two more low-risk preflight extraction tasks routed by the
# same policy: structured role-requirement extraction and an (advisory,
# JD-only-first-pass) evidence gap plan. Both are bounded classification work
# that is safe to run locally, so they share the ``low`` risk tier.
TASK_ROLE_REQUIREMENTS = "role_requirements"
TASK_EVIDENCE_GAP_PLAN = "evidence_gap_plan"
TASK_EMAIL_CLASSIFICATION = "email_classification"
TASK_RESUME_SUGGESTIONS = "resume_suggestions"
TASK_RESUME_TAILORING = "resume_tailoring"
TASK_CLAIM_AUDIT = "claim_audit"
TASK_RECRUITER_REVIEW = "recruiter_review"

RISK_LOW = "low"
RISK_EXPERIMENTAL = "experimental"
RISK_HIGH = "high"
RISK_CLAUDE_ONLY = "claude_only"

# Every task the policy knows about, with its risk tier. ``recruiter_review``
# is intentionally *not* configurable: it is always Claude Code.
TASK_RISK: dict[str, str] = {
    TASK_JOB_SUMMARY: RISK_LOW,
    TASK_ATS_KEYWORDS: RISK_LOW,
    TASK_ROLE_REQUIREMENTS: RISK_LOW,
    TASK_EVIDENCE_GAP_PLAN: RISK_LOW,
    TASK_EMAIL_CLASSIFICATION: RISK_LOW,
    TASK_RESUME_SUGGESTIONS: RISK_EXPERIMENTAL,
    TASK_RESUME_TAILORING: RISK_HIGH,
    TASK_CLAIM_AUDIT: RISK_HIGH,
    TASK_RECRUITER_REVIEW: RISK_CLAUDE_ONLY,
}

# The tasks that appear as user-toggleable checkboxes in Settings. Order is
# stable so the UI and the persisted dict line up. ``recruiter_review`` is
# excluded — it is Claude-only and not a toggle.
CONFIGURABLE_TASKS: tuple[str, ...] = (
    TASK_JOB_SUMMARY,
    TASK_ATS_KEYWORDS,
    TASK_ROLE_REQUIREMENTS,
    TASK_EVIDENCE_GAP_PLAN,
    TASK_EMAIL_CLASSIFICATION,
    TASK_RESUME_SUGGESTIONS,
    TASK_RESUME_TAILORING,
    TASK_CLAIM_AUDIT,
)

# Default per-task toggles: low-risk tasks on, everything else off. Note the
# subsystem also has a master ``enabled`` switch (default off), so nothing
# runs locally until the user turns the whole thing on.
DEFAULT_ALLOWED_TASKS: dict[str, bool] = {
    TASK_JOB_SUMMARY: True,
    TASK_ATS_KEYWORDS: True,
    TASK_ROLE_REQUIREMENTS: True,
    TASK_EVIDENCE_GAP_PLAN: True,
    TASK_EMAIL_CLASSIFICATION: True,
    TASK_RESUME_SUGGESTIONS: False,
    TASK_RESUME_TAILORING: False,
    TASK_CLAIM_AUDIT: False,
}


class LocalLLMValidationError(ValueError):
    """Raised when an attempt to persist an invalid local LLM config is made."""


@dataclass(frozen=True)
class LocalLLMConfig:
    """The persisted local LLM configuration.

    ``api_key`` is the plaintext key (or ``None``); it stays inside the
    backend and is never returned by :func:`get_settings_view`.
    """

    enabled: bool = False
    provider: str = PROVIDER_OPENAI_COMPATIBLE
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    # Whether ``timeout_seconds`` was explicitly chosen by the user. When
    # False the effective per-call timeout is resolved provider-aware via
    # :attr:`effective_timeout_seconds` (Ollama gets 180s; other providers
    # keep 60s) without baking that default into the stored value. This flag
    # is persisted *implicitly*: ``timeout_seconds`` is stored as ``null`` in
    # the settings JSON when unset and as an integer when explicit, so no new
    # stored field name is introduced (task 130).
    timeout_explicitly_set: bool = False
    allowed_tasks: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_ALLOWED_TASKS)
    )
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS
    max_input_tokens: Optional[int] = DEFAULT_MAX_INPUT_TOKENS
    # Optional running context length to request from an Ollama server
    # (``options.num_ctx``). ``None`` means "do not request a specific server
    # context; leave the server at its own default". This is independent of
    # ``context_window_tokens``: it configures the *model server*, not
    # JobApplicator's prompt budget, and only applies to the Ollama-native
    # provider (task 126).
    num_ctx: Optional[int] = None
    allow_compression: bool = DEFAULT_ALLOW_COMPRESSION
    allow_fallback: bool = DEFAULT_ALLOW_FALLBACK
    abort_on_over_budget: bool = DEFAULT_ABORT_ON_OVER_BUDGET
    api_key: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def context_budget(self) -> ContextBudget:
        return build_context_budget(
            self.context_window_tokens,
            self.reserved_output_tokens,
            self.max_input_tokens,
        )

    @property
    def effective_timeout_seconds(self) -> int:
        """The per-call timeout (seconds) actually applied to a local call.

        An explicit user-configured timeout always wins. Otherwise the
        Ollama-native provider uses a longer default (180s) to absorb a cold
        model's first-token / load latency, while the OpenAI-compatible
        provider keeps the 60s default (task 130).
        """
        if self.timeout_explicitly_set:
            return self.timeout_seconds
        if self.provider == PROVIDER_OLLAMA:
            return DEFAULT_OLLAMA_TIMEOUT_SECONDS
        return self.timeout_seconds


def default_config() -> LocalLLMConfig:
    """Return the documented defaults for a fresh install."""
    return LocalLLMConfig(allowed_tasks=dict(DEFAULT_ALLOWED_TASKS))


def _normalize_allowed_tasks(raw: Any) -> dict[str, bool]:
    """Coerce a stored/incoming allowed-tasks mapping to the known shape.

    Unknown keys are dropped and missing keys fall back to their default,
    so the persisted toggles always match :data:`CONFIGURABLE_TASKS`.
    """
    result = dict(DEFAULT_ALLOWED_TASKS)
    if isinstance(raw, dict):
        for task in CONFIGURABLE_TASKS:
            if task in raw:
                result[task] = bool(raw[task])
    return result


def _local_provider_label(config: LocalLLMConfig) -> str:
    """Stable provider id recorded in metadata for local runs."""
    if config.provider == PROVIDER_OLLAMA:
        return "local_ollama"
    return "local_openai_compatible"


# ---- Persistence -----------------------------------------------------


def _load_row() -> Optional[dict[str, Any]]:
    with SessionLocal() as session:
        row = session.get(AppSetting, LOCAL_LLM_SETTING_KEY)
        if row is None:
            return None
        try:
            data = json.loads(row.value)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data


def get_config() -> LocalLLMConfig:
    """Return the persisted config, or documented defaults when unset."""
    raw = _load_row()
    if raw is None:
        return default_config()
    api_key = raw.get("api_key") or None
    # ``num_ctx`` is optional: missing, null, or a non-integer value all mean
    # "leave the server at its own default" (task 126).
    raw_num_ctx = raw.get("num_ctx")
    try:
        num_ctx = int(raw_num_ctx) if raw_num_ctx is not None else None
    except (TypeError, ValueError):
        num_ctx = None
    # ``timeout_seconds`` is optional: a missing, null, or non-integer stored
    # value means "not explicitly configured", so the effective timeout is
    # resolved provider-aware at read time. A stored integer is an explicit
    # user choice that is honoured verbatim (task 130).
    raw_timeout = raw.get("timeout_seconds")
    if raw_timeout is None:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        timeout_explicitly_set = False
    else:
        try:
            timeout_seconds = int(raw_timeout)
            timeout_explicitly_set = True
        except (TypeError, ValueError):
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS
            timeout_explicitly_set = False
    return LocalLLMConfig(
        enabled=bool(raw.get("enabled", False)),
        provider=raw.get("provider") or PROVIDER_OPENAI_COMPATIBLE,
        base_url=raw.get("base_url") or DEFAULT_BASE_URL,
        model=raw.get("model") or DEFAULT_MODEL,
        timeout_seconds=timeout_seconds,
        timeout_explicitly_set=timeout_explicitly_set,
        allowed_tasks=_normalize_allowed_tasks(raw.get("allowed_tasks")),
        context_window_tokens=int(
            raw.get("context_window_tokens") or DEFAULT_CONTEXT_WINDOW_TOKENS
        ),
        reserved_output_tokens=int(
            raw.get("reserved_output_tokens") or DEFAULT_RESERVED_OUTPUT_TOKENS
        ),
        max_input_tokens=(
            int(raw["max_input_tokens"])
            if raw.get("max_input_tokens") is not None
            else None
        ),
        num_ctx=num_ctx,
        allow_compression=bool(
            raw.get("allow_compression", DEFAULT_ALLOW_COMPRESSION)
        ),
        allow_fallback=bool(raw.get("allow_fallback", DEFAULT_ALLOW_FALLBACK)),
        abort_on_over_budget=bool(
            raw.get("abort_on_over_budget", DEFAULT_ABORT_ON_OVER_BUDGET)
        ),
        api_key=api_key,
        updated_at=raw.get("updated_at"),
    )


def save_config(
    *,
    enabled: bool,
    provider: str,
    base_url: str,
    model: str,
    timeout_seconds: Optional[int] = None,
    allowed_tasks: dict[str, bool],
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
    max_input_tokens: Optional[int] = DEFAULT_MAX_INPUT_TOKENS,
    num_ctx: Optional[int] = None,
    allow_compression: bool = DEFAULT_ALLOW_COMPRESSION,
    allow_fallback: bool = DEFAULT_ALLOW_FALLBACK,
    abort_on_over_budget: bool = DEFAULT_ABORT_ON_OVER_BUDGET,
    api_key: Optional[str] = None,
    preserve_existing_key: bool = False,
) -> LocalLLMConfig:
    """Validate and persist the local LLM config.

    Raises :class:`LocalLLMValidationError` for invalid input. When
    ``preserve_existing_key`` is true and no new ``api_key`` is supplied,
    the previously stored key is retained. The plaintext key is never
    logged.
    """
    provider = (provider or "").strip() or PROVIDER_OPENAI_COMPATIBLE
    if provider not in SUPPORTED_PROVIDER_MODES:
        raise LocalLLMValidationError(
            f"unsupported provider {provider!r}; supported: "
            + ", ".join(SUPPORTED_PROVIDER_MODES)
        )

    base_url = (base_url or "").strip()
    if not base_url:
        raise LocalLLMValidationError("base_url is required")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise LocalLLMValidationError(
            "base_url must start with http:// or https://"
        )

    model = (model or "").strip()
    if not model:
        raise LocalLLMValidationError("model is required")

    # ``timeout_seconds`` is optional: ``None`` records "not explicitly
    # configured" (stored as null) so the effective timeout is resolved
    # provider-aware at read time without overwriting the stored value. A
    # supplied value must be a positive integer and is honoured verbatim for
    # every provider (task 130).
    if timeout_seconds is None:
        timeout_int: Optional[int] = None
    else:
        try:
            timeout_int = int(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise LocalLLMValidationError(
                "timeout_seconds must be an integer"
            ) from exc
        if timeout_int <= 0:
            raise LocalLLMValidationError("timeout_seconds must be positive")

    normalized_tasks = _normalize_allowed_tasks(allowed_tasks)
    try:
        budget = build_context_budget(
            context_window_tokens,
            reserved_output_tokens,
            max_input_tokens,
        )
    except ValueError as exc:
        raise LocalLLMValidationError(str(exc)) from exc

    # ``num_ctx`` is validated independently of the context budget: it
    # configures the Ollama server's running context, not JobApplicator's
    # prompt budget. When present it must be a positive integer (task 126).
    if num_ctx is not None:
        try:
            num_ctx = int(num_ctx)
        except (TypeError, ValueError) as exc:
            raise LocalLLMValidationError(
                "num_ctx must be a positive integer"
            ) from exc
        if num_ctx <= 0:
            raise LocalLLMValidationError("num_ctx must be a positive integer")

    # Resolve the API key: an empty incoming key with preserve flag keeps
    # whatever was previously stored.
    incoming_key = (api_key or "").strip() or None
    if incoming_key is None and preserve_existing_key:
        existing = get_config()
        incoming_key = existing.api_key

    updated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "enabled": bool(enabled),
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "timeout_seconds": timeout_int,
        "allowed_tasks": normalized_tasks,
        "context_window_tokens": budget.context_window_tokens,
        "reserved_output_tokens": budget.reserved_output_tokens,
        "max_input_tokens": budget.max_input_tokens,
        "num_ctx": num_ctx,
        "allow_compression": bool(allow_compression),
        "allow_fallback": bool(allow_fallback),
        "abort_on_over_budget": bool(abort_on_over_budget),
        "api_key": incoming_key,
        "updated_at": updated_at,
    }
    serialized = json.dumps(payload, sort_keys=True)
    with SessionLocal() as session:
        row = session.get(AppSetting, LOCAL_LLM_SETTING_KEY)
        if row is None:
            row = AppSetting(key=LOCAL_LLM_SETTING_KEY, value=serialized)
            session.add(row)
        else:
            row.value = serialized
        session.commit()

    return LocalLLMConfig(
        enabled=bool(enabled),
        provider=provider,
        base_url=base_url,
        model=model,
        timeout_seconds=(
            timeout_int if timeout_int is not None else DEFAULT_TIMEOUT_SECONDS
        ),
        timeout_explicitly_set=timeout_int is not None,
        allowed_tasks=normalized_tasks,
        context_window_tokens=budget.context_window_tokens,
        reserved_output_tokens=budget.reserved_output_tokens,
        max_input_tokens=budget.max_input_tokens,
        num_ctx=num_ctx,
        allow_compression=bool(allow_compression),
        allow_fallback=bool(allow_fallback),
        abort_on_over_budget=bool(abort_on_over_budget),
        api_key=incoming_key,
        updated_at=updated_at,
    )


def delete_config() -> bool:
    """Remove the persisted config. Returns ``True`` if a row existed."""
    with SessionLocal() as session:
        row = session.get(AppSetting, LOCAL_LLM_SETTING_KEY)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def task_policy_view() -> list[dict[str, Any]]:
    """Static per-task policy metadata for the Settings UI.

    ``configurable`` is false for Claude-only tasks (recruiter review),
    which the UI renders as informational rather than as a toggle.
    """
    view: list[dict[str, Any]] = []
    for task, risk in TASK_RISK.items():
        view.append(
            {
                "task": task,
                "risk": risk,
                "configurable": task in CONFIGURABLE_TASKS,
                "default_local": DEFAULT_ALLOWED_TASKS.get(task, False),
            }
        )
    return view


def get_settings_view() -> dict[str, Any]:
    """Return a sanitized snapshot for the GET endpoint and Settings UI.

    The plaintext API key is never returned; callers see ``has_api_key``
    and a masked preview.
    """
    config = get_config()
    budget = config.context_budget
    return {
        "enabled": config.enabled,
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        # ``timeout_seconds`` echoes the user's explicit choice (``None`` when
        # unset); ``effective_timeout_seconds`` is the provider-aware value
        # actually in force for each local call (task 130).
        "timeout_seconds": (
            config.timeout_seconds if config.timeout_explicitly_set else None
        ),
        "effective_timeout_seconds": config.effective_timeout_seconds,
        "allowed_tasks": dict(config.allowed_tasks),
        "context_window_tokens": budget.context_window_tokens,
        "reserved_output_tokens": budget.reserved_output_tokens,
        "max_input_tokens": budget.max_input_tokens,
        "num_ctx": config.num_ctx,
        "allow_compression": config.allow_compression,
        "allow_fallback": config.allow_fallback,
        "abort_on_over_budget": config.abort_on_over_budget,
        "has_api_key": bool(config.api_key),
        "api_key_preview": API_KEY_PREVIEW_MASK if config.api_key else "",
        "updated_at": config.updated_at,
        "task_policy": task_policy_view(),
    }


# ---- Task policy decisions -------------------------------------------


def local_allowed_for_task(task: str, config: Optional[LocalLLMConfig] = None) -> bool:
    """True when the local provider may run ``task`` under ``config``.

    The local provider is allowed only when (a) the subsystem is enabled,
    (b) the task is configurable (not Claude-only), and (c) the per-task
    toggle is on. High-risk tasks (resume tailoring, claim audit) default
    to off, so accidental local use is impossible without an explicit
    opt-in. ``recruiter_review`` is never allowed locally.
    """
    cfg = config if config is not None else get_config()
    if not cfg.enabled:
        return False
    if task not in CONFIGURABLE_TASKS:
        return False
    return bool(cfg.allowed_tasks.get(task, False))


def provider_for_task(task: str, config: Optional[LocalLLMConfig] = None) -> str:
    """Return the provider id that should run ``task``.

    Falls back to ``claude_code`` whenever the local provider is not
    permitted, which is the safe default for every high-risk output.
    """
    cfg = config if config is not None else get_config()
    if local_allowed_for_task(task, cfg):
        return _local_provider_label(cfg)
    return CLAUDE_CODE_PROVIDER_ID


def task_run_metadata(
    task: str, config: Optional[LocalLLMConfig] = None
) -> dict[str, Any]:
    """Provider/model metadata to stamp on a run record for ``task``.

    Mirrors the run-metadata shape in the task spec so callers can record
    which provider/model actually produced an artifact.
    """
    cfg = config if config is not None else get_config()
    provider = provider_for_task(task, cfg)
    is_local = provider != CLAUDE_CODE_PROVIDER_ID
    return {
        "task": task,
        "provider": provider,
        "model": cfg.model if is_local else "claude-code",
        "local_llm_enabled": cfg.enabled,
    }


# ---- Schema validation -----------------------------------------------


def validate_json_payload(
    content: Optional[str], required_fields: list[str]
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Parse ``content`` as a JSON object and check required fields.

    Returns ``(data, None)`` on success or ``(None, reason)`` on failure.
    """
    if not content:
        return None, "empty response"
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "expected a JSON object at the top level"
    missing = [f for f in required_fields if f not in data]
    if missing:
        return None, "missing required fields: " + ", ".join(missing)
    return data, None


def _repair_prompt(required_fields: list[str], reason: str) -> str:
    fields = ", ".join(required_fields)
    return (
        "Your previous reply was not valid. Reason: "
        f"{reason}. Reply again with ONLY a single JSON object containing "
        f"these required fields: {fields}. Do not include any prose, "
        "markdown fences, or explanation."
    )


# ---- Call result -----------------------------------------------------


@dataclass
class LLMCallResult:
    """Outcome of a local LLM call, including provenance for logging."""

    ok: bool
    provider: str
    model: str
    task: Optional[str] = None
    content: Optional[str] = None
    parsed: Optional[dict[str, Any]] = None
    schema_valid: Optional[bool] = None
    fallback_used: bool = False
    repaired: bool = False
    error: Optional[str] = None
    latency_ms: Optional[int] = None
    context: Optional[dict[str, Any]] = None


def _log_call(result: LLMCallResult) -> None:
    if result.schema_valid is None:
        schema = "n/a"
    else:
        schema = "passed" if result.schema_valid else "failed"
    logger.info(
        "LLM provider: %s | Model: %s | Task: %s | "
        "Schema validation: %s | Fallback used: %s",
        result.provider,
        result.model,
        result.task or "n/a",
        schema,
        "yes" if result.fallback_used else "no",
    )


# ---- HTTP layer (stdlib; monkeypatchable in tests) -------------------


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST ``payload`` as JSON to ``url`` and return the parsed response.

    Kept as a module-level function so tests can monkeypatch the network
    boundary without a live server.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _extract_content(body: dict[str, Any]) -> Optional[str]:
    # OpenAI-compatible shape: choices[0].message.content.
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
    # Ollama native /api/chat shape: top-level message.content (task 126).
    message = body.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return None


# ---- Server-context detection (task 127) -----------------------------


@dataclass(frozen=True)
class ServerContextResult:
    """Outcome of best-effort model-server context detection.

    ``server_reported_context_tokens`` is the running model's context length
    as reported by the server (or ``None`` when it could not be determined).
    ``context_verified`` is true only when the server actually reported a
    context length. ``note`` is a short human-readable explanation suitable
    for surfacing in the connection-test result or the preflight manifest.
    """

    server_reported_context_tokens: Optional[int]
    context_verified: bool
    note: str


def _ollama_show_url(base_url: str) -> str:
    """The native ``/api/show`` endpoint derived from ``base_url``.

    Mirrors :meth:`LocalLLMClient._ollama_native_chat_url`: Ollama's native
    metadata API lives at the server root, so a configured
    ``http://host:11434/v1`` resolves to ``http://host:11434/api/show``.
    """
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}/api/show"


def _extract_ollama_context_length(body: dict[str, Any]) -> Optional[int]:
    """Find the running model's context length in an ``/api/show`` response.

    Ollama reports model metadata under ``model_info`` with an
    architecture-prefixed key, e.g. ``llama.context_length`` or
    ``qwen2.context_length``. We accept any key ending in ``context_length``
    (and a bare top-level ``context_length`` some servers surface) and coerce
    the first positive integer value.
    """
    candidates: list[Any] = []
    model_info = body.get("model_info")
    if isinstance(model_info, dict):
        for key, value in model_info.items():
            if isinstance(key, str) and key.endswith("context_length"):
                candidates.append(value)
    if "context_length" in body:
        candidates.append(body["context_length"])
    for value in candidates:
        try:
            ctx = int(value)
        except (TypeError, ValueError):
            continue
        if ctx > 0:
            return ctx
    return None


def detect_server_context(
    config: LocalLLMConfig, *, timeout: Optional[float] = None
) -> ServerContextResult:
    """Best-effort detection of the model server's running context length.

    Only the Ollama-native provider exposes its context window (via the
    native ``/api/show`` endpoint). For the OpenAI-compatible provider there
    is no portable way to read the server's context window, so detection
    reports ``context_verified = False`` with an explanatory note —
    JobApplicator cannot verify that the server's real context matches the
    configured budget. Any network or parse failure degrades the same way.

    This function never raises: callers can record the result without a
    try/except and the test/preflight paths stay robust against an
    unreachable or unusual server.
    """
    if config.provider != PROVIDER_OLLAMA:
        return ServerContextResult(
            server_reported_context_tokens=None,
            context_verified=False,
            note=(
                "An OpenAI-compatible endpoint does not expose its context "
                "window, so JobApplicator cannot verify that the server's "
                "real context matches the configured budget."
            ),
        )

    url = _ollama_show_url(config.base_url)
    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    effective_timeout = (
        timeout if timeout is not None else config.effective_timeout_seconds
    )

    try:
        body = _post_json(
            url,
            {"model": config.model},
            headers=headers,
            timeout=effective_timeout,
        )
    except Exception as exc:  # noqa: BLE001 - detection must never raise
        return ServerContextResult(
            server_reported_context_tokens=None,
            context_verified=False,
            note=(
                "Could not read the Ollama server's context length from "
                f"{url}: {exc}"
            ),
        )

    if not isinstance(body, dict):
        return ServerContextResult(
            server_reported_context_tokens=None,
            context_verified=False,
            note=f"Ollama {url} returned a response that was not a JSON object.",
        )

    ctx = _extract_ollama_context_length(body)
    if ctx is None:
        return ServerContextResult(
            server_reported_context_tokens=None,
            context_verified=False,
            note=(
                "Ollama did not report a context length for model "
                f"{config.model!r}; cannot verify the configured budget."
            ),
        )

    num_ctx_note = (
        f" Requested num_ctx is {config.num_ctx}."
        if config.num_ctx is not None
        else ""
    )
    return ServerContextResult(
        server_reported_context_tokens=ctx,
        context_verified=True,
        note=(
            f"Ollama reports a context length of {ctx} tokens for model "
            f"{config.model}.{num_ctx_note}"
        ),
    )


class LocalLLMClient:
    """A tiny local chat client with two provider surfaces.

    The ``openai_compatible`` provider speaks ``POST {base_url}/chat/completions``
    (Ollama's ``/v1`` surface, vLLM, LM Studio, llama.cpp's server). The
    ``ollama`` provider speaks Ollama's native ``POST {base_url}/api/chat`` at
    the server root, optionally carrying ``options.num_ctx``. Routing is by
    provider, not by num_ctx (task 129). Errors are returned as a non-OK
    :class:`LLMCallResult` rather than raised, so callers can fall back to
    Claude Code cleanly.
    """

    def __init__(self, config: LocalLLMConfig):
        self.config = config

    @property
    def provider_id(self) -> str:
        return _local_provider_label(self.config)

    def _chat_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    def _ollama_native_chat_url(self) -> str:
        """The native ``/api/chat`` endpoint derived from ``base_url``.

        Ollama's OpenAI-compatible surface lives under ``/v1``; its native
        chat API is ``/api/chat`` at the server root. Strip a trailing
        ``/v1`` so a configured ``http://host:11434/v1`` resolves to
        ``http://host:11434/api/chat``.
        """
        base = self.config.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base}/api/chat"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        task: Optional[str] = None,
    ) -> LLMCallResult:
        """Send a chat-completions request and return the result."""
        prompt_text = "\n\n".join(
            f"{m.get('role', '')}: {m.get('content', '')}" for m in messages
        )
        budget_check = check_context_budget(prompt_text, self.config.context_budget)
        if budget_check.over_budget:
            return LLMCallResult(
                ok=False,
                provider=self.provider_id,
                model=self.config.model,
                task=task,
                error=(
                    "local LLM input over budget: estimated "
                    f"{budget_check.estimated_input_tokens} > "
                    f"{budget_check.max_input_tokens}; refusing to send prompt"
                ),
                context=budget_check.as_dict(),
            )

        # Routing is decided by the *provider*, not by num_ctx. The
        # Ollama-native provider always speaks its native ``/api/chat`` surface;
        # that endpoint exists at the server root regardless of whether a base
        # URL accidentally still carries a ``/v1`` suffix. Routing on num_ctx
        # (the previous behaviour) sent an Ollama server with no num_ctx
        # configured to ``/chat/completions``, which only exists under ``/v1``
        # on Ollama and 404s against a bare ``http://host:11434`` base URL.
        #
        # ``options.num_ctx`` is an optional add-on: Ollama only honours a
        # custom server context length on the native surface, so we attach it
        # when (and only when) it is configured. The OpenAI-compatible provider
        # speaks ``/chat/completions`` and never sends num_ctx — there is no
        # per-request way to set it there (tasks 126, 129).
        if self.config.provider == PROVIDER_OLLAMA:
            url = self._ollama_native_chat_url()
            payload: dict[str, Any] = {
                "model": self.config.model,
                "messages": messages,
                "stream": False,
            }
            if self.config.num_ctx is not None:
                payload["options"] = {"num_ctx": self.config.num_ctx}
            if response_format is not None:
                # Native /api/chat uses a top-level ``format`` field rather
                # than OpenAI's ``response_format``; ``"json"`` is the
                # supported structured-output value.
                payload["format"] = "json"
        else:
            url = self._chat_url()
            payload = {
                "model": self.config.model,
                "messages": messages,
            }
            if response_format is not None:
                payload["response_format"] = response_format

        headers: dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        # An explicit per-call ``timeout`` wins; otherwise use the config's
        # provider-aware effective timeout (Ollama 180s by default, others
        # 60s). This resolved value is the per-call bound passed to the
        # outbound request below (task 130).
        effective_timeout = (
            timeout if timeout is not None else self.config.effective_timeout_seconds
        )

        start = time.monotonic()
        try:
            body = _post_json(
                url, payload, headers=headers, timeout=effective_timeout
            )
        except urllib.error.HTTPError as exc:
            return LLMCallResult(
                ok=False,
                provider=self.provider_id,
                model=self.config.model,
                task=task,
                error=f"HTTP {exc.code} from {url}: {exc.reason}",
            )
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                msg = f"timeout after {effective_timeout}s contacting {url}"
            else:
                msg = f"connection error contacting {url}: {reason}"
            return LLMCallResult(
                ok=False,
                provider=self.provider_id,
                model=self.config.model,
                task=task,
                error=msg,
            )
        except TimeoutError:
            return LLMCallResult(
                ok=False,
                provider=self.provider_id,
                model=self.config.model,
                task=task,
                error=f"timeout after {effective_timeout}s contacting {url}",
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return LLMCallResult(
                ok=False,
                provider=self.provider_id,
                model=self.config.model,
                task=task,
                error=f"invalid response from {url}: {exc}",
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        content = _extract_content(body)
        if content is None:
            return LLMCallResult(
                ok=False,
                provider=self.provider_id,
                model=self.config.model,
                task=task,
                error="response missing choices[0].message.content",
                latency_ms=latency_ms,
            )
        model = body.get("model") or self.config.model
        return LLMCallResult(
            ok=True,
            provider=self.provider_id,
            model=model,
            task=task,
            content=content,
            latency_ms=latency_ms,
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        required_fields: list[str],
        task: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> LLMCallResult:
        """Chat and validate the reply as JSON with ``required_fields``.

        On a schema-validation failure the call is retried *once* with a
        repair prompt. The returned result records ``schema_valid`` and
        whether a repair (``repaired``) was used, and is logged.
        """
        result = self.chat(
            messages,
            response_format={"type": "json_object"},
            timeout=timeout,
            task=task,
        )
        if not result.ok:
            result.schema_valid = False
            _log_call(result)
            return result

        data, reason = validate_json_payload(result.content, required_fields)
        if reason is None:
            result.parsed = data
            result.schema_valid = True
            _log_call(result)
            return result

        # One repair attempt: feed the bad reply back with the reason.
        repair_messages = [
            *messages,
            {"role": "assistant", "content": result.content or ""},
            {"role": "user", "content": _repair_prompt(required_fields, reason)},
        ]
        retry = self.chat(
            repair_messages,
            response_format={"type": "json_object"},
            timeout=timeout,
            task=task,
        )
        retry.repaired = True
        if not retry.ok:
            retry.schema_valid = False
            _log_call(retry)
            return retry
        data2, reason2 = validate_json_payload(retry.content, required_fields)
        retry.parsed = data2
        retry.schema_valid = reason2 is None
        if reason2 is not None:
            retry.error = f"schema validation failed after repair: {reason2}"
        _log_call(retry)
        return retry

    def test_connection(self) -> LLMCallResult:
        """Send a minimal prompt to verify the endpoint and model respond."""
        result = self.chat(
            [{"role": "user", "content": "Reply with the single word: pong"}],
            task="test_connection",
        )
        return result
