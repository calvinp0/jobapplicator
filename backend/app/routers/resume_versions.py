from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..evidence_source_discovery import (
    EvidenceSourceDiscoveryError,
    is_filesystem_id as is_filesystem_evidence_id,
    load_filesystem_evidence_text,
    resolve_filesystem_evidence_source,
)
from ..master_resume_discovery import (
    MasterResumeDiscoveryError,
    is_filesystem_id as is_filesystem_master_id,
    load_filesystem_master_resume_text,
    resolve_filesystem_master_resume,
)
from ..models import (
    ClaudeRun,
    EvidenceBank,
    Job,
    JobCapture,
    MasterResume,
    ResumeVersion,
    RevisionFeedback,
)
from ..run_directory import (
    EvidenceSourceInput,
    RevisionFeedbackInput,
    RunDirectoryError,
    create_run_directory,
    default_candidate_context_root,
    default_runs_root,
    default_runtime_prompts_root,
)
from ..run_import import RunImportError, approve_resume_version
from ..schemas import (
    RevisionFeedbackCreate,
    RevisionFeedbackRead,
    ResumeVersionRead,
)

router = APIRouter(prefix="/resume-versions", tags=["resume-versions"])


@router.get("", response_model=list[ResumeVersionRead])
def list_resume_versions(db: Session = Depends(get_db)) -> list[ResumeVersion]:
    return list(
        db.query(ResumeVersion).order_by(ResumeVersion.created_at.desc()).all()
    )


@router.get("/{version_id}", response_model=ResumeVersionRead)
def get_resume_version(version_id: str, db: Session = Depends(get_db)) -> ResumeVersion:
    version = db.get(ResumeVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="resume version not found")
    return version


@router.post("/{version_id}/approve", response_model=ResumeVersionRead)
def approve_version(version_id: str, db: Session = Depends(get_db)) -> ResumeVersion:
    try:
        return approve_resume_version(version_id, db)
    except RunImportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _resolve_master_resume(
    master_resume_id: str,
) -> tuple[Optional[MasterResume], Optional[Path]]:
    """Resolve a master resume id from the filesystem discovery layer.

    Returns a pair ``(master_resume, docx_path)``. ``master_resume`` is an
    unattached ORM object built from the discovered file so downstream
    code can read ``id`` and ``content_markdown`` without caring whether
    the resume is database- or filesystem-backed. ``docx_path`` is set
    only when the discovered file is a ``.docx`` so the run directory can
    stage the verbatim DOCX alongside the markdown projection.
    """
    if not is_filesystem_master_id(master_resume_id):
        return None, None
    fs_record = resolve_filesystem_master_resume(master_resume_id)
    if fs_record is None:
        return None, None
    try:
        content = load_filesystem_master_resume_text(fs_record)
    except MasterResumeDiscoveryError:
        return None, None
    master_resume = MasterResume(
        id=fs_record.id,
        name=fs_record.name,
        source_path=fs_record.source_path,
        content_markdown=content,
    )
    docx_path = (
        fs_record.absolute_path if fs_record.source_format == "docx" else None
    )
    return master_resume, docx_path


def _resolve_evidence_source(
    sid: str,
    db: Session,
) -> EvidenceSourceInput:
    """Resolve a single evidence source id to a stageable input record.

    Mirrors the resolution rules from ``routers/runs.py`` so a revision
    run gets the same evidence input shape as the run that produced the
    source draft.
    """
    if is_filesystem_evidence_id(sid):
        fs_record = resolve_filesystem_evidence_source(sid)
        if fs_record is None:
            raise HTTPException(
                status_code=404, detail=f"evidence source not found: {sid}"
            )
        try:
            content = load_filesystem_evidence_text(fs_record)
        except EvidenceSourceDiscoveryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return EvidenceSourceInput(
            id=fs_record.id,
            name=fs_record.name,
            source_type=fs_record.source_type,
            source_format=fs_record.source_format,
            source="filesystem",
            source_path=fs_record.source_path,
            content=content,
            docx_path=(
                fs_record.absolute_path
                if fs_record.source_format == "docx"
                else None
            ),
        )
    db_bank = db.get(EvidenceBank, sid)
    if db_bank is None:
        raise HTTPException(
            status_code=404, detail=f"evidence source not found: {sid}"
        )
    return EvidenceSourceInput(
        id=db_bank.id,
        name=db_bank.name,
        source_type="evidence_bank",
        source_format="md",
        source="database",
        source_path=db_bank.source_path,
        content=db_bank.content_markdown,
        docx_path=None,
    )


def _original_evidence_source_ids(prior_run: Optional[ClaudeRun]) -> list[str]:
    """Recover the evidence source id list from the prior run.

    Multi-source selections live in the run's ``metadata.json`` (the DB
    row only carries the legacy single ``evidence_bank_id``). Fall back
    to the bank id when metadata is missing so legacy runs created
    before multi-source landed still produce a usable revision context.
    """
    if prior_run is None:
        return []
    metadata_path = Path(prior_run.run_dir) / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        ids = metadata.get("evidence_source_ids")
        if isinstance(ids, list) and ids:
            return [str(i) for i in ids]
    if prior_run.evidence_bank_id:
        return [prior_run.evidence_bank_id]
    return []


