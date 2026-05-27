from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..claude_worker import (
    OUTPUT_DIRNAME,
    PROGRESS_RELPATH,
    RECRUITER_REVIEW_FILENAME,
    RUN_LOG_FILENAME,
    ClaudeWorkerError,
    invoke_claude_run,
    read_progress_lines,
    read_recent_log_lines,
)
from ..db import get_db
from ..evidence_source_discovery import (
    EvidenceSourceDiscoveryError,
    is_filesystem_id as is_filesystem_evidence_id,
    load_filesystem_evidence_text,
    resolve_filesystem_evidence_source,
)
from ..llm_providers import is_known_provider, list_providers
from ..master_resume_discovery import (
    MasterResumeDiscoveryError,
    is_filesystem_id,
    load_filesystem_master_resume_text,
    resolve_filesystem_master_resume,
)
from ..models import ClaudeRun, EvidenceBank, Job, JobCapture, MasterResume
from ..run_directory import (
    EvidenceSourceInput,
    RunDirectoryError,
    create_run_directory,
    default_candidate_context_root,
    default_runs_root,
    default_runtime_prompts_root,
)
from ..run_import import RunImportError, import_run_outputs
from ..settings import get_default_llm_provider
from ..schemas import (
    ClaudeRunCreate,
    ClaudeRunLogRead,
    ClaudeRunProgressRead,
    ClaudeRunRead,
    ClaudeRunRecruiterReviewRead,
    ResumeVersionRead,
)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=ClaudeRunRead, status_code=status.HTTP_201_CREATED)
def create_run(payload: ClaudeRunCreate, db: Session = Depends(get_db)) -> ClaudeRun:
    job = db.get(Job, payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    master_resume_docx_path = None
    if is_filesystem_id(payload.master_resume_id):
        fs_record = resolve_filesystem_master_resume(payload.master_resume_id)
        if fs_record is None:
            raise HTTPException(
                status_code=404, detail="master resume not found"
            )
        try:
            content = load_filesystem_master_resume_text(fs_record)
        except MasterResumeDiscoveryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"failed to load master resume: {exc}",
            ) from exc
        # Build an unattached MasterResume so create_run_directory can read
        # ``id`` and ``content_markdown`` without us having to widen the
        # function's contract. The row is never added to the session — the
        # filesystem is the source of truth for these resumes.
        master_resume = MasterResume(
            id=fs_record.id,
            name=fs_record.name,
            source_path=fs_record.source_path,
            content_markdown=content,
        )
        if fs_record.source_format == "docx":
            master_resume_docx_path = fs_record.absolute_path
    else:
        master_resume = db.get(MasterResume, payload.master_resume_id)
        if master_resume is None:
            raise HTTPException(status_code=404, detail="master resume not found")

    evidence_bank: EvidenceBank | None = None
    if payload.evidence_bank_id is not None:
        evidence_bank = db.get(EvidenceBank, payload.evidence_bank_id)
        if evidence_bank is None:
            raise HTTPException(status_code=404, detail="evidence bank not found")

    # Resolve every id in ``evidence_source_ids`` to a stageable record.
    # The legacy ``evidence_bank_id`` is folded in as the leading entry
    # when present so both fields can coexist without surprising the
    # caller — see ``ClaudeRunCreate`` for the contract.
    resolved_evidence_sources: list[EvidenceSourceInput] = []
    requested_ids: list[str] = []
    if evidence_bank is not None:
        requested_ids.append(evidence_bank.id)
    for sid in payload.evidence_source_ids or []:
        if sid not in requested_ids:
            requested_ids.append(sid)

    seen_ids: set[str] = set()
    for sid in requested_ids:
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
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
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"failed to load evidence source {sid}: {exc}",
                ) from exc
            resolved_evidence_sources.append(
                EvidenceSourceInput(
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
            )
        else:
            db_bank = (
                evidence_bank
                if evidence_bank is not None and evidence_bank.id == sid
                else db.get(EvidenceBank, sid)
            )
            if db_bank is None:
                raise HTTPException(
                    status_code=404, detail=f"evidence source not found: {sid}"
                )
            resolved_evidence_sources.append(
                EvidenceSourceInput(
                    id=db_bank.id,
                    name=db_bank.name,
                    source_type="evidence_bank",
                    source_format="md",
                    source="database",
                    source_path=db_bank.source_path,
                    content=db_bank.content_markdown,
                    docx_path=None,
                )
            )

    job_capture: JobCapture | None = None
    if job.created_from_capture_id:
        job_capture = db.get(JobCapture, job.created_from_capture_id)

    # Validate the provider against the registry before touching the
    # filesystem so an unknown id never leaves a half-created run on disk.
    # Omitting the field falls back to the persisted app-wide default
    # (``app_settings.default_llm_provider``); on a fresh DB that is
    # ``claude_code`` per ADR-009.
    provider_id = payload.llm_provider or get_default_llm_provider()
    if not is_known_provider(provider_id):
        known = ", ".join(p.id for p in list_providers())
        raise HTTPException(
            status_code=400,
            detail=f"unknown llm_provider: {provider_id!r}; known: {known}",
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
            llm_provider=provider_id,
            master_resume_docx_path=master_resume_docx_path,
            evidence_sources=resolved_evidence_sources,
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
        llm_provider=provider_id,
        prompt_hash=info.prompt_hash,
        input_hash=info.input_hash,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    # Attach the resolved evidence source ids as a transient attribute
    # so the response schema can echo what was staged. The list lives in
    # the run's ``metadata.json`` (the source of truth); the DB row keeps
    # only the legacy single ``evidence_bank_id`` to avoid a migration.
    run.evidence_source_ids = [s.id for s in resolved_evidence_sources]
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


@router.get("/{run_id}/progress", response_model=ClaudeRunProgressRead)
def get_run_progress(
    run_id: str, db: Session = Depends(get_db)
) -> ClaudeRunProgressRead:
    """Return recent user-facing progress lines for the live progress panel.

    Reads ``progress/progress.log`` inside the run directory. The file
    contains plain-language phase events written by Claude during the run
    and worker heartbeats (when Claude is silent). Returns an empty list
    when the file is absent so the UI can fall back to the technical log
    or its waiting state.
    """
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="claude run not found")
    progress_path = Path(run.run_dir) / PROGRESS_RELPATH
    lines, truncated = read_progress_lines(progress_path)
    return ClaudeRunProgressRead(
        run_id=run.id, lines=lines, truncated=truncated
    )


@router.get(
    "/{run_id}/recruiter-review",
    response_model=ClaudeRunRecruiterReviewRead,
)
def get_run_recruiter_review(
    run_id: str, db: Session = Depends(get_db)
) -> ClaudeRunRecruiterReviewRead:
    """Return the recruiter review markdown for a run, when present.

    The recruiter review is produced as ``output/recruiter_review.md``
    inside the run directory. The file is requested but not strictly
    required by the worker today (task 108), so callers must handle the
    "not yet written" case — the endpoint reports ``available=False``
    rather than returning 404, which lets the UI render a hint instead
    of an error.
    """
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="claude run not found")
    review_relpath = f"{OUTPUT_DIRNAME}/{RECRUITER_REVIEW_FILENAME}"
    review_path = Path(run.run_dir) / OUTPUT_DIRNAME / RECRUITER_REVIEW_FILENAME
    if not review_path.is_file():
        return ClaudeRunRecruiterReviewRead(
            run_id=run.id, available=False, content=None, path=None
        )
    try:
        content = review_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to read recruiter review: {exc}",
        ) from exc
    return ClaudeRunRecruiterReviewRead(
        run_id=run.id,
        available=True,
        content=content,
        path=review_relpath,
    )


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
