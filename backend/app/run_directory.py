from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .llm_providers import (
    DEFAULT_PROVIDER_ID,
    WORD_HANDOFF_PROVIDER_ID,
    is_known_provider,
)
from .models import EvidenceBank, Job, JobCapture, MasterResume

CANDIDATE_CONTEXT_FILES = (
    "candidate_profile.md",
    "project_notes.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)

EXPECTED_OUTPUTS = (
    "tailored_resume.docx",
    "tailored_resume.md",
    "change_log.md",
    "claim_audit.md",
)

RUNTIME_PROMPT_FILENAME = "resume_tailoring.md"
REVISION_FEEDBACK_FILENAME = "revision_feedback.md"

METADATA_FILENAME = "metadata.json"

# Tailoring methods describe how a run will produce its tailored draft.
# ``auto`` is the existing Claude Code subprocess path. ``word_handoff``
# packages inputs for a manual/semi-automated Claude for Word edit and is
# implemented by a follow-up task — this module only persists the choice.
TAILORING_METHOD_AUTO = "auto"
TAILORING_METHOD_WORD_HANDOFF = "word_handoff"
ALLOWED_TAILORING_METHODS = (
    TAILORING_METHOD_AUTO,
    TAILORING_METHOD_WORD_HANDOFF,
)
DEFAULT_TAILORING_METHOD = TAILORING_METHOD_AUTO

# Run-level workflow statuses tracked in metadata.json. This is distinct
# from the DB-level ``ClaudeRun.status`` column, which tracks just the
# subprocess lifecycle. The metadata status spans both the auto path and
# the upcoming word_handoff path.
# Default LLM provider for the ``auto`` tailoring path. The router accepts an
# explicit override per run; this constant is the fallback when none is given
# (task 066 will replace it with a user-configurable setting).
DEFAULT_LLM_PROVIDER = DEFAULT_PROVIDER_ID

# Sentinel stamped into ``llm_provider`` when ``tailoring_method == word_handoff``.
# That flow never invokes a backend CLI, but the contract requires the field
# to be present so the metadata file stays self-describing.
WORD_HANDOFF_LLM_PROVIDER = WORD_HANDOFF_PROVIDER_ID

ALLOWED_RUN_STATUSES = (
    "created",
    "input_ready",
    "auto_tailoring_running",
    "auto_tailoring_failed",
    "auto_tailoring_complete",
    "word_handoff_ready",
    "waiting_for_word_result",
    "word_result_imported",
    "validation_failed",
    "completed",
    "failed",
)
DEFAULT_RUN_STATUS = "created"


@dataclass(frozen=True)
class RunDirectoryInfo:
    run_id: str
    run_dir: Path
    prompt_hash: str
    input_hash: str


@dataclass(frozen=True)
class RevisionFeedbackInput:
    """Inputs needed to stage ``input/revision_feedback.md`` on a follow-up run.

    Per ADR-008 the file carries the user's free-text feedback body plus an
    identifier for the source ``ResumeVersion`` and optional structured flags.
    """

    source_resume_version_id: str
    feedback_markdown: str
    structured_flags: Optional[dict[str, Any]] = field(default=None)


class RunDirectoryError(ValueError):
    """Raised when a run directory cannot be created from the provided inputs."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _read_candidate_file(candidate_root: Path, filename: str) -> str:
    src = candidate_root / filename
    if filename == "project_notes.md" and not src.exists():
        # Allow notes to be split across files under candidate_context/project_notes/
        notes_dir = candidate_root / "project_notes"
        if notes_dir.is_dir():
            parts: list[str] = []
            for note in sorted(notes_dir.iterdir()):
                if note.is_file() and note.suffix == ".md":
                    parts.append(note.read_text(encoding="utf-8"))
            return "\n\n".join(parts)
    if not src.exists():
        raise RunDirectoryError(
            f"required candidate context file not found: {src}"
        )
    return src.read_text(encoding="utf-8")


def _validate_tailoring_method(method: str) -> str:
    if method not in ALLOWED_TAILORING_METHODS:
        raise RunDirectoryError(
            "invalid tailoring_method: "
            f"{method!r}; allowed: {list(ALLOWED_TAILORING_METHODS)}"
        )
    return method


def _resolve_llm_provider(
    tailoring_method: str, llm_provider: Optional[str]
) -> str:
    """Decide which value to stamp into ``metadata.json``.

    Word-handoff runs always carry the ``claude_for_word`` sentinel
    because no backend CLI runs in that flow; any caller-supplied
    provider id is ignored. Auto runs default to ``claude_code`` and
    accept any id registered with the provider registry.
    """
    if tailoring_method == TAILORING_METHOD_WORD_HANDOFF:
        return WORD_HANDOFF_LLM_PROVIDER
    if llm_provider is None:
        return DEFAULT_LLM_PROVIDER
    if not is_known_provider(llm_provider):
        raise RunDirectoryError(
            f"invalid llm_provider: {llm_provider!r}"
        )
    return llm_provider


def _validate_run_status(status: str) -> str:
    if status not in ALLOWED_RUN_STATUSES:
        raise RunDirectoryError(
            "invalid run status: "
            f"{status!r}; allowed: {list(ALLOWED_RUN_STATUSES)}"
        )
    return status


def create_run_directory(
    job: Job,
    master_resume: MasterResume,
    evidence_bank: Optional[EvidenceBank],
    candidate_context_root: Path,
    runs_root: Path,
    runtime_prompts_root: Path,
    job_capture: Optional[JobCapture] = None,
    run_id: Optional[str] = None,
    now: Optional[datetime] = None,
    revision_feedback: Optional[RevisionFeedbackInput] = None,
    tailoring_method: str = DEFAULT_TAILORING_METHOD,
    llm_provider: Optional[str] = None,
    master_resume_docx_path: Optional[Path] = None,
) -> RunDirectoryInfo:
    """Create a Claude Code run directory for the given inputs.

    Layout matches docs/contracts/claude_run_directory.md. Returns the new
    run_id, the absolute run directory, and the prompt/input hashes.
    """
    if job is None:
        raise RunDirectoryError("job is required")
    if master_resume is None:
        raise RunDirectoryError("master_resume is required")
    _validate_tailoring_method(tailoring_method)
    resolved_llm_provider = _resolve_llm_provider(tailoring_method, llm_provider)

    candidate_root = Path(candidate_context_root)
    if not candidate_root.is_dir():
        raise RunDirectoryError(
            f"candidate_context_root does not exist: {candidate_root}"
        )

    prompts_root = Path(runtime_prompts_root)
    prompt_src = prompts_root / RUNTIME_PROMPT_FILENAME
    if not prompt_src.is_file():
        raise RunDirectoryError(
            f"runtime prompt not found: {prompt_src}"
        )

    runs_root = Path(runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)

    rid = run_id or str(uuid.uuid4())
    run_dir = runs_root / rid
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=False)

    # --- write input files ---
    _write_text(input_dir / "job_description.md", _format_job_description(job))
    _write_text(input_dir / "master_resume.md", master_resume.content_markdown)

    if master_resume_docx_path is not None:
        docx_src = Path(master_resume_docx_path)
        if not docx_src.is_file():
            raise RunDirectoryError(
                f"master_resume_docx_path does not exist: {docx_src}"
            )
        shutil.copyfile(docx_src, input_dir / "master_resume.docx")

    if evidence_bank is not None:
        _write_text(input_dir / "evidence_bank.md", evidence_bank.content_markdown)
    else:
        # Optional per contract; write an empty stub so the input set is uniform
        # and the prompt's read list does not 404.
        _write_text(
            input_dir / "evidence_bank.md",
            "# Evidence Bank\n\n(none provided)\n",
        )

    for filename in CANDIDATE_CONTEXT_FILES:
        content = _read_candidate_file(candidate_root, filename)
        _write_text(input_dir / filename, content)

    # Verbatim copy of the runtime prompt so prompt_hash matches the source.
    shutil.copyfile(prompt_src, input_dir / "tailoring_prompt.md")

    if revision_feedback is not None:
        _write_text(
            input_dir / REVISION_FEEDBACK_FILENAME,
            _render_revision_feedback(revision_feedback),
        )

    # --- hashes ---
    prompt_hash = _sha256_bytes((input_dir / "tailoring_prompt.md").read_bytes())

    input_files = sorted(p for p in input_dir.iterdir() if p.is_file())
    hasher = hashlib.sha256()
    file_hashes: dict[str, str] = {}
    for path in input_files:
        data = path.read_bytes()
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(data)
        hasher.update(b"\0")
        file_hashes[path.name] = _sha256_bytes(data)
    input_hash = hasher.hexdigest()

    # --- metadata ---
    created_at = (now or datetime.now(timezone.utc)).isoformat()
    capture_method = _resolve_capture_method(job, job_capture)

    metadata = {
        "run_id": rid,
        "job_id": job.id,
        "master_resume_id": master_resume.id,
        "evidence_bank_id": evidence_bank.id if evidence_bank is not None else None,
        "capture_method": capture_method,
        "created_at": created_at,
        "updated_at": created_at,
        "input_files": file_hashes,
        "expected_outputs": list(EXPECTED_OUTPUTS),
        "prompt_hash": prompt_hash,
        "input_hash": input_hash,
        "tailoring_method": tailoring_method,
        "llm_provider": resolved_llm_provider,
        "status": DEFAULT_RUN_STATUS,
    }
    _write_metadata(run_dir, metadata)

    return RunDirectoryInfo(
        run_id=rid,
        run_dir=run_dir,
        prompt_hash=prompt_hash,
        input_hash=input_hash,
    )


def _metadata_path(run_dir: Path) -> Path:
    return Path(run_dir) / METADATA_FILENAME


def _read_metadata(run_dir: Path) -> dict[str, Any]:
    path = _metadata_path(run_dir)
    if not path.is_file():
        raise RunDirectoryError(f"metadata.json not found in run directory: {run_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_metadata(run_dir: Path, metadata: dict[str, Any]) -> None:
    _metadata_path(run_dir).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _stamp_updated_at(metadata: dict[str, Any], now: Optional[datetime]) -> None:
    metadata["updated_at"] = (now or datetime.now(timezone.utc)).isoformat()


def get_tailoring_method(run_dir: Path) -> str:
    """Return the tailoring method recorded in metadata.json.

    Backwards compatibility: older runs created before this field existed
    are treated as ``auto`` (the only behavior the system ever had).
    """
    metadata = _read_metadata(run_dir)
    method = metadata.get("tailoring_method", DEFAULT_TAILORING_METHOD)
    # Don't silently coerce an unexpected value to the default — surface it
    # so the caller can decide. ``None`` (an explicit null) also falls back.
    if method is None:
        return DEFAULT_TAILORING_METHOD
    return method


def set_tailoring_method(
    run_dir: Path,
    method: str,
    *,
    now: Optional[datetime] = None,
) -> None:
    """Persist ``method`` as the run's tailoring method in metadata.json."""
    _validate_tailoring_method(method)
    metadata = _read_metadata(run_dir)
    metadata["tailoring_method"] = method
    _stamp_updated_at(metadata, now)
    _write_metadata(run_dir, metadata)


def get_llm_provider(run_dir: Path) -> str:
    """Return the llm provider recorded in metadata.json.

    Backwards compatibility: pre-registry runs have no ``llm_provider``
    key; readers must treat that as ``claude_code`` since that was the
    only worker the system supported.
    """
    metadata = _read_metadata(run_dir)
    value = metadata.get("llm_provider", DEFAULT_LLM_PROVIDER)
    if value is None:
        return DEFAULT_LLM_PROVIDER
    return value


def get_run_status(run_dir: Path) -> str:
    """Return the workflow status recorded in metadata.json.

    Older metadata that predates the status field is reported as
    ``created`` to keep callers from having to special-case missing keys.
    """
    metadata = _read_metadata(run_dir)
    return metadata.get("status", DEFAULT_RUN_STATUS) or DEFAULT_RUN_STATUS


def set_run_status(
    run_dir: Path,
    status: str,
    *,
    now: Optional[datetime] = None,
) -> None:
    """Persist ``status`` as the run's workflow status in metadata.json."""
    _validate_run_status(status)
    metadata = _read_metadata(run_dir)
    metadata["status"] = status
    _stamp_updated_at(metadata, now)
    _write_metadata(run_dir, metadata)


def _render_revision_feedback(feedback: RevisionFeedbackInput) -> str:
    """Render the contents of ``input/revision_feedback.md`` per ADR-008.

    The rendered file uses a small frontmatter block to surface the source
    ResumeVersion id (and structured flags, when provided) so the worker
    prompt can reference them distinctly from the free-text feedback body.
    """
    lines = ["---", f"source_resume_version_id: {feedback.source_resume_version_id}"]
    if feedback.structured_flags is not None:
        lines.append(
            "structured_flags: "
            + json.dumps(feedback.structured_flags, sort_keys=True)
        )
    lines.append("---")
    lines.append("")
    body = feedback.feedback_markdown.rstrip()
    if body:
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


def _format_job_description(job: Job) -> str:
    header_lines = [
        f"# {job.title} — {job.company}",
        "",
    ]
    meta = [
        ("Source platform", job.source_platform),
        ("External URL", job.external_url),
        ("External job ID", job.external_job_id),
        ("Location", job.location),
        ("Application method", job.application_method),
    ]
    for label, value in meta:
        if value:
            header_lines.append(f"- **{label}:** {value}")
    header_lines.extend(["", "## Description", "", job.description_text.rstrip(), ""])
    return "\n".join(header_lines)


def _resolve_capture_method(job: Job, job_capture: Optional[JobCapture]) -> str:
    if job_capture is not None and job_capture.capture_method:
        return job_capture.capture_method
    if job.application_method:
        return job.application_method
    return job.source_platform or "unknown"


# --- runtime path resolution (used by the router) ---

def _project_root() -> Path:
    # backend/app/run_directory.py -> backend/app -> backend -> project root
    return Path(__file__).resolve().parents[2]


def default_candidate_context_root() -> Path:
    return Path(
        os.environ.get(
            "JOBAPPLY_CANDIDATE_CONTEXT_ROOT",
            str(_project_root() / "candidate_context"),
        )
    )


def default_runs_root() -> Path:
    return Path(
        os.environ.get(
            "JOBAPPLY_RUNS_ROOT",
            str(_project_root() / "runs"),
        )
    )


def default_runtime_prompts_root() -> Path:
    return Path(
        os.environ.get(
            "JOBAPPLY_RUNTIME_PROMPTS_ROOT",
            str(_project_root() / "runtime_prompts"),
        )
    )


def default_resume_versions_root() -> Path:
    return Path(
        os.environ.get(
            "JOBAPPLY_RESUME_VERSIONS_ROOT",
            str(_project_root() / "resume_versions"),
        )
    )