@router.post(
    "/{version_id}/revision-feedback",
    response_model=RevisionFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
def create_revision_feedback(
    version_id: str,
    payload: RevisionFeedbackCreate,
    db: Session = Depends(get_db),
) -> RevisionFeedback:
    """Submit revision feedback against a prior draft and stage a follow-up run.

    Per ADR-008 this endpoint performs three actions atomically from the
    caller's perspective: insert the ``revision_feedbacks`` row, create a
    new ``ClaudeRun`` linked back via ``followup_claude_run_id``, and write
    ``runs/<run_id>/input/revision_feedback.md`` into the new run directory.

    Per task 091 the new run directory also carries the full provenance
    of the source draft so the worker can revise it rather than blindly
    regenerating: the master resume (markdown and optionally DOCX), the
    original evidence sources used by the source run, and the current
    tailored draft (markdown and optionally DOCX). Additional evidence
    selected during revision is merged into the staged set.
    """
    source_version = db.get(ResumeVersion, version_id)
    if source_version is None:
        raise HTTPException(status_code=404, detail="resume version not found")

    job = db.get(Job, source_version.job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="job not found for source resume version",
        )

    # Resolve the master resume through the DB first, falling back to the
    # filesystem discovery layer. ``ClaudeRun.master_resume_id`` may be a
    # synthetic ``fs:<hash>`` id when the source run was created from a
    # discovered DOCX/markdown file, so a missing DB row is not by itself
    # a failure.
    master_resume = db.get(MasterResume, source_version.master_resume_id)
    master_resume_docx_path: Optional[Path] = None
    if master_resume is None:
        master_resume, master_resume_docx_path = _resolve_master_resume(
            source_version.master_resume_id
        )
    if master_resume is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "revision_missing_master_resume",
                "message": (
                    "This draft cannot be revised because its source master "
                    "resume record is missing. Regenerate the draft or "
                    "relink a master resume."
                ),
                "source_resume_version_id": version_id,
                "master_resume_id": source_version.master_resume_id,
            },
        )

    # Recover original evidence context from the prior run. ``prior_run``
    # may be None on very old drafts that predate the claude_run_id link;
    # in that case we still build a working revision context with no
    # original evidence — the user can add evidence via
    # ``additional_evidence_source_ids``.
    prior_run: Optional[ClaudeRun] = None
    legacy_evidence_bank: Optional[EvidenceBank] = None
    if source_version.claude_run_id is not None:
        prior_run = db.get(ClaudeRun, source_version.claude_run_id)
        if prior_run is not None and prior_run.evidence_bank_id is not None:
            legacy_evidence_bank = db.get(EvidenceBank, prior_run.evidence_bank_id)

    original_ids = _original_evidence_source_ids(prior_run)
    additional_ids = list(payload.additional_evidence_source_ids or [])

    seen_ids: set[str] = set()
    resolved_evidence_sources: list[EvidenceSourceInput] = []
    for sid in [*original_ids, *additional_ids]:
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        resolved_evidence_sources.append(_resolve_evidence_source(sid, db))

    job_capture: JobCapture | None = None
    if job.created_from_capture_id:
        job_capture = db.get(JobCapture, job.created_from_capture_id)

    # Stage the current tailored draft so the worker can revise it
    # instead of regenerating from scratch.
    current_md = source_version.content_markdown
    current_docx_path: Optional[Path] = None
    if source_version.docx_path:
        candidate = Path(source_version.docx_path)
        if candidate.is_file():
            current_docx_path = candidate

    feedback_input = RevisionFeedbackInput(
        source_resume_version_id=version_id,
        feedback_markdown=payload.feedback_markdown,
        structured_flags=payload.structured_flags,
        additional_evidence_source_ids=additional_ids or None,
    )

    try:
        info = create_run_directory(
            job=job,
            master_resume=master_resume,
            evidence_bank=legacy_evidence_bank,
            candidate_context_root=default_candidate_context_root(),
            runs_root=default_runs_root(),
            runtime_prompts_root=default_runtime_prompts_root(),
            job_capture=job_capture,
            revision_feedback=feedback_input,
            master_resume_docx_path=master_resume_docx_path,
            evidence_sources=resolved_evidence_sources,
            current_tailored_resume_markdown=current_md,
            current_tailored_resume_docx_path=current_docx_path,
        )
    except RunDirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_run = ClaudeRun(
        id=info.run_id,
        job_id=job.id,
        master_resume_id=master_resume.id,
        evidence_bank_id=(
            legacy_evidence_bank.id if legacy_evidence_bank is not None else None
        ),
        run_dir=str(info.run_dir),
        status="created",
        prompt_hash=info.prompt_hash,
        input_hash=info.input_hash,
    )
    db.add(new_run)
    db.flush()

    feedback = RevisionFeedback(
        job_id=job.id,
        source_resume_version_id=version_id,
        followup_claude_run_id=new_run.id,
        feedback_markdown=payload.feedback_markdown,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback
