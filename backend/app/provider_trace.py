"""Provider/run trace for application/tailoring runs (task 129).

This module records *which execution provider produced each step* of an
application run so the UI can answer, at a glance, questions like "was the
local LLM actually used?" without the operator having to read logs or run
``ollama ps``.

The trace is intentionally provider-agnostic and decoupled from how each
step runs: the preflight pipeline (:mod:`app.preflight`) routes low-risk
extraction tasks to a local LLM or a deterministic fallback; the main
tailoring prompt runs on Claude Code; and DOCX rendering is deterministic
backend work (:mod:`app.resume_docx_renderer`). Each of those contributes
:class:`TraceEvent` rows, which the worker assembles into a single
``runs/<run_id>/provider_trace.json`` plus a compact ``provider_summary``
mirrored into ``metadata.json``.

Design boundaries:

- The trace is **descriptive**, never authoritative. It records what ran;
  it does not change routing decisions.
- Advanced/technical fields (context budget, requested ``num_ctx``,
  server-reported context, endpoint host) live under a nested ``details``
  block so the default UI can stay compact and only the disclosure shows
  them. The endpoint *host* may be recorded, but never a full URL and
  **never** an API key — credentials never enter the trace.
- Writing the trace must never fail a run: callers wrap persistence so a
  trace error degrades to "no trace" rather than aborting tailoring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---- Filenames -------------------------------------------------------

PROVIDER_TRACE_FILENAME = "provider_trace.json"
# Key under which the compact summary is mirrored into metadata.json.
PROVIDER_SUMMARY_KEY = "provider_summary"

# ---- Statuses --------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_FALLBACK = "fallback"
STATUS_ABORTED = "aborted"

ALLOWED_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_FALLBACK,
    STATUS_ABORTED,
)

# ---- Providers -------------------------------------------------------

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_CLAUDE_CODE = "claude_code"
PROVIDER_BACKEND = "backend"
PROVIDER_DETERMINISTIC = "deterministic"
PROVIDER_UNKNOWN = "unknown"

ALLOWED_PROVIDERS: tuple[str, ...] = (
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_CLAUDE_CODE,
    PROVIDER_BACKEND,
    PROVIDER_DETERMINISTIC,
    PROVIDER_UNKNOWN,
)

# User-facing labels. Kept here (not in the frontend) so the API and any
# persisted file agree on the exact wording.
PROVIDER_LABELS: dict[str, str] = {
    PROVIDER_OLLAMA: "Ollama",
    PROVIDER_OPENAI_COMPATIBLE: "OpenAI-compatible local LLM",
    PROVIDER_CLAUDE_CODE: "Claude Code",
    PROVIDER_BACKEND: "Backend renderer",
    PROVIDER_DETERMINISTIC: "Deterministic backend",
    PROVIDER_UNKNOWN: "Unknown",
}

# Short labels used in the one-line compact summary so it stays subtle.
PROVIDER_SHORT_LABELS: dict[str, str] = {
    PROVIDER_OLLAMA: "Ollama",
    PROVIDER_OPENAI_COMPATIBLE: "OpenAI-compatible",
    PROVIDER_CLAUDE_CODE: "Claude Code",
    PROVIDER_BACKEND: "Backend",
    PROVIDER_DETERMINISTIC: "deterministic backend",
    PROVIDER_UNKNOWN: "Unknown",
}

# ---- Steps -----------------------------------------------------------

STEP_JOB_SUMMARY = "job_summary"
STEP_ATS_KEYWORDS = "ats_keywords"
STEP_ROLE_REQUIREMENTS = "role_requirements"
STEP_EVIDENCE_GAP_PLAN = "evidence_gap_plan"
STEP_RESUME_SUGGESTIONS = "resume_suggestions"
STEP_RESUME_GENERATION = "resume_generation"
STEP_CLAIM_AUDIT = "claim_audit"
STEP_DOCX_RENDER = "docx_render"
STEP_TEMPLATE_FIDELITY_AUDIT = "template_fidelity_audit"

STEP_LABELS: dict[str, str] = {
    STEP_JOB_SUMMARY: "Job summary",
    STEP_ATS_KEYWORDS: "ATS keywords",
    STEP_ROLE_REQUIREMENTS: "Role requirements",
    STEP_EVIDENCE_GAP_PLAN: "Evidence gap plan",
    STEP_RESUME_SUGGESTIONS: "Resume suggestions",
    STEP_RESUME_GENERATION: "Resume generation",
    STEP_CLAIM_AUDIT: "Claim audit",
    STEP_DOCX_RENDER: "DOCX render",
    STEP_TEMPLATE_FIDELITY_AUDIT: "Template fidelity audit",
}

# Steps grouped for the compact one-line summary. Preflight is the local /
# deterministic helper band; tailoring is the Claude band; docx is backend.
_PREFLIGHT_STEPS = (
    STEP_JOB_SUMMARY,
    STEP_ATS_KEYWORDS,
    STEP_ROLE_REQUIREMENTS,
    STEP_EVIDENCE_GAP_PLAN,
)

# Maps the preflight pipeline's internal provider ids (``local_ollama`` /
# ``local_openai_compatible`` / ``deterministic``) onto trace provider ids.
_PREFLIGHT_PROVIDER_MAP: dict[str, str] = {
    "local_ollama": PROVIDER_OLLAMA,
    "local_openai_compatible": PROVIDER_OPENAI_COMPATIBLE,
    "deterministic": PROVIDER_DETERMINISTIC,
}

# Maps the run's tailoring provider id (the llm_provider registry id) onto a
# trace provider. Anything not local maps to Claude Code, since the tailoring
# band is Claude unless full local tailoring is explicitly enabled.
_TAILORING_PROVIDER_MAP: dict[str, str] = {
    "claude_code": PROVIDER_CLAUDE_CODE,
    "local_ollama": PROVIDER_OLLAMA,
    "local_openai_compatible": PROVIDER_OPENAI_COMPATIBLE,
}


def provider_label(provider: str) -> str:
    """Return the user-facing label for a trace provider id."""
    return PROVIDER_LABELS.get(provider, PROVIDER_LABELS[PROVIDER_UNKNOWN])


def map_preflight_provider(provider_id: Optional[str]) -> str:
    """Map a preflight provider id onto a trace provider id."""
    if not provider_id:
        return PROVIDER_UNKNOWN
    return _PREFLIGHT_PROVIDER_MAP.get(provider_id, PROVIDER_UNKNOWN)


def map_tailoring_provider(provider_id: Optional[str]) -> str:
    """Map a run's llm_provider id onto a trace provider id.

    The tailoring band is Claude Code unless the run explicitly selected a
    local provider, so an unknown/empty id is treated as Claude Code rather
    than ``unknown`` — that matches the worker's own default.
    """
    if not provider_id:
        return PROVIDER_CLAUDE_CODE
    return _TAILORING_PROVIDER_MAP.get(provider_id, PROVIDER_CLAUDE_CODE)


# ---- Trace event -----------------------------------------------------


@dataclass
class TraceEvent:
    """One provider-trace row for a single run step.

    ``provider`` must be one of :data:`ALLOWED_PROVIDERS` and ``status`` one
    of :data:`ALLOWED_STATUSES`. ``provider_label`` is derived automatically
    from ``provider`` when not supplied. The advanced/technical fields
    (context budget, requested ``num_ctx``, server-reported context,
    endpoint host) are serialized under a nested ``details`` block so the
    compact view never has to carry them.
    """

    step: str
    provider: str
    status: str
    label: Optional[str] = None
    provider_label: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    compression_used: bool = False
    fallback_used: bool = False
    warning: Optional[str] = None
    # Advanced/technical fields (nested under ``details`` on serialization).
    context_budget_tokens: Optional[int] = None
    usable_input_tokens: Optional[int] = None
    requested_num_ctx: Optional[int] = None
    server_reported_context_tokens: Optional[int] = None
    context_verified: Optional[bool] = None
    endpoint_host: Optional[str] = None

    def __post_init__(self) -> None:
        if self.label is None:
            self.label = STEP_LABELS.get(self.step, self.step)
        if self.provider_label is None:
            self.provider_label = provider_label(self.provider)

    def details(self) -> dict[str, Any]:
        """Return the advanced/technical detail block (omitting empties)."""
        raw = {
            "context_budget_tokens": self.context_budget_tokens,
            "usable_input_tokens": self.usable_input_tokens,
            "requested_num_ctx": self.requested_num_ctx,
            "server_reported_context_tokens": self.server_reported_context_tokens,
            "context_verified": self.context_verified,
            "endpoint_host": self.endpoint_host,
        }
        return {k: v for k, v in raw.items() if v is not None}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the shape used by both the trace file and the API.

        Compact fields stay at the top level; advanced fields are nested
        under ``details``. ``details`` is omitted entirely when empty so a
        deterministic/Claude step doesn't carry an empty object. The shape
        never includes credentials.
        """
        event: dict[str, Any] = {
            "step": self.step,
            "label": self.label,
            "provider": self.provider,
            "provider_label": self.provider_label,
            "model": self.model,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "compression_used": self.compression_used,
            "fallback_used": self.fallback_used,
            "warning": self.warning,
        }
        details = self.details()
        if details:
            event["details"] = details
        return event


