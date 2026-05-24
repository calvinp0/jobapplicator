from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..claude_worker import (
    RUN_LOG_FILENAME,
    ClaudeWorkerError,
    invoke_claude_run,
    read_recent_log_lines,
)
from ..db import get_db
from ..models import ClaudeRun, EvidenceBank, Job, JobCapture, MasterResume
from ..run_directory import (
    RunDirectoryError,
    create_run_directory,
    default_candidate_context_root,
    default_runs_root,
    default_runtime_prompts_root,
)
from ..run_import import RunImportError, import_run_outputs
from ..schemas import (
    ClaudeRunCreate,
    ClaudeRunLogRead,
    ClaudeRunRead,
    ResumeVersionRead,
)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=ClaudeRunRead, status_code=status.HTTP_201_CREATED)
def create_run(payload: ClaudeRunCreate, db: Session = Depends(get_db)) -> ClaudeRun:
    job = db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    master_resume = db.get(MasterResume, payload.master_resume_id)
    if master_resume is None:
        raise HTTPException(status_code=404, detail="master resume not found")

    evidence_bank: EvidenceBank | None = None
    if payload.evidence_bank_id is not None:
        evidence_bank = db.get(EvidenceBank, payload.evidence_bank_id)
        if evidence_bank is None:
            raise HTTPException(status_code=404, detail="evidence bank not found")

    job_capture: JobCapture | None = None
    if job.created_from_capture_id:
        job_capture = db.get(JobCapture, job.created_from_capture_id)

    try:
        info = create_run_directory(
            job=job,
            master_resume=master_resume,
            evidence_bank=evidence_bank,
            candidate_context_root=default_candidate_context_root(),
            runs_root=default_runs_root(),
            runtime_prompts_root=default_runtime_prompts_root(),
            job_capture=job_capture,
        )
    except RunDirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run = ClaudeRun(
        id=info.run_id,
        job_id=job.id,
        master_resume_id=master_resume.id,
        evidence_bank_id=evidence_bank.id if evidence_bank is not None else None,
        run_dir=str(info.run_dir),
        status="created",
        prompt_hash=info.prompt_hash,
        input_hash=info.input_hash,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=list[ClaudeRunRead])
def list_runs(db: Session = Depends(get_db)) -> list[ClaudeRun]:
    return list(db.query(ClaudeRun).order_by(ClaudeRun.created_at.desc()).all())


@router.get("/{run_id}", response_model=ClaudeRunRead)
def get_run(run_id: str, db: Session = Depends(get_db)) -> ClaudeRun:
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="claude run not found")
    return run


@router.get("/{run_id}/log", response_model=ClaudeRunLogRead)
def get_run_log(run_id: str, db: Session = Depends(get_db)) -> ClaudeRunLogRead:
    """Return recent ``run.log`` lines for live progress polling.

    The log file is read directly from the run directory recorded on the
    ``ClaudeRun`` row, so this never escapes a run's own directory. An
    absent log file (run hasn't written anything yet) returns an empty list
    rather than a 404 so the polling UI can stay quiet.
    """
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="claude run not found")
    log_path = Path(run.run_dir) / RUN_LOG_FILENAME
    lines, truncated = read_recent_log_lines(log_path)
    return ClaudeRunLogRead(run_id=run.id, lines=lines, truncated=truncated)


@router.post("/{run_id}/invoke", response_model=ClaudeRunRead)
def invoke_run(run_id: str, db: Session = Depends(get_db)) -> ClaudeRun:
    try:
        return invoke_claude_run(run_id, db)
    except ClaudeWorkerError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/import", response_model=ResumeVersionRead, status_code=status.HTTP_201_CREATED)
def import_run(run_id: str, db: Session = Depends(get_db)):
    try:
        result = import_run_outputs(run_id, db)
    except RunImportError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc
    return result.resume_version
