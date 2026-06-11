"""Provider-routed preflight analysis pipeline (task 124).

This module runs a small set of *low-risk* extraction/classification tasks
over a run's job description **before** the main Claude Code tailoring
prompt runs. Each task produces a structured JSON artifact under
``input/preflight/`` that the tailoring prompt consumes as advisory input:

```text
input/preflight/job_summary.json
input/preflight/ats_keywords.json
input/preflight/role_requirements.json
input/preflight/evidence_gap_plan.json
input/preflight/preflight_manifest.json
input/preflight/preflight_summary.md     # human-readable projection
```

Provider routing reuses the Task 123 policy in :mod:`app.local_llm`: when
the experimental local LLM subsystem is enabled *and* a preflight task is
toggled on, that task is attempted on the local provider; otherwise (or on
any failure) a deterministic, regex/heading-based extractor produces the
same artifact. The deterministic path is the floor — preflight never
requires a local LLM, and never fails the whole run as long as the
deterministic fallback can write valid JSON.

Design boundaries (mirrors ``docs/llm_providers.md``):

- Preflight outputs are **advisory**. The tailoring prompt's truthfulness /
  evidence contract still dominates; if preflight conflicts with the job
  description, the job description wins.
- Preflight does **not** decide whether the candidate has a keyword, nor
  audit evidence. ``evidence_gap_plan.json`` is a *plan* of where to look,
  never a claim that evidence exists.
- Local prompts send only bounded inputs (the job description and, for the
  gap plan, the staged evidence index filenames) — never secrets, never the
  full run directory.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import local_llm
from .context_budget import (
    ContextBudget,
    ContextBudgetCheck,
    build_context_budget,
    check_context_budget,
)
from .local_llm import (
    LLMCallResult,
    LocalLLMClient,
    LocalLLMConfig,
    TASK_ATS_KEYWORDS,
    TASK_EVIDENCE_GAP_PLAN,
    TASK_JOB_SUMMARY,
    TASK_ROLE_REQUIREMENTS,
    local_allowed_for_task,
)

# ---- Layout ----------------------------------------------------------

INPUT_DIRNAME = "input"
PREFLIGHT_DIRNAME = "preflight"

JOB_SUMMARY_FILENAME = "job_summary.json"
ATS_KEYWORDS_FILENAME = "ats_keywords.json"
ROLE_REQUIREMENTS_FILENAME = "role_requirements.json"
EVIDENCE_GAP_PLAN_FILENAME = "evidence_gap_plan.json"
PREFLIGHT_MANIFEST_FILENAME = "preflight_manifest.json"
PREFLIGHT_SUMMARY_FILENAME = "preflight_summary.md"

JOB_DESCRIPTION_FILENAME = "job_description.md"
JOB_CAPTURE_FILENAME = "job_capture.md"
EVIDENCE_SOURCES_INDEX_FILENAME = "evidence_sources_index.md"
EVIDENCE_SOURCES_DIRNAME = "evidence_sources"

# Provider id stamped on the manifest when no local LLM produced an artifact.
DETERMINISTIC_PROVIDER = "deterministic"

# Manifest task names (descriptive; the ATS task name is spelled out per the
# task spec even though its routing policy id is ``ats_keywords``).
TASK_NAME_JOB_SUMMARY = "job_summary"
TASK_NAME_ATS_KEYWORDS = "ats_keyword_extraction"
TASK_NAME_ROLE_REQUIREMENTS = "role_requirements"
TASK_NAME_EVIDENCE_GAP_PLAN = "evidence_gap_plan"

STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_FALLBACK = "fallback"

# Provider-degradation guardrails (task 132). A slow or wedged local server
# otherwise makes *every* eligible preflight task pay a full timeout before
# falling back, multiplying the wasted wall-clock by the number of tasks. The
# first local timeout in a run marks the provider degraded; once this many
# timeouts accumulate the remaining tasks skip the local provider entirely and
# go straight to the deterministic extractor. The threshold is deliberately
# small (2) so a single cold task can still recover while a genuinely
# unresponsive server is abandoned after one extra confirmation.
LOCAL_SKIP_TIMEOUT_THRESHOLD = 2

# Recorded as the per-task ``fallback_reason`` when a task is routed straight
# to the deterministic extractor because the local provider was skipped after
# repeated timeouts.
LOCAL_SKIPPED_REASON = "local provider skipped after repeated timeouts"

# Stable marker phrasing for the "local LLM was tried and then degraded/skipped"
# situation (task 133). Emitted verbatim through the run trace (run.log /
# progress stream) and rendered into the human-readable preflight summary so an
# operator — and the frontend run-trace task (134) — can key on a single,
# documented string. Always followed by ``": <reason>"``.
LOCAL_ATTEMPTED_FELL_BACK_MARKER = "Local LLM attempted but fell back"

# Default context window preflight budgets against (task 132). Preflight
# prompts are short — a single job description plus a fixed JSON shape — and a
# reasoning model handed a large declared context wastes it (and slows down)
# for no benefit. So preflight budgets against a smaller window than the
# general local-LLM default (``local_llm.DEFAULT_CONTEXT_WINDOW_TOKENS`` =
# 8192) whenever the user has not explicitly configured ``context_window_tokens``.
# This is a *default*, never a cap: an explicit user-configured context window
# is always honoured verbatim (see ``_preflight_context_budget``).
PREFLIGHT_DEFAULT_CONTEXT_WINDOW_TOKENS = 4096

# Keyword category / priority vocabularies (used by validators and the
# deterministic extractor). Categories follow the task spec.
KEYWORD_CATEGORIES = ("required", "preferred", "industry", "responsibility")
KEYWORD_PRIORITIES = ("high", "medium", "low")

REQUIREMENT_IMPORTANCE = ("required", "preferred")


# ---- Deterministic vocabularies --------------------------------------
#
# A curated, conservative vocabulary keeps the deterministic extractor
# stable and testable: we only surface a tool/domain keyword when it
# literally appears in the job description. This is intentionally not an
# exhaustive ontology — the local-LLM path is where richer extraction
# happens. Matching is case-insensitive and word-boundary aware.

KNOWN_TOOLS: tuple[str, ...] = (
    "Python", "PyTorch", "TensorFlow", "JAX", "NumPy", "Pandas",
    "scikit-learn", "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis",
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Spark", "Hadoop",
    "Kafka", "Airflow", "Git", "Java", "JavaScript", "TypeScript",
    "C++", "Go", "Rust", "React", "Node.js", "FastAPI", "Flask",
    "Django", "Linux", "Bash", "Terraform", "MATLAB", "R",
)

KNOWN_DOMAINS: tuple[str, ...] = (
    "Scientific Machine Learning", "Machine Learning", "Deep Learning",
    "Natural Language Processing", "NLP", "Computer Vision", "Simulation",
    "Computational Chemistry", "Data Science", "Reinforcement Learning",
    "Large Language Models", "LLM", "MLOps", "Data Engineering",
    "Distributed Systems", "High Performance Computing", "Statistics",
    "Cloud deployment", "Cloud", "Bioinformatics",
)

# Heading keywords that switch the "current section" while scanning the JD.
_REQUIRED_HEADINGS = ("requirement", "qualification", "must have", "what you", "you have", "skills")
_PREFERRED_HEADINGS = ("preferred", "nice to have", "nice-to-have", "bonus", "plus")
_RESPONSIBILITY_HEADINGS = ("responsibilit", "what you'll do", "what you will do", "the role", "day to day", "day-to-day")

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(.+?)\s*$")
_SENIORITY_RE = re.compile(
    r"\b(intern|junior|mid[- ]level|senior|staff|principal|lead|head|director)\b",
    re.IGNORECASE,
)


class PreflightError(RuntimeError):
    """Raised only when even the deterministic fallback cannot run."""


# ---- Result types ----------------------------------------------------


@dataclass
class PreflightTaskResult:
    """Outcome of one preflight task, recorded in the manifest."""

    name: str
    provider: str
    model: Optional[str]
    status: str
    output: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    context: Optional[dict[str, Any]] = None
    # Wall-clock timing for the provider trace (task 129). Recorded on the
    # dataclass only — intentionally kept out of ``manifest_entry`` so the
    # preflight manifest shape stays stable; the worker reads these to build
    # ``provider_trace.json``.
    duration_ms: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # Local LLM performance record (task 133). ``local_attempted`` is True only
    # when a local call was actually issued for this task (a ``chat_json``
    # request was sent), distinct from a task that fell back before contacting
    # the server (budget over-limit, or the task-132 skip path). The other three
    # fields populate the manifest entry's ``performance`` object:
    # ``prompt_token_estimate`` reuses the estimate already computed in
    # ``_prepare_local_messages`` (``estimated_input_tokens_final``);
    # ``latency_ms`` is the call's measured elapsed time; and
    # ``effective_timeout_seconds`` is the per-call timeout that bounded it
    # (task 130).
    local_attempted: bool = False
    prompt_token_estimate: Optional[int] = None
    latency_ms: Optional[int] = None
    effective_timeout_seconds: Optional[int] = None

    def manifest_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "output": self.output,
        }
        if self.fallback_used:
            entry["fallback_used"] = True
            if self.fallback_reason:
                entry["fallback_reason"] = self.fallback_reason
        if self.context is not None:
            entry["context"] = self.context
        # Performance record for a genuinely-attempted local call (task 133).
        # Deterministic-only tasks (local never attempted) gain neither the flag
        # nor the ``performance`` object, so they stay neutral.
        if self.local_attempted:
            entry["local_attempted"] = True
            performance: dict[str, Any] = {}
            if self.prompt_token_estimate is not None:
                performance["prompt_token_estimate"] = self.prompt_token_estimate
            if self.latency_ms is not None:
                performance["elapsed_ms"] = self.latency_ms
            if self.effective_timeout_seconds is not None:
                performance["effective_timeout_seconds"] = (
                    self.effective_timeout_seconds
                )
            if performance:
                entry["performance"] = performance
        return entry


@dataclass
class PreflightResult:
    """Aggregate outcome of a preflight run."""

    preflight_dir: Path
    provider: str
    model: Optional[str]
    fallback_used: bool
    fallback_reason: Optional[str]
    tasks: list[PreflightTaskResult] = field(default_factory=list)
    manifest_path: Optional[Path] = None
    artifact_paths: dict[str, Path] = field(default_factory=dict)
    # Per-run provider-degradation state (task 132), exposed in-memory for the
    # manifest/run-trace task (133). ``local_degraded`` is set after the first
    # local timeout; ``local_skipped`` after the repeated-timeout threshold,
    # once the remaining tasks bypass the local provider entirely.
    local_degraded: bool = False
    local_skipped: bool = False


@dataclass
class _ProviderHealth:
    """Per-run local-provider health tracker (task 132).

    Threaded explicitly through the per-task ``_run_one`` calls — never
    module-level or process-global — so degradation is scoped to a single
    ``run_preflight`` invocation and a fresh run always starts clean.
    """

    timeouts: int = 0
    degraded: bool = False

    def record_timeout(self) -> None:
        """Note a local timeout; the first one marks the provider degraded."""
        self.timeouts += 1
        self.degraded = True

    @property
    def skip_local(self) -> bool:
        """Whether remaining tasks should bypass the local provider."""
        return self.timeouts >= LOCAL_SKIP_TIMEOUT_THRESHOLD


# A spec wiring a manifest task name to its routing policy id, artifact
# filename, the local-LLM ``required_fields`` gate, and the deterministic
# builder + validator used for the fallback / final shape check.
@dataclass(frozen=True)
class _TaskSpec:
    name: str
    policy_task: str
    artifact: str
    required_fields: tuple[str, ...]


# ---- Public entry point ----------------------------------------------


def run_preflight(
    run_dir: Path,
    *,
    config: Optional[LocalLLMConfig] = None,
    now: Optional[datetime] = None,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> PreflightResult:
    """Run the preflight pipeline for a staged run directory.

    Reads ``input/job_description.md`` (and, for the gap plan, the staged
    evidence index), routes each task through the local provider when the
    Task 123 policy permits, otherwise falls back to the deterministic
    extractor, and writes every artifact under ``input/preflight/``. The
    manifest is always written, even on degradation. Returns a
    :class:`PreflightResult` describing what ran.
    """

    def log(msg: str) -> None:
        if on_log is not None:
            on_log(msg)

    def progress(msg: str) -> None:
        if on_progress is not None:
            on_progress(msg)

    run_dir = Path(run_dir)
    input_dir = run_dir / INPUT_DIRNAME
    preflight_dir = input_dir / PREFLIGHT_DIRNAME
    preflight_dir.mkdir(parents=True, exist_ok=True)

    cfg = config if config is not None else local_llm.get_config()

    jd_text = _read_text(input_dir / JOB_DESCRIPTION_FILENAME)
    capture_text = _read_text(input_dir / JOB_CAPTURE_FILENAME)
    if capture_text and capture_text not in jd_text:
        jd_text = f"{jd_text}\n\n{capture_text}".strip()
    evidence_files = _staged_evidence_files(input_dir)

    log("running preflight analysis")
    progress("Running preflight job analysis")

    # Is the local provider the *intended* primary for this run? Used to
    # decide the manifest's top-level provider and whether a deterministic
    # result counts as a fallback (vs. the deterministic default).
    intended_local = cfg.enabled and any(
        local_allowed_for_task(spec.policy_task, cfg) for spec in _SPECS
    )
    client = LocalLLMClient(cfg) if intended_local else None

    primary_provider = (
        local_llm._local_provider_label(cfg) if intended_local else DETERMINISTIC_PROVIDER
    )
    primary_model = cfg.model if intended_local else None
    log(
        "preflight provider: "
        + (primary_provider if intended_local else DETERMINISTIC_PROVIDER)
    )

    # Best-effort server-context detection for local runs (task 127). The
    # result is recorded once at the manifest top level so every local run
    # carries an auditable record of the context it assumed vs. the context
    # the server actually reports. Detection never raises and never fails
    # preflight: an unreachable or OpenAI-compatible server simply degrades to
    # ``context_verified = False``.
    context_summary: Optional[dict[str, Any]] = None
    if intended_local:
        detection = local_llm.detect_server_context(
            cfg, timeout=min(float(cfg.timeout_seconds), 10.0)
        )
        context_summary = {
            "assumed_context_tokens": cfg.context_window_tokens,
            "server_reported_context_tokens": (
                detection.server_reported_context_tokens
            ),
            "context_verified": detection.context_verified,
            "note": detection.note,
        }
        if cfg.num_ctx is not None:
            context_summary["requested_num_ctx"] = cfg.num_ctx
        log(
            "preflight context: assumed "
            f"{cfg.context_window_tokens} tokens; "
            + (
                "server reports "
                f"{detection.server_reported_context_tokens} tokens"
                if detection.context_verified
                else "server context unverified"
            )
        )

    results: list[PreflightTaskResult] = []
    artifact_paths: dict[str, Path] = {}

    # Per-run provider-degradation tracker (task 132). Created fresh per call —
    # never module-level — so degradation is scoped to this run and a fresh
    # ``run_preflight`` always starts clean.
    health = _ProviderHealth()

    # job_summary -------------------------------------------------------
    progress("Summarizing job description")
    _t0, _started = time.monotonic(), datetime.now(timezone.utc).isoformat()
    data, result = _run_one(
        _SPEC_JOB_SUMMARY,
        cfg,
        client,
        local_messages=lambda text: _job_summary_messages(text),
        source_text=jd_text,
        deterministic=lambda: deterministic_job_summary(jd_text),
        validator=validate_job_summary,
        log=log,
        health=health,
    )
    _stamp_timing(result, _t0, _started)
    _write_artifact(preflight_dir, _SPEC_JOB_SUMMARY.artifact, data, results, result, artifact_paths, log)

    # ats_keyword_extraction -------------------------------------------
    progress("Extracting ATS keywords")
    _t0, _started = time.monotonic(), datetime.now(timezone.utc).isoformat()
    data, result = _run_one(
        _SPEC_ATS_KEYWORDS,
        cfg,
        client,
        local_messages=lambda text: _ats_keywords_messages(text),
        source_text=jd_text,
        deterministic=lambda: deterministic_ats_keywords(jd_text),
        validator=validate_ats_keywords,
        log=log,
        health=health,
    )
    _stamp_timing(result, _t0, _started)
    _write_artifact(preflight_dir, _SPEC_ATS_KEYWORDS.artifact, data, results, result, artifact_paths, log)

    # role_requirements ------------------------------------------------
    progress("Extracting role requirements")
    _t0, _started = time.monotonic(), datetime.now(timezone.utc).isoformat()
    data, result = _run_one(
        _SPEC_ROLE_REQUIREMENTS,
        cfg,
        client,
        local_messages=lambda text: _role_requirements_messages(text),
        source_text=jd_text,
        deterministic=lambda: deterministic_role_requirements(jd_text),
        validator=validate_role_requirements,
        log=log,
        health=health,
    )
    _stamp_timing(result, _t0, _started)
    _write_artifact(preflight_dir, _SPEC_ROLE_REQUIREMENTS.artifact, data, results, result, artifact_paths, log)
    requirements_for_plan = data

    # evidence_gap_plan ------------------------------------------------
    progress("Planning evidence gaps")
    _t0, _started = time.monotonic(), datetime.now(timezone.utc).isoformat()
    data, result = _run_one(
        _SPEC_EVIDENCE_GAP_PLAN,
        cfg,
        client,
        local_messages=lambda text: _evidence_gap_messages(text, evidence_files),
        source_text=jd_text,
        deterministic=lambda: deterministic_evidence_gap_plan(
            requirements_for_plan, evidence_files
        ),
        validator=validate_evidence_gap_plan,
        log=log,
        health=health,
    )
    _stamp_timing(result, _t0, _started)
    _write_artifact(preflight_dir, _SPEC_EVIDENCE_GAP_PLAN.artifact, data, results, result, artifact_paths, log)

    progress("Writing preflight analysis")

    fallback_used = any(r.fallback_used for r in results)
    fallback_reason = next(
        (r.fallback_reason for r in results if r.fallback_used and r.fallback_reason),
        None,
    )
    # Whether the local provider was actually contacted for at least one task
    # (task 133). Distinct from ``fallback_used``: a run can fall back without
    # ever issuing a local call (everything over budget), and a run can attempt
    # local and still fall back (timeout / bad output).
    local_attempted = any(r.local_attempted for r in results)

    # Surface "attempted but fell back" prominently in the run trace so an
    # operator does not have to reverse-engineer why a slow/wedged local model
    # (task 132) quietly produced deterministic artifacts (task 133).
    if local_attempted and fallback_used:
        marker = _local_fell_back_line(
            fallback_reason, health.degraded, health.skip_local
        )
        log(marker)
        progress(marker)

    created_at = (now or datetime.now(timezone.utc)).isoformat()
    manifest = {
        "created_at": created_at,
        "provider": primary_provider,
        "model": primary_model,
        "fallback_used": fallback_used,
        "tasks": [r.manifest_entry() for r in results],
    }
    if fallback_used and fallback_reason:
        manifest["fallback_reason"] = fallback_reason
    # Local-attempt / degradation signals are recorded only when the local
    # provider was the intended primary, so a deterministic-only run never gains
    # misleading "attempted" fields (task 133).
    if intended_local:
        manifest["local_attempted"] = local_attempted
        manifest["local_degraded"] = health.degraded
        manifest["local_skipped"] = health.skip_local
    if context_summary is not None:
        manifest["context"] = context_summary

    manifest_path = preflight_dir / PREFLIGHT_MANIFEST_FILENAME
    _write_json(manifest_path, manifest)
    log(f"wrote {_relpath(manifest_path, run_dir)}")
    artifact_paths[PREFLIGHT_MANIFEST_FILENAME] = manifest_path

    # Human-readable projection (optional, best effort).
    try:
        summary_md = render_preflight_summary(manifest, artifact_paths)
        summary_path = preflight_dir / PREFLIGHT_SUMMARY_FILENAME
        summary_path.write_text(summary_md, encoding="utf-8")
        artifact_paths[PREFLIGHT_SUMMARY_FILENAME] = summary_path
    except Exception:  # noqa: BLE001 - the md projection is non-essential
        pass

    return PreflightResult(
        preflight_dir=preflight_dir,
        provider=primary_provider,
        model=primary_model,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        tasks=results,
        manifest_path=manifest_path,
        artifact_paths=artifact_paths,
        local_degraded=health.degraded,
        local_skipped=health.skip_local,
    )


# ---- Per-task routing ------------------------------------------------


def _stamp_timing(
    result: PreflightTaskResult, monotonic_start: float, started_at: str
) -> None:
    """Record wall-clock timing on a task result for the provider trace."""
    result.duration_ms = int((time.monotonic() - monotonic_start) * 1000)
    result.started_at = started_at
    result.completed_at = datetime.now(timezone.utc).isoformat()


def _is_timeout(call: LLMCallResult) -> bool:
    """Whether a failed local call timed out (vs. a schema/other failure).

    A timeout is identified from the :class:`LLMCallResult` contract in
    :mod:`app.local_llm`: the call failed (``ok is False``) and its ``error``
    is the documented ``"timeout after Ns contacting ..."`` string. Ordinary
    schema-validation failures keep ``ok`` truthy (or carry a non-timeout
    error) and therefore do **not** count as a timeout (task 132).
    """
    return (
        not call.ok
        and isinstance(call.error, str)
        and call.error.startswith("timeout after")
    )


def _preflight_context_budget(cfg: LocalLLMConfig) -> ContextBudget:
    """Return the context budget preflight should use (task 132).

    Preflight budgets against a smaller default window than the general
    local-LLM default when the user has not explicitly configured
    ``context_window_tokens`` (detected by it still being the library default).
    An explicit user value — raised *or* lowered — is honoured verbatim; the
    smaller value is a default, not a cap. When the smaller default is applied,
    ``max_input_tokens`` is clamped to fit the reduced window so the budget
    stays valid; the over-budget handling (compression/fallback/abort) is
    unchanged.
    """
    if cfg.context_window_tokens != local_llm.DEFAULT_CONTEXT_WINDOW_TOKENS:
        # User explicitly set a context window: honour it exactly.
        return cfg.context_budget

    window = PREFLIGHT_DEFAULT_CONTEXT_WINDOW_TOKENS
    computed_max = window - cfg.reserved_output_tokens
    max_input = cfg.max_input_tokens
    if max_input is None or max_input > computed_max:
        max_input = computed_max
    return build_context_budget(window, cfg.reserved_output_tokens, max_input)


def _deterministic_result(
    spec: _TaskSpec,
    deterministic: Callable[[], dict[str, Any]],
    validator: Callable[[Any], tuple[Optional[dict[str, Any]], Optional[str]]],
    *,
    status: str = STATUS_SUCCEEDED,
    fallback_used: bool = False,
    fallback_reason: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], PreflightTaskResult]:
    """Build (and validate) a deterministic-extractor task result.

    The deterministic output is validated so a bug there surfaces as a failed
    task rather than a malformed artifact. Shared by every path that resolves a
    task to the deterministic floor (local disabled, budget fallback, post-call
    fallback, and the task-132 skip path).
    """
    data = deterministic()
    valid, det_reason = validator(data)
    if det_reason is not None or valid is None:
        raise PreflightError(
            f"deterministic {spec.name} produced invalid output: {det_reason}"
        )
    return valid, PreflightTaskResult(
        name=spec.name,
        provider=DETERMINISTIC_PROVIDER,
        model=None,
        status=status,
        output=_artifact_relpath(spec.artifact),
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        context=context,
    )


def _run_one(
    spec: _TaskSpec,
    cfg: LocalLLMConfig,
    client: Optional[LocalLLMClient],
    *,
    local_messages: Callable[[str], list[dict[str, str]]],
    source_text: str,
    deterministic: Callable[[], dict[str, Any]],
    validator: Callable[[Any], tuple[Optional[dict[str, Any]], Optional[str]]],
    log: Callable[[str], None],
    health: _ProviderHealth,
) -> tuple[dict[str, Any], PreflightTaskResult]:
    """Resolve one task to (artifact_data, task_result).

    Tries the local provider when permitted; validates the result; falls
    back to the deterministic extractor on any network/schema failure. The
    deterministic output is itself validated so a bug there surfaces as a
    failed task rather than a malformed artifact.

    ``health`` carries the per-run provider-degradation state (task 132): a
    local timeout marks the provider degraded, and once the run has seen the
    repeated-timeout threshold the local provider is skipped for this and every
    later task — routed straight to the deterministic floor. Skipping never
    raises; the deterministic path already guarantees a valid artifact.
    """
    use_local = client is not None and local_allowed_for_task(spec.policy_task, cfg)

    if use_local:
        # Repeated local timeouts already tripped the skip threshold this run:
        # bypass the local provider entirely instead of paying another timeout.
        if health.skip_local:
            log(
                f"jobapply: {LOCAL_SKIPPED_REASON}; using deterministic "
                f"{spec.name} extractor"
            )
            return _deterministic_result(
                spec,
                deterministic,
                validator,
                status=STATUS_FALLBACK,
                fallback_used=True,
                fallback_reason=LOCAL_SKIPPED_REASON,
            )

        messages, context_info, fallback_reason = _prepare_local_messages(
            spec,
            cfg,
            local_messages,
            source_text,
            log,
        )
        if fallback_reason is not None:
            return _deterministic_result(
                spec,
                deterministic,
                validator,
                status=STATUS_FALLBACK,
                fallback_used=True,
                fallback_reason=fallback_reason,
                context=context_info,
            )

        call = client.chat_json(
            messages,
            required_fields=list(spec.required_fields),
            task=spec.policy_task,
        )
        # A local call was actually issued: capture its performance record
        # (task 133) regardless of whether it ultimately validated. The prompt
        # token estimate reuses the figure already computed while budgeting.
        prompt_token_estimate = context_info.get("estimated_input_tokens_final")
        effective_timeout = cfg.effective_timeout_seconds
        if call.ok and call.schema_valid and call.parsed is not None:
            data, reason = validator(call.parsed)
            if reason is None and data is not None:
                return data, PreflightTaskResult(
                    name=spec.name,
                    provider=client.provider_id,
                    model=call.model,
                    status=STATUS_SUCCEEDED,
                    output=_artifact_relpath(spec.artifact),
                    context=context_info,
                    local_attempted=True,
                    prompt_token_estimate=prompt_token_estimate,
                    latency_ms=call.latency_ms,
                    effective_timeout_seconds=effective_timeout,
                )
            fallback_reason = f"local output failed schema validation: {reason}"
        else:
            # A timeout degrades the provider for the rest of the run; an
            # ordinary schema/parse failure does not (task 132).
            if _is_timeout(call):
                health.record_timeout()
            fallback_reason = (
                call.error
                or "local provider returned an invalid or unparseable response"
            )
        # Fall through to deterministic, recording that local was attempted (so
        # the manifest distinguishes "tried and degraded" from "never tried")
        # along with its performance record.
        data, result = _deterministic_result(
            spec,
            deterministic,
            validator,
            status=STATUS_SUCCEEDED,
            fallback_used=True,
            fallback_reason=fallback_reason,
            context=context_info,
        )
        result.local_attempted = True
        result.prompt_token_estimate = prompt_token_estimate
        result.latency_ms = call.latency_ms
        result.effective_timeout_seconds = effective_timeout
        return data, result

    # Deterministic is the intended provider (local disabled/not allowed).
    return _deterministic_result(spec, deterministic, validator)


def _prepare_local_messages(
    spec: _TaskSpec,
    cfg: LocalLLMConfig,
    message_builder: Callable[[str], list[dict[str, str]]],
    source_text: str,
    log: Callable[[str], None],
) -> tuple[list[dict[str, str]], dict[str, Any], Optional[str]]:
    # Preflight budgets against a smaller default context than the general
    # local-LLM default unless the user explicitly configured one (task 132).
    budget = _preflight_context_budget(cfg)
    messages = message_builder(source_text)
    initial = _check_messages(messages, budget=budget)
    context_info: dict[str, Any] = {
        "context_window_tokens": initial.context_window_tokens,
        "reserved_output_tokens": initial.reserved_output_tokens,
        "max_input_tokens": initial.max_input_tokens,
        # The context window JobApplicator budgeted this task against (task
        # 127). Tracks the effective preflight budget's window (task 132 lowers
        # the default), recorded under an explicit name so every task entry
        # carries an auditable record of the assumed context — even if the
        # budget plumbing changes later.
        "effective_assumed_context_tokens": budget.context_window_tokens,
        "estimated_input_tokens_initial": initial.estimated_input_tokens,
        "estimated_input_tokens_final": initial.estimated_input_tokens,
        "compression_used": False,
        "fallback_used": False,
        "over_budget": initial.over_budget,
    }
    # The Ollama server context requested for this run, when configured (task
    # 126/127). Recorded for audit only; it does not change the budget.
    if cfg.num_ctx is not None:
        context_info["requested_num_ctx"] = cfg.num_ctx
    if not initial.over_budget:
        log("jobapply: local LLM budget check passed")
        return messages, context_info, None

    log(
        "jobapply: local LLM input over budget for "
        f"{spec.name}: estimated {initial.estimated_input_tokens} > "
        f"{initial.max_input_tokens}"
    )

    final = initial
    if cfg.allow_compression:
        compressed = _compress_for_local_task(spec, source_text, budget.max_input_tokens)
        messages = message_builder(compressed)
        final = _check_messages(messages, budget=budget)
        context_info.update(
            {
                "estimated_input_tokens_final": final.estimated_input_tokens,
                "compression_used": True,
                "over_budget": final.over_budget,
            }
        )
        log(
            "jobapply: compressed input to "
            f"{final.estimated_input_tokens} estimated tokens"
        )

    if not final.over_budget:
        log("jobapply: local LLM budget check passed")
        return messages, context_info, None

    reason = "local LLM input remained over budget after compression"
    context_info["fallback_used"] = cfg.allow_fallback
    if cfg.allow_fallback:
        log(
            "jobapply: local LLM input over budget after compression; "
            f"using deterministic {spec.name} extractor"
        )
        return messages, context_info, reason
    if cfg.abort_on_over_budget:
        raise PreflightError(reason)
    raise PreflightError(
        "local LLM input over budget and neither fallback nor abort is enabled"
    )


def _check_messages(
    messages: list[dict[str, str]], *, budget: ContextBudget
) -> ContextBudgetCheck:
    prompt = "\n\n".join(
        f"{m.get('role', '')}: {m.get('content', '')}" for m in messages
    )
    return check_context_budget(prompt, budget)


def _write_artifact(
    preflight_dir: Path,
    filename: str,
    data: dict[str, Any],
    results: list[PreflightTaskResult],
    result: PreflightTaskResult,
    artifact_paths: dict[str, Path],
    log: Callable[[str], None],
) -> None:
    path = preflight_dir / filename
    _write_json(path, data)
    results.append(result)
    artifact_paths[filename] = path
    run_dir = preflight_dir.parent.parent
    log(f"wrote {_relpath(path, run_dir)}")


# ---- Local LLM prompts (budget-checked, JSON-only) -------------------


def _job_summary_messages(jd_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You extract a neutral structured summary of a single job "
                "posting. Use ONLY the provided text. Never infer company "
                "facts from outside knowledge. Reply with a single JSON "
                "object and nothing else."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract this JSON shape from the job posting. Use null for "
                "any field not stated in the text:\n"
                '{"company": null, "job_title": null, "location": null, '
                '"employment_type": null, "seniority": null, '
                '"role_family": null, "summary": "neutral 1-2 sentence '
                'summary", "source": "input/job_description.md"}\n\n'
                "JOB POSTING:\n" + jd_text
            ),
        },
    ]


def _ats_keywords_messages(jd_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You extract ATS keywords from a job description. Do NOT "
                "decide whether any candidate has a keyword. Classify each "
                "keyword's category as one of required, preferred, industry, "
                "responsibility, and priority as one of high, medium, low. "
                "Reply with a single JSON object and nothing else."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract ATS keywords as this JSON shape:\n"
                '{"target_company": null, "target_job_title": null, '
                '"keywords": [{"keyword": "...", "category": "required", '
                '"kind": "tool", "evidence": "exact phrase from JD", '
                '"priority": "high"}], "groups": {"required": [], '
                '"preferred": [], "tools": [], "domains": [], '
                '"responsibilities": []}}\n\n'
                "JOB DESCRIPTION:\n" + jd_text
            ),
        },
    ]


def _role_requirements_messages(jd_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You extract structured role requirements and "
                "responsibilities grounded ONLY in the job description. Do "
                "not add generic requirements that are not present. Reply "
                "with a single JSON object and nothing else."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract this JSON shape:\n"
                '{"requirements": [{"id": "req_001", "requirement": "...", '
                '"category": "technical", "importance": "required", '
                '"source_quote": "...", "keywords": []}], '
                '"responsibilities": [{"id": "resp_001", '
                '"responsibility": "...", "source_quote": "...", '
                '"keywords": []}], "screening_signals": []}\n\n'
                "JOB DESCRIPTION:\n" + jd_text
            ),
        },
    ]


def _evidence_gap_messages(
    jd_text: str, evidence_files: list[str]
) -> list[dict[str, str]]:
    files_block = "\n".join(f"- {f}" for f in evidence_files) or "- (none staged)"
    return [
        {
            "role": "system",
            "content": (
                "You produce a PRE-tailoring evidence gap PLAN. You may "
                "suggest where to look for evidence, but you must NOT claim "
                "any evidence exists — you have not read the evidence files. "
                "Reply with a single JSON object and nothing else."
            ),
        },
        {
            "role": "user",
            "content": (
                "Using the job description and the list of staged evidence "
                "files, produce this JSON shape. Only reference files from "
                "the provided list in candidate_evidence_files_to_check:\n"
                '{"likely_evidence_targets": [{"requirement_id": "req_001", '
                '"requirement": "...", "search_terms": [], '
                '"candidate_evidence_files_to_check": [], "notes": "..."}], '
                '"known_risks_before_tailoring": [{"gap": "...", '
                '"source": "job description requirement", '
                '"severity": "medium"}]}\n\n'
                "STAGED EVIDENCE FILES:\n" + files_block + "\n\n"
                "JOB DESCRIPTION:\n" + jd_text
            ),
        },
    ]


def _compress_for_local_task(
    spec: _TaskSpec, text: str, max_input_tokens: int
) -> str:
    """Deterministically reduce JD-like input while preserving requirements."""
    del spec
    max_chars = max(1200, max_input_tokens * 3)
    lines = text.splitlines()
    kept: list[str] = []
    seen: set[str] = set()

    important_terms = (
        "requirement",
        "qualification",
        "responsibilit",
        "preferred",
        "must",
        "python",
        "machine learning",
        "ml",
        "data",
        "cloud",
        "aws",
        "gcp",
        "azure",
        "docker",
        "kubernetes",
        "sql",
        "llm",
    )
    boilerplate_terms = (
        "equal opportunity",
        "privacy policy",
        "cookie",
        "terms of use",
        "all rights reserved",
        "we are an equal",
    )

    def add(line: str) -> None:
        cleaned = line.rstrip()
        key = cleaned.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        kept.append(cleaned)

    for line in lines[:40]:
        add(line)
    for line in lines:
        low = line.lower()
        if any(term in low for term in boilerplate_terms):
            continue
        if _heading_text(line) is not None or _bullet_text(line) is not None:
            add(line)
            continue
        if any(term in low for term in important_terms):
            add(line)
    for line in lines[-30:]:
        if any(term in line.lower() for term in boilerplate_terms):
            continue
        add(line)

    compact = "\n".join(kept).strip()
    if len(compact) <= max_chars:
        return compact

    head = compact[: max_chars // 2].rsplit("\n", 1)[0]
    tail = compact[-(max_chars // 2) :].split("\n", 1)[-1]
    return (
        f"{head}\n\n"
        "[deterministic compression: middle omitted for local LLM budget]\n\n"
        f"{tail}"
    ).strip()


# ---- Deterministic extractors ----------------------------------------


def deterministic_job_summary(jd_text: str) -> dict[str, Any]:
    """Parse company/title/location/summary from the JD text."""
    title, company = _parse_title_company(jd_text)
    location = _parse_meta_field(jd_text, "Location")
    employment_type = _parse_meta_field(jd_text, "Employment type") or _parse_meta_field(
        jd_text, "Application method"
    )
    seniority = None
    if title:
        m = _SENIORITY_RE.search(title)
        if m:
            seniority = m.group(1).title()
    body = _description_body(jd_text)
    summary = _first_sentences(body, max_chars=280) if body else None
    return {
        "company": company,
        "job_title": title,
        "location": location,
        "employment_type": employment_type,
        "seniority": seniority,
        "role_family": None,
        "summary": summary or (title or "Job posting"),
        "source": f"{INPUT_DIRNAME}/{JOB_DESCRIPTION_FILENAME}",
    }


def deterministic_ats_keywords(jd_text: str) -> dict[str, Any]:
    """Extract tool/domain keywords from the JD by vocabulary matching."""
    title, company = _parse_title_company(jd_text)
    sections = _section_map(jd_text)

    keywords: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(term: str, kind: str) -> None:
        category, priority = _classify_term(term, jd_text, sections)
        evidence = _evidence_snippet(term, jd_text)
        norm = term.lower()
        if norm in seen:
            return
        seen.add(norm)
        keywords.append(
            {
                "keyword": term,
                "category": category,
                "kind": kind,
                "evidence": evidence,
                "priority": priority,
            }
        )

    for tool in KNOWN_TOOLS:
        if _term_present(tool, jd_text):
            add(tool, "tool")
    for domain in KNOWN_DOMAINS:
        if _term_present(domain, jd_text):
            add(domain, "domain")

    required = [k["keyword"] for k in keywords if k["category"] == "required"]
    preferred = [k["keyword"] for k in keywords if k["category"] == "preferred"]
    tools = [k["keyword"] for k in keywords if k["kind"] == "tool"]
    domains = [k["keyword"] for k in keywords if k["kind"] == "domain"]
    responsibilities = _responsibility_phrases(sections)

    return {
        "target_company": company,
        "target_job_title": title,
        "keywords": keywords,
        "groups": {
            "required": required,
            "preferred": preferred,
            "tools": tools,
            "domains": domains,
            "responsibilities": responsibilities,
        },
    }


def deterministic_role_requirements(jd_text: str) -> dict[str, Any]:
    """Build requirements/responsibilities from headings + bullet blocks."""
    sections = _section_map(jd_text)

    requirements: list[dict[str, Any]] = []
    responsibilities: list[dict[str, Any]] = []

    req_idx = 1
    resp_idx = 1
    for section_kind, bullets in sections:
        for bullet in bullets:
            if section_kind == "responsibility":
                responsibilities.append(
                    {
                        "id": f"resp_{resp_idx:03d}",
                        "responsibility": bullet,
                        "source_quote": bullet,
                        "keywords": _keywords_in(bullet),
                    }
                )
                resp_idx += 1
            elif section_kind in ("required", "preferred"):
                requirements.append(
                    {
                        "id": f"req_{req_idx:03d}",
                        "requirement": bullet,
                        "category": "technical",
                        "importance": (
                            "required" if section_kind == "required" else "preferred"
                        ),
                        "source_quote": bullet,
                        "keywords": _keywords_in(bullet),
                    }
                )
                req_idx += 1

    screening_signals = [
        f"Evidence of {kw}"
        for kw in dict.fromkeys(
            kw for r in requirements for kw in r["keywords"]
        )
    ][:8]

    return {
        "requirements": requirements,
        "responsibilities": responsibilities,
        "screening_signals": screening_signals,
    }


def deterministic_evidence_gap_plan(
    role_requirements: dict[str, Any], evidence_files: list[str]
) -> dict[str, Any]:
    """Bridge requirements → where to look, without claiming evidence.

    This is a JD-only first pass: it names the staged evidence index files
    as candidates to check but never asserts that any file *contains*
    supporting evidence.
    """
    requirements = role_requirements.get("requirements", []) if isinstance(
        role_requirements, dict
    ) else []

    targets: list[dict[str, Any]] = []
    for req in requirements[:12]:
        keywords = req.get("keywords") or []
        targets.append(
            {
                "requirement_id": req.get("id", ""),
                "requirement": req.get("requirement", ""),
                "search_terms": keywords,
                "candidate_evidence_files_to_check": list(evidence_files),
                "notes": "Check staged evidence for support; not yet audited.",
            }
        )

    risks: list[dict[str, Any]] = []
    for req in requirements:
        if req.get("importance") == "required" and not (req.get("keywords")):
            risks.append(
                {
                    "gap": req.get("requirement", ""),
                    "source": "job description requirement",
                    "severity": "medium",
                }
            )

    return {
        "likely_evidence_targets": targets,
        "known_risks_before_tailoring": risks,
    }


# ---- Validators ------------------------------------------------------


def _require_dict(data: Any) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if not isinstance(data, dict):
        return None, "expected a JSON object at the top level"
    return data, None


def validate_job_summary(
    data: Any,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    obj, reason = _require_dict(data)
    if reason:
        return None, reason
    for key in ("company", "job_title", "summary", "source"):
        if key not in obj:
            return None, f"missing required field: {key}"
    if not isinstance(obj.get("summary"), str) or not obj["summary"].strip():
        return None, "summary must be a non-empty string"
    return obj, None


def validate_ats_keywords(
    data: Any,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    obj, reason = _require_dict(data)
    if reason:
        return None, reason
    for key in ("keywords", "groups"):
        if key not in obj:
            return None, f"missing required field: {key}"
    if not isinstance(obj["keywords"], list):
        return None, "keywords must be an array"
    for i, kw in enumerate(obj["keywords"]):
        if not isinstance(kw, dict):
            return None, f"keywords[{i}] must be an object"
        if not kw.get("keyword"):
            return None, f"keywords[{i}] missing keyword"
        category = kw.get("category")
        if category is not None and category not in KEYWORD_CATEGORIES:
            return None, f"keywords[{i}] invalid category: {category!r}"
        priority = kw.get("priority")
        if priority is not None and priority not in KEYWORD_PRIORITIES:
            return None, f"keywords[{i}] invalid priority: {priority!r}"
    if not isinstance(obj["groups"], dict):
        return None, "groups must be an object"
    return obj, None


def validate_role_requirements(
    data: Any,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    obj, reason = _require_dict(data)
    if reason:
        return None, reason
    if "requirements" not in obj:
        return None, "missing required field: requirements"
    if not isinstance(obj["requirements"], list):
        return None, "requirements must be an array"
    for i, req in enumerate(obj["requirements"]):
        if not isinstance(req, dict):
            return None, f"requirements[{i}] must be an object"
        if not req.get("id"):
            return None, f"requirements[{i}] missing id"
        if not req.get("requirement"):
            return None, f"requirements[{i}] missing requirement text"
    responsibilities = obj.get("responsibilities", [])
    if not isinstance(responsibilities, list):
        return None, "responsibilities must be an array"
    # Normalize the optional collections so downstream code can rely on them.
    obj.setdefault("responsibilities", [])
    obj.setdefault("screening_signals", [])
    return obj, None


def validate_evidence_gap_plan(
    data: Any,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    obj, reason = _require_dict(data)
    if reason:
        return None, reason
    if "likely_evidence_targets" not in obj:
        return None, "missing required field: likely_evidence_targets"
    if not isinstance(obj["likely_evidence_targets"], list):
        return None, "likely_evidence_targets must be an array"
    obj.setdefault("known_risks_before_tailoring", [])
    if not isinstance(obj["known_risks_before_tailoring"], list):
        return None, "known_risks_before_tailoring must be an array"
    return obj, None


def validate_manifest(
    data: Any,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    obj, reason = _require_dict(data)
    if reason:
        return None, reason
    for key in ("created_at", "provider", "fallback_used", "tasks"):
        if key not in obj:
            return None, f"missing required field: {key}"
    if not isinstance(obj["tasks"], list):
        return None, "tasks must be an array"
    for i, task in enumerate(obj["tasks"]):
        if not isinstance(task, dict):
            return None, f"tasks[{i}] must be an object"
        for key in ("name", "provider", "status", "output"):
            if key not in task:
                return None, f"tasks[{i}] missing {key}"
    return obj, None


# ---- Human-readable projection ---------------------------------------


def _local_fell_back_line(
    reason: Optional[str], degraded: bool, skipped: bool
) -> str:
    """Build the stable "attempted but fell back" trace/summary line (task 133).

    Used verbatim both in the run-trace callbacks and the human-readable
    summary so the marker phrasing stays identical for the frontend (task 134).
    """
    line = LOCAL_ATTEMPTED_FELL_BACK_MARKER
    if reason:
        line += f": {reason}"
    if skipped:
        line += " (local provider skipped after repeated timeouts)"
    elif degraded:
        line += " (local provider degraded)"
    return line


def render_preflight_summary(
    manifest: dict[str, Any], artifact_paths: dict[str, Path]
) -> str:
    lines = ["# Preflight Analysis", ""]
    lines.append(f"- Provider: {manifest.get('provider')}")
    if manifest.get("model"):
        lines.append(f"- Model: {manifest.get('model')}")
    lines.append(f"- Fallback used: {manifest.get('fallback_used')}")
    if manifest.get("fallback_reason"):
        lines.append(f"- Fallback reason: {manifest['fallback_reason']}")
    # When the local provider was tried and the run still fell back, make the
    # situation obvious at a glance (task 133).
    if manifest.get("local_attempted") and manifest.get("fallback_used"):
        lines.append(
            "- "
            + _local_fell_back_line(
                manifest.get("fallback_reason"),
                bool(manifest.get("local_degraded")),
                bool(manifest.get("local_skipped")),
            )
        )
    context = manifest.get("context")
    if isinstance(context, dict):
        assumed = context.get("assumed_context_tokens")
        server = context.get("server_reported_context_tokens")
        verified = context.get("context_verified")
        lines.append(f"- Assumed context: {assumed} tokens")
        if verified:
            lines.append(f"- Server-reported context: {server} tokens (verified)")
        else:
            lines.append("- Server-reported context: unverified")
    lines.append("")
    lines.append("## Tasks")
    for task in manifest.get("tasks", []):
        suffix = " (fallback)" if task.get("fallback_used") else ""
        lines.append(
            f"- {task.get('name')}: {task.get('status')} "
            f"via {task.get('provider')}{suffix} → {task.get('output')}"
        )
    lines.append("")
    lines.append(
        "These artifacts are advisory inputs to resume tailoring. The "
        "truthfulness/evidence contract still governs the final resume; "
        "if preflight conflicts with the job description, the job "
        "description wins."
    )
    lines.append("")
    return "\n".join(lines)


# ---- Text parsing helpers --------------------------------------------


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return ""


def _parse_title_company(jd_text: str) -> tuple[Optional[str], Optional[str]]:
    """Parse ``# {title} — {company}`` (the run-directory JD header)."""
    for line in jd_text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            heading = m.group(1).strip()
            # The run-directory writer joins title and company with " — ".
            for sep in (" — ", " – ", " - ", " @ "):
                if sep in heading:
                    title, company = heading.split(sep, 1)
                    return title.strip() or None, company.strip() or None
            return heading or None, None
    return None, None


