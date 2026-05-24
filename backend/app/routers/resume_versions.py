from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
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

    master_resume = db.get(MasterResume, source_version.master_resume_id)
    if master_resume is None:
        raise HTTPException(
            status_code=404,
            detail="master resume not found for source resume version",
        )

    evidence_bank: EvidenceBank | None = None
    if source_version.claude_run_id is not None:
        prior_run = db.get(ClaudeRun, source_version.claude_run_id)
        if prior_run is not None and prior_run.evidence_bank_id is not None:
            evidence_bank = db.get(EvidenceBank, prior_run.evidence_bank_id)

    job_capture: JobCapture | None = None
    if job.created_from_capture_id:
        job_capture = db.get(JobCapture, job.created_from_capture_id)

    feedback_input = RevisionFeedbackInput(
        source_resume_version_id=version_id,
        feedback_markdown=payload.feedback_markdown,
        structured_flags=payload.structured_flags,
    )

    try:
        info = create_run_directory(
            job=job,
            master_resume=master_resume,
            evidence_bank=evidence_bank,
            candidate_context_root=default_candidate_context_root(),
            runs_root=default_runs_root(),
            runtime_prompts_root=default_runtime_prompts_root(),
            job_capture=job_capture,
            revision_feedback=feedback_input,
        )
    except RunDirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_run = ClaudeRun(
        id=info.run_id,
        job_id=job.id,
        master_resume_id=master_resume.id,
        evidence_bank_id=evidence_bank.id if evidence_bank is not None else None,
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
