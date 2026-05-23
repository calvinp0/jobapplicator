from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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


@dataclass(frozen=True)
class RunDirectoryInfo:
    run_id: str
    run_dir: Path
    prompt_hash: str
    input_hash: str


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
) -> RunDirectoryInfo:
    """Create a Claude Code run directory for the given inputs.

    Layout matches docs/contracts/claude_run_directory.md. Returns the new
    run_id, the absolute run directory, and the prompt/input hashes.
    """
    if job is None:
        raise RunDirectoryError("job is required")
    if master_resume is None:
        raise RunDirectoryError("master_resume is required")

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
        "input_files": file_hashes,
        "expected_outputs": list(EXPECTED_OUTPUTS),
        "prompt_hash": prompt_hash,
        "input_hash": input_hash,
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return RunDirectoryInfo(
        run_id=rid,
        run_dir=run_dir,
        prompt_hash=prompt_hash,
        input_hash=input_hash,
    )


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