def _parse_meta_field(jd_text: str, label: str) -> Optional[str]:
    pattern = re.compile(
        r"^\s*-\s*\*\*" + re.escape(label) + r":\*\*\s*(.+?)\s*$",
        re.IGNORECASE,
    )
    for line in jd_text.splitlines():
        m = pattern.match(line)
        if m:
            return m.group(1).strip() or None
    return None


def _description_body(jd_text: str) -> str:
    """Return text after a ``## Description`` heading, else the whole body."""
    lines = jd_text.splitlines()
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and "description" in m.group(1).lower():
            return "\n".join(lines[i + 1 :]).strip()
    # No explicit description heading: drop the title + metadata block.
    body_lines = [
        ln
        for ln in lines
        if not _HEADING_RE.match(ln) and not ln.strip().startswith("- **")
    ]
    return "\n".join(body_lines).strip()


def _first_sentences(text: str, *, max_chars: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    cut = flat[:max_chars]
    # Prefer to cut on a sentence boundary, else a word boundary.
    for boundary in (". ", "! ", "? "):
        idx = cut.rfind(boundary)
        if idx > 40:
            return cut[: idx + 1].strip()
    idx = cut.rfind(" ")
    return (cut[:idx] if idx > 0 else cut).strip() + "…"


def _section_map(jd_text: str) -> list[tuple[str, list[str]]]:
    """Group bullet lines under their nearest requirement-ish heading.

    Returns an ordered list of ``(section_kind, [bullet, ...])`` where
    ``section_kind`` is one of ``required`` / ``preferred`` /
    ``responsibility`` / ``other``. Bullets that appear before any
    recognized heading are dropped (they are usually company blurb).
    """
    result: list[tuple[str, list[str]]] = []
    current_kind = "other"
    current_bullets: list[str] = []

    def flush() -> None:
        nonlocal current_bullets
        if current_bullets:
            result.append((current_kind, current_bullets))
            current_bullets = []

    for line in jd_text.splitlines():
        heading = _heading_text(line)
        if heading is not None:
            flush()
            current_kind = _classify_heading(heading)
            continue
        bullet = _bullet_text(line)
        if bullet is not None:
            current_bullets.append(bullet)
    flush()
    return result


def _heading_text(line: str) -> Optional[str]:
    m = _HEADING_RE.match(line)
    if m:
        return m.group(1).strip()
    # Also treat a bare "Requirements:" style line as a heading.
    stripped = line.strip()
    if stripped.endswith(":") and len(stripped) <= 60 and not _bullet_text(line):
        low = stripped.lower()
        if any(
            h in low
            for h in _REQUIRED_HEADINGS + _PREFERRED_HEADINGS + _RESPONSIBILITY_HEADINGS
        ):
            return stripped[:-1].strip()
    return None


def _bullet_text(line: str) -> Optional[str]:
    m = _BULLET_RE.match(line)
    if m:
        return m.group(1).strip()
    return None


def _classify_heading(heading: str) -> str:
    low = heading.lower()
    if any(h in low for h in _PREFERRED_HEADINGS):
        return "preferred"
    if any(h in low for h in _RESPONSIBILITY_HEADINGS):
        return "responsibility"
    if any(h in low for h in _REQUIRED_HEADINGS):
        return "required"
    return "other"


def _classify_term(
    term: str, jd_text: str, sections: list[tuple[str, list[str]]]
) -> tuple[str, str]:
    """Classify a matched keyword's category/priority by where it appears."""
    low = term.lower()
    in_required = _term_in_section(low, sections, "required")
    in_preferred = _term_in_section(low, sections, "preferred")
    in_responsibility = _term_in_section(low, sections, "responsibility")
    if in_required:
        return "required", "high"
    if in_preferred:
        return "preferred", "medium"
    if in_responsibility:
        return "responsibility", "medium"
    return "industry", "low"


def _term_in_section(
    low_term: str, sections: list[tuple[str, list[str]]], kind: str
) -> bool:
    for section_kind, bullets in sections:
        if section_kind != kind:
            continue
        for bullet in bullets:
            if low_term in bullet.lower():
                return True
    return False


def _responsibility_phrases(sections: list[tuple[str, list[str]]]) -> list[str]:
    phrases: list[str] = []
    for section_kind, bullets in sections:
        if section_kind == "responsibility":
            phrases.extend(bullets)
    return phrases[:10]


def _term_present(term: str, text: str) -> bool:
    return re.search(
        r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
        text,
        re.IGNORECASE,
    ) is not None


def _evidence_snippet(term: str, jd_text: str) -> str:
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    for line in jd_text.splitlines():
        if pattern.search(line):
            cleaned = line.strip().lstrip("-*• ").strip()
            return cleaned[:200]
    return term


def _keywords_in(text: str) -> list[str]:
    found: list[str] = []
    for term in KNOWN_TOOLS + KNOWN_DOMAINS:
        if _term_present(term, text):
            found.append(term)
    # de-dupe preserving order
    return list(dict.fromkeys(found))


def _staged_evidence_files(input_dir: Path) -> list[str]:
    """Return staged evidence file paths to name in the gap plan.

    Prefers the staged ``input/evidence_sources/`` files (the index points
    at them); always includes the index itself plus the common bank/notes
    inputs that exist, so the plan can name where to look without auditing.
    """
    files: list[str] = []
    index = input_dir / EVIDENCE_SOURCES_INDEX_FILENAME
    if index.is_file():
        files.append(f"{INPUT_DIRNAME}/{EVIDENCE_SOURCES_INDEX_FILENAME}")
    sources_dir = input_dir / EVIDENCE_SOURCES_DIRNAME
    if sources_dir.is_dir():
        for path in sorted(sources_dir.iterdir()):
            if path.is_file() and path.suffix == ".md":
                files.append(
                    f"{INPUT_DIRNAME}/{EVIDENCE_SOURCES_DIRNAME}/{path.name}"
                )
    for name in ("evidence_bank.md", "project_notes.md"):
        if (input_dir / name).is_file():
            files.append(f"{INPUT_DIRNAME}/{name}")
    return files


def _artifact_relpath(filename: str) -> str:
    return f"{INPUT_DIRNAME}/{PREFLIGHT_DIRNAME}/{filename}"


def _relpath(path: Path, run_dir: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.name


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# ---- Task specs (defined after the helpers they reference) -----------

_SPEC_JOB_SUMMARY = _TaskSpec(
    name=TASK_NAME_JOB_SUMMARY,
    policy_task=TASK_JOB_SUMMARY,
    artifact=JOB_SUMMARY_FILENAME,
    required_fields=("company", "job_title", "summary"),
)
_SPEC_ATS_KEYWORDS = _TaskSpec(
    name=TASK_NAME_ATS_KEYWORDS,
    policy_task=TASK_ATS_KEYWORDS,
    artifact=ATS_KEYWORDS_FILENAME,
    required_fields=("keywords",),
)
_SPEC_ROLE_REQUIREMENTS = _TaskSpec(
    name=TASK_NAME_ROLE_REQUIREMENTS,
    policy_task=TASK_ROLE_REQUIREMENTS,
    artifact=ROLE_REQUIREMENTS_FILENAME,
    required_fields=("requirements",),
)
_SPEC_EVIDENCE_GAP_PLAN = _TaskSpec(
    name=TASK_NAME_EVIDENCE_GAP_PLAN,
    policy_task=TASK_EVIDENCE_GAP_PLAN,
    artifact=EVIDENCE_GAP_PLAN_FILENAME,
    required_fields=("likely_evidence_targets",),
)

_SPECS: tuple[_TaskSpec, ...] = (
    _SPEC_JOB_SUMMARY,
    _SPEC_ATS_KEYWORDS,
    _SPEC_ROLE_REQUIREMENTS,
    _SPEC_EVIDENCE_GAP_PLAN,
)
