from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import ClaudeRun, ResumeVersion
from .resume_suggestions import (
    SuggestionError,
    load_suggestions_json,
    validate_suggestions_payload,
)


EXPECTED_OUTPUT_FILES = (
    "tailored_resume.docx",
    "tailored_resume.md",
    "tailored_resume.json",
    # Task 113: imported into ``ResumeVersion.suggestions_json`` for the
    # interactive review surface.
    "resume_suggestions.json",
    "change_log.md",
    "claim_audit.md",
    "ats_audit.md",
    # Required by the v2 tailoring contract; import re-validates it too.
    "recruiter_review.md",
)


class RunImportError(ValueError):
    """Raised when a completed run's outputs cannot be imported."""


@dataclass(frozen=True)
class RunImportResult:
    resume_version: ResumeVersion
    output_hash: str
    file_hashes: dict[str, str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json_object(path: Path) -> Optional[dict[str, Any]]:
    """Parse ``path`` as a JSON object, tolerating malformed/non-object data.

    The structured resume JSON is already validated by the deterministic
    renderer during the worker run, so import treats it as best-effort
    provenance: a parse failure here returns ``None`` rather than failing the
    import (which would block a run whose DOCX already rendered cleanly).
    """
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _resolve_inside(run_dir: Path, relative: str) -> Path:
    """Resolve ``relative`` against ``run_dir`` and assert it stays inside.

    Guards against symlinks or path components that would escape the run
    directory. Returns the resolved absolute path on success.
    """
    run_dir_resolved = run_dir.resolve()
    candidate = (run_dir / relative).resolve()
    try:
        candidate.relative_to(run_dir_resolved)
    except ValueError as exc:
        raise RunImportError(
            f"output file resolves outside the run directory: {relative}"
        ) from exc
    return candidate


def import_run_outputs(run_id: str, db: Session) -> RunImportResult:
    """Validate a completed Claude run and import its outputs.

    On success:

    - creates exactly one ``ResumeVersion`` row for ``(job_id, master_resume_id)``
      with the next ``version_number``, ``source="claude_run"``,
      ``approved_at=None``, paths/content for the generated artifacts, and
      output hashes.
    - sets ``claude_run.status = "imported"`` and records ``output_hash``
      on the run.

    Raises :class:`RunImportError` if the run is missing, not completed,
    or its outputs are missing / escape the run directory. Nothing is
    persisted on failure.
    """
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise RunImportError(f"claude run not found: {run_id}")

    if run.status != "completed":
        raise RunImportError(
            f"claude run {run_id} has status {run.status!r}; expected 'completed'"
        )

    run_dir = Path(run.run_dir)
    if not run_dir.is_dir():
        raise RunImportError(f"run directory does not exist: {run_dir}")

    # Validate every expected output file is present and inside the run dir.
    output_paths: dict[str, Path] = {}
    for filename in EXPECTED_OUTPUT_FILES:
        rel = f"output/{filename}"
        resolved = _resolve_inside(run_dir, rel)
        if not resolved.is_file():
            raise RunImportError(f"expected output file missing: {rel}")
        output_paths[filename] = resolved

    # Per-file SHA-256 and combined output_hash (sorted by filename, like input_hash).
    file_hashes: dict[str, str] = {}
    combined = hashlib.sha256()
    md_bytes: Optional[bytes] = None
    for filename in sorted(output_paths):
        data = output_paths[filename].read_bytes()
        file_hashes[filename] = _sha256_bytes(data)
        combined.update(filename.encode("utf-8"))
        combined.update(b"\0")
        combined.update(data)
        combined.update(b"\0")
        if filename == "tailored_resume.md":
            md_bytes = data
    output_hash = combined.hexdigest()

    # Next version_number for this (job, master_resume) pair.
    max_version = (
        db.query(func.max(ResumeVersion.version_number))
        .filter(
            ResumeVersion.job_id == run.job_id,
            ResumeVersion.master_resume_id == run.master_resume_id,
        )
        .scalar()
    )
    next_version = (max_version or 0) + 1

    content_markdown = md_bytes.decode("utf-8") if md_bytes is not None else None

    # Task 113: import the section-level suggestions and the base structured
    # resume so the interactive review surface has something to render and
    # the apply step can rebuild a working resume from accepted suggestions.
    try:
        suggestions_doc = validate_suggestions_payload(
            load_suggestions_json(output_paths["resume_suggestions.json"])
        )
    except SuggestionError as exc:
        raise RunImportError(f"invalid resume suggestions: {exc}") from exc
    base_resume = _load_json_object(output_paths["tailored_resume.json"])
    review_state = {
        "base_resume_json": base_resume,
        "working_resume_json": None,
        "applied_at": None,
    }

    version = ResumeVersion(
        job_id=run.job_id,
        master_resume_id=run.master_resume_id,
        claude_run_id=run.id,
        version_number=next_version,
        content_markdown=content_markdown,
        docx_path=str(output_paths["tailored_resume.docx"]),
        content_hash=file_hashes["tailored_resume.md"],
        prompt_hash=run.prompt_hash,
        source="claude_run",
        approved_at=None,
        suggestions_json=json.dumps(suggestions_doc),
        suggestion_review_state=json.dumps(review_state),
    )

    run.status = "imported"
    run.output_hash = output_hash

    db.add(version)
    db.commit()
    db.refresh(version)
    db.refresh(run)

    return RunImportResult(
        resume_version=version,
        output_hash=output_hash,
        file_hashes=file_hashes,
    )


def approve_resume_version(version_id: str, db: Session) -> ResumeVersion:
    """Mark a resume version approved. Idempotent on re-approval.

    The first call sets ``approved_at`` to now. Subsequent calls leave the
    timestamp untouched and return the existing row. Callers that want to
    detect re-approval can compare ``approved_at`` before and after.
    """
    version = db.get(ResumeVersion, version_id)
    if version is None:
        raise RunImportError(f"resume version not found: {version_id}")

    if version.approved_at is None:
        version.approved_at = _now()
        db.commit()
        db.refresh(version)
    return version
