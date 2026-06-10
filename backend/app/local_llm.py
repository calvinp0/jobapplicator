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
# OpenAI-compatible surface). ``ollama`` is kept as a label so the UI can
# distinguish a native-Ollama setup; both speak the same chat-completions
# shape in this iteration.
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_OLLAMA = "ollama"
SUPPORTED_PROVIDER_MODES = (PROVIDER_OPENAI_COMPATIBLE, PROVIDER_OLLAMA)

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT_SECONDS = 60
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
    allowed_tasks: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_ALLOWED_TASKS)
    )
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS
    max_input_tokens: Optional[int] = DEFAULT_MAX_INPUT_TOKENS
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
    return LocalLLMConfig(
        enabled=bool(raw.get("enabled", False)),
        provider=raw.get("provider") or PROVIDER_OPENAI_COMPATIBLE,
        base_url=raw.get("base_url") or DEFAULT_BASE_URL,
        model=raw.get("model") or DEFAULT_MODEL,
        timeout_seconds=int(raw.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
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
    timeout_seconds: int,
    allowed_tasks: dict[str, bool],
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
    reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT_TOKENS,
    max_input_tokens: Optional[int] = DEFAULT_MAX_INPUT_TOKENS,
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

    try:
        timeout_int = int(timeout_seconds)
    except (TypeError, ValueError) as exc:
        raise LocalLLMValidationError("timeout_seconds must be an integer") from exc
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
        timeout_seconds=timeout_int,
        allowed_tasks=normalized_tasks,
        context_window_tokens=budget.context_window_tokens,
        reserved_output_tokens=budget.reserved_output_tokens,
        max_input_tokens=budget.max_input_tokens,
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
        "timeout_seconds": config.timeout_seconds,
        "allowed_tasks": dict(config.allowed_tasks),
        "context_window_tokens": budget.context_window_tokens,
        "reserved_output_tokens": budget.reserved_output_tokens,
        "max_input_tokens": budget.max_input_tokens,
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
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


class LocalLLMClient:
    """A tiny OpenAI-compatible chat-completions client.

    Speaks the ``POST {base_url}/chat/completions`` shape used by Ollama's
    ``/v1`` surface, vLLM, LM Studio, and llama.cpp's server. Errors are
    returned as a non-OK :class:`LLMCallResult` rather than raised, so
    callers can fall back to Claude Code cleanly.
    """

    def __init__(self, config: LocalLLMConfig):
        self.config = config

    @property
    def provider_id(self) -> str:
        return _local_provider_label(self.config)

    def _chat_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

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

        url = self._chat_url()
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        headers: dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        effective_timeout = (
            timeout if timeout is not None else self.config.timeout_seconds
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
                msg = f"timeout after {effective_timeout}s"
            else:
                msg = f"connection error: {reason}"
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
                error=f"timeout after {effective_timeout}s",
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
