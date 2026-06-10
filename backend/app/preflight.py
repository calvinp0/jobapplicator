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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import local_llm
from .local_llm import (
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

# Bound the text we hand to a local model so a huge JD never blows the
# context window or leaks unbounded content over HTTP.
MAX_JD_CHARS = 12_000

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

    results: list[PreflightTaskResult] = []
    artifact_paths: dict[str, Path] = {}

    # job_summary -------------------------------------------------------
    progress("Summarizing job description")
    data, result = _run_one(
        _SPEC_JOB_SUMMARY,
        cfg,
        client,
        local_messages=_job_summary_messages(jd_text),
        deterministic=lambda: deterministic_job_summary(jd_text),
        validator=validate_job_summary,
    )
    _write_artifact(preflight_dir, _SPEC_JOB_SUMMARY.artifact, data, results, result, artifact_paths, log)

    # ats_keyword_extraction -------------------------------------------
    progress("Extracting ATS keywords")
    data, result = _run_one(
        _SPEC_ATS_KEYWORDS,
        cfg,
        client,
        local_messages=_ats_keywords_messages(jd_text),
        deterministic=lambda: deterministic_ats_keywords(jd_text),
        validator=validate_ats_keywords,
    )
    _write_artifact(preflight_dir, _SPEC_ATS_KEYWORDS.artifact, data, results, result, artifact_paths, log)

    # role_requirements ------------------------------------------------
    progress("Extracting role requirements")
    data, result = _run_one(
        _SPEC_ROLE_REQUIREMENTS,
        cfg,
        client,
        local_messages=_role_requirements_messages(jd_text),
        deterministic=lambda: deterministic_role_requirements(jd_text),
        validator=validate_role_requirements,
    )
    _write_artifact(preflight_dir, _SPEC_ROLE_REQUIREMENTS.artifact, data, results, result, artifact_paths, log)
    requirements_for_plan = data

    # evidence_gap_plan ------------------------------------------------
    progress("Planning evidence gaps")
    data, result = _run_one(
        _SPEC_EVIDENCE_GAP_PLAN,
        cfg,
        client,
        local_messages=_evidence_gap_messages(jd_text, evidence_files),
        deterministic=lambda: deterministic_evidence_gap_plan(
            requirements_for_plan, evidence_files
        ),
        validator=validate_evidence_gap_plan,
    )
    _write_artifact(preflight_dir, _SPEC_EVIDENCE_GAP_PLAN.artifact, data, results, result, artifact_paths, log)

    progress("Writing preflight analysis")

    fallback_used = any(r.fallback_used for r in results)
    fallback_reason = next(
        (r.fallback_reason for r in results if r.fallback_used and r.fallback_reason),
        None,
    )

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
    )


# ---- Per-task routing ------------------------------------------------


def _run_one(
    spec: _TaskSpec,
    cfg: LocalLLMConfig,
    client: Optional[LocalLLMClient],
    *,
    local_messages: list[dict[str, str]],
    deterministic: Callable[[], dict[str, Any]],
    validator: Callable[[Any], tuple[Optional[dict[str, Any]], Optional[str]]],
) -> tuple[dict[str, Any], PreflightTaskResult]:
    """Resolve one task to (artifact_data, task_result).

    Tries the local provider when permitted; validates the result; falls
    back to the deterministic extractor on any network/schema failure. The
    deterministic output is itself validated so a bug there surfaces as a
    failed task rather than a malformed artifact.
    """
    use_local = client is not None and local_allowed_for_task(spec.policy_task, cfg)

    if use_local:
        call = client.chat_json(
            local_messages,
            required_fields=list(spec.required_fields),
            task=spec.policy_task,
        )
        if call.ok and call.schema_valid and call.parsed is not None:
            data, reason = validator(call.parsed)
            if reason is None and data is not None:
                return data, PreflightTaskResult(
                    name=spec.name,
                    provider=client.provider_id,
                    model=call.model,
                    status=STATUS_SUCCEEDED,
                    output=_artifact_relpath(spec.artifact),
                )
            fallback_reason = f"local output failed schema validation: {reason}"
        else:
            fallback_reason = (
                call.error
                or "local provider returned an invalid or unparseable response"
            )
        # Fall through to deterministic, recording that local was intended.
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
            status=STATUS_SUCCEEDED,
            output=_artifact_relpath(spec.artifact),
            fallback_used=True,
            fallback_reason=fallback_reason,
        )

    # Deterministic is the intended provider (local disabled/not allowed).
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
        status=STATUS_SUCCEEDED,
        output=_artifact_relpath(spec.artifact),
    )


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


# ---- Local LLM prompts (bounded, JSON-only) --------------------------


def _bounded(jd_text: str) -> str:
    return jd_text[:MAX_JD_CHARS]


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
                "JOB POSTING:\n" + _bounded(jd_text)
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
                "JOB DESCRIPTION:\n" + _bounded(jd_text)
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
                "JOB DESCRIPTION:\n" + _bounded(jd_text)
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
                "JOB DESCRIPTION:\n" + _bounded(jd_text)
            ),
        },
    ]


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