# ---- Preflight → events ----------------------------------------------


def events_from_preflight(result: Any) -> list[TraceEvent]:
    """Build trace events from a :class:`app.preflight.PreflightResult`.

    Reads each :class:`PreflightTaskResult`: the provider id and model are
    mapped onto trace ids, the preflight ``status`` (``succeeded`` /
    ``failed`` / ``fallback``) is mapped onto a trace status, and the
    per-task ``context`` block (when the local path was attempted) supplies
    the advanced budget fields. A task that fell back to the deterministic
    extractor is recorded with ``status="fallback"`` and ``fallback_used``
    so the UI can show the degradation without a second row.
    """
    events: list[TraceEvent] = []
    for task in getattr(result, "tasks", []) or []:
        step = _preflight_task_step(getattr(task, "name", ""))
        provider = map_preflight_provider(getattr(task, "provider", None))
        status = _preflight_status(
            getattr(task, "status", ""),
            fallback_used=bool(getattr(task, "fallback_used", False)),
        )
        context = getattr(task, "context", None) or {}
        events.append(
            TraceEvent(
                step=step,
                provider=provider,
                status=status,
                model=getattr(task, "model", None),
                duration_ms=getattr(task, "duration_ms", None),
                started_at=getattr(task, "started_at", None),
                completed_at=getattr(task, "completed_at", None),
                compression_used=bool(context.get("compression_used", False)),
                fallback_used=bool(getattr(task, "fallback_used", False)),
                warning=_preflight_warning(task),
                context_budget_tokens=context.get("context_window_tokens"),
                usable_input_tokens=context.get("max_input_tokens"),
                requested_num_ctx=context.get("requested_num_ctx"),
            )
        )
    return events


# Preflight uses descriptive task names; the ATS task spells its name out.
_PREFLIGHT_NAME_TO_STEP: dict[str, str] = {
    "job_summary": STEP_JOB_SUMMARY,
    "ats_keyword_extraction": STEP_ATS_KEYWORDS,
    "role_requirements": STEP_ROLE_REQUIREMENTS,
    "evidence_gap_plan": STEP_EVIDENCE_GAP_PLAN,
}


def _preflight_task_step(name: str) -> str:
    return _PREFLIGHT_NAME_TO_STEP.get(name, name)


def _preflight_status(status: str, *, fallback_used: bool) -> str:
    if fallback_used:
        return STATUS_FALLBACK
    if status == "succeeded":
        return STATUS_COMPLETE
    if status == "failed":
        return STATUS_FAILED
    if status == "fallback":
        return STATUS_FALLBACK
    return STATUS_COMPLETE


def _preflight_warning(task: Any) -> Optional[str]:
    reason = getattr(task, "fallback_reason", None)
    if getattr(task, "fallback_used", False) and reason:
        return f"Local LLM step fell back to deterministic extractor: {reason}"
    return None


# ---- Convenience constructors ----------------------------------------


def claude_event(
    step: str,
    *,
    provider_id: Optional[str],
    status: str,
    duration_ms: Optional[int] = None,
    warning: Optional[str] = None,
) -> TraceEvent:
    """Build a tailoring-band event (Claude Code unless local is selected)."""
    provider = map_tailoring_provider(provider_id)
    model = "claude-code" if provider == PROVIDER_CLAUDE_CODE else None
    return TraceEvent(
        step=step,
        provider=provider,
        status=status,
        model=model,
        duration_ms=duration_ms,
        warning=warning,
    )


def backend_event(
    step: str,
    *,
    status: str,
    duration_ms: Optional[int] = None,
    warning: Optional[str] = None,
) -> TraceEvent:
    """Build a deterministic backend event (DOCX render / fidelity audit)."""
    return TraceEvent(
        step=step,
        provider=PROVIDER_BACKEND,
        status=status,
        duration_ms=duration_ms,
        warning=warning,
    )


# ---- Summary ---------------------------------------------------------

# Statuses that count as "this provider actually did work on this run" for
# the providers_used list and the compact band labels. A skipped/pending
# step does not pull its provider into the summary.
_ACTIVE_STATUSES = (STATUS_COMPLETE, STATUS_FAILED, STATUS_FALLBACK, STATUS_ABORTED, STATUS_RUNNING)


def build_summary(events: list[TraceEvent]) -> dict[str, Any]:
    """Build the compact provider summary mirrored into metadata + API.

    Produces the one-line ``label`` ("Preflight: … · Tailoring: … · DOCX:
    …"), the per-band strings, an ordered de-duplicated ``providers_used``
    list, and the collected ``warnings``. A run with no events still
    returns a well-formed (empty) summary so callers never special-case it.
    """
    active = [e for e in events if e.status in _ACTIVE_STATUSES]

    preflight_band = _band_label(
        [e for e in active if e.step in _PREFLIGHT_STEPS]
    )
    tailoring_band = _band_label(
        [e for e in active if e.step == STEP_RESUME_GENERATION]
    )
    docx_band = _band_label(
        [e for e in active if e.step == STEP_DOCX_RENDER]
    )

    parts: list[str] = []
    if preflight_band:
        parts.append(f"Preflight: {preflight_band}")
    if tailoring_band:
        parts.append(f"Tailoring: {tailoring_band}")
    if docx_band:
        parts.append(f"DOCX: {docx_band}")
    label = " · ".join(parts)

    providers_used: list[str] = []
    for event in active:
        if event.provider not in providers_used:
            providers_used.append(event.provider)

    warnings = [e.warning for e in events if e.warning]

    return {
        "label": label,
        "preflight": _band_label_full(
            [e for e in active if e.step in _PREFLIGHT_STEPS]
        ),
        "tailoring": _band_label_full(
            [e for e in active if e.step == STEP_RESUME_GENERATION]
        ),
        "docx": _band_label_full(
            [e for e in active if e.step == STEP_DOCX_RENDER]
        ),
        "providers_used": providers_used,
        "warnings": warnings,
        "has_warnings": bool(warnings),
    }


def _distinct_providers(events: list[TraceEvent]) -> list[str]:
    out: list[str] = []
    for event in events:
        if event.provider not in out:
            out.append(event.provider)
    return out


def _band_label(events: list[TraceEvent]) -> str:
    """Short band label for the one-line summary (no model)."""
    providers = _distinct_providers(events)
    if not providers:
        return ""
    return " + ".join(PROVIDER_SHORT_LABELS.get(p, p) for p in providers)


def _band_label_full(events: list[TraceEvent]) -> str:
    """Full band label including the model when a single provider ran.

    e.g. ``"Ollama / qwen3.5:9b"`` for a clean local preflight, or
    ``"Backend renderer"`` for docx. Mixed providers join their full
    labels without a model since there's no single model to name.
    """
    providers = _distinct_providers(events)
    if not providers:
        return ""
    if len(providers) == 1:
        provider = providers[0]
        label = PROVIDER_LABELS.get(provider, provider)
        # Only name the model for local LLM bands — "Claude Code / claude-code"
        # is noise, and backend/deterministic steps have no model.
        if provider in (PROVIDER_OLLAMA, PROVIDER_OPENAI_COMPATIBLE):
            models = {e.model for e in events if e.model}
            if len(models) == 1:
                return f"{label} / {next(iter(models))}"
        return label
    return " + ".join(PROVIDER_LABELS.get(p, p) for p in providers)


# ---- Persistence -----------------------------------------------------


def _trace_path(run_dir: Path) -> Path:
    return Path(run_dir) / PROVIDER_TRACE_FILENAME


def write_provider_trace(run_dir: Path, events: list[TraceEvent]) -> Path:
    """Write ``runs/<run_id>/provider_trace.json`` and return its path.

    The file is a flat list of serialized events. It never contains
    credentials — :meth:`TraceEvent.to_dict` only emits the whitelisted
    fields, and the endpoint *host* (when present) is the only network
    locator recorded.
    """
    path = _trace_path(run_dir)
    payload = [event.to_dict() for event in events]
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def read_provider_trace(run_dir: Path) -> list[dict[str, Any]]:
    """Read the persisted provider trace, or ``[]`` when absent/unreadable.

    Best-effort: a missing or malformed file returns an empty list so the
    API can still serve runs that predate the trace (or whose trace write
    was interrupted) without erroring.
    """
    path = _trace_path(run_dir)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return data
