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
from ..resume_docx_renderer import RendererError, render_resume, validate_resume_payload
from ..resume_suggestions import (
    apply_accepted,
    find_suggestion,
)
from ..run_import import RunImportError, approve_resume_version
from ..schemas import (
    ApplySuggestionsRead,
    ResumeSuggestionRead,
    ResumeSuggestionsRead,
    RevisionFeedbackCreate,
    RevisionFeedbackRead,
    ResumeVersionRead,
    SuggestionReviseRequest,
)
from datetime import datetime, timezone

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


# ---- Interactive resume suggestion review (task 113) ----


def _load_version_or_404(version_id: str, db: Session) -> ResumeVersion:
    version = db.get(ResumeVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="resume version not found")
    return version


def _load_suggestions_doc_or_404(version: ResumeVersion) -> dict:
    """Decode the suggestions document or 404 when the draft has none.

    Drafts produced before task 113 (or one-shot imports without a
    suggestions artifact) carry a null ``suggestions_json`` — the review
    surface is simply unavailable for them.
    """
    doc = version.suggestions
    if not doc or not isinstance(doc.get("suggestions"), list):
        raise HTTPException(
            status_code=404,
            detail="no resume suggestions available for this version",
        )
    return doc


def _suggestions_read(version: ResumeVersion, doc: dict) -> ResumeSuggestionsRead:
    review_state = version.review_state or {}
    base_resume = review_state.get("base_resume_json")
    working_resume = review_state.get("working_resume_json")
    return ResumeSuggestionsRead(
        resume_version_id=version.id,
        target_company=doc.get("target_company", "") or "",
        target_job_title=doc.get("target_job_title", "") or "",
        suggestions=[ResumeSuggestionRead(**s) for s in doc.get("suggestions", [])],
        applied_at=review_state.get("applied_at"),
        has_working_resume=bool(working_resume),
        base_resume=base_resume if isinstance(base_resume, dict) else None,
        working_resume=working_resume if isinstance(working_resume, dict) else None,
    )


def _set_suggestion_status(
    version_id: str,
    suggestion_id: str,
    status_value: str,
    db: Session,
    *,
    revision_instruction: Optional[str] = None,
) -> ResumeSuggestionRead:
    version = _load_version_or_404(version_id, db)
    doc = _load_suggestions_doc_or_404(version)
    suggestion = find_suggestion(doc, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    suggestion["status"] = status_value
    if revision_instruction is not None:
        suggestion["revision_instruction"] = revision_instruction
    # Re-serialize the whole document; status lives inline on each suggestion.
    version.suggestions_json = json.dumps(doc)
    db.commit()
    db.refresh(version)
    return ResumeSuggestionRead(**suggestion)


@router.get("/{version_id}/suggestions", response_model=ResumeSuggestionsRead)
def list_suggestions(
    version_id: str, db: Session = Depends(get_db)
) -> ResumeSuggestionsRead:
    version = _load_version_or_404(version_id, db)
    doc = _load_suggestions_doc_or_404(version)
    return _suggestions_read(version, doc)


@router.post(
    "/{version_id}/suggestions/{suggestion_id}/accept",
    response_model=ResumeSuggestionRead,
)
def accept_suggestion(
    version_id: str, suggestion_id: str, db: Session = Depends(get_db)
) -> ResumeSuggestionRead:
    """Mark a suggestion accepted.

    Accepting records intent; the working resume is rebuilt from all accepted
    suggestions atomically by ``POST .../apply-suggestions`` so a sequence of
    accept/reject clicks stays cheap and the rebuild is a single explicit step.
    """
    return _set_suggestion_status(version_id, suggestion_id, "accepted", db)


@router.post(
    "/{version_id}/suggestions/{suggestion_id}/reject",
    response_model=ResumeSuggestionRead,
)
def reject_suggestion(
    version_id: str, suggestion_id: str, db: Session = Depends(get_db)
) -> ResumeSuggestionRead:
    return _set_suggestion_status(version_id, suggestion_id, "rejected", db)


@router.post(
    "/{version_id}/suggestions/{suggestion_id}/revise",
    response_model=ResumeSuggestionRead,
)
def revise_suggestion(
    version_id: str,
    suggestion_id: str,
    payload: SuggestionReviseRequest,
    db: Session = Depends(get_db),
) -> ResumeSuggestionRead:
    """Store a revision instruction and mark the suggestion ``revised``.

    First implementation per task 113: the instruction is captured for a
    later revision run (the existing ``/revision-feedback`` endpoint), not
    regenerated live here.
    """
    return _set_suggestion_status(
        version_id,
        suggestion_id,
        "revised",
        db,
        revision_instruction=payload.instruction,
    )


@router.post("/{version_id}/apply-suggestions", response_model=ApplySuggestionsRead)
def apply_suggestions(
    version_id: str, db: Session = Depends(get_db)
) -> ApplySuggestionsRead:
    """Rebuild the working structured resume from the accepted suggestions.

    Applies every ``accepted`` suggestion onto the imported base
    ``tailored_resume.json`` and persists the result as the working resume
    state. When the deterministic renderer can consume the result and the
    source run directory still exists, a fresh ``output/applied_resume.docx``
    is rendered best-effort so the operator can download the applied draft;
    a render failure never fails the apply call.
    """
    version = _load_version_or_404(version_id, db)
    doc = _load_suggestions_doc_or_404(version)
    review_state = version.review_state or {}
    base_resume = review_state.get("base_resume_json")
    if not isinstance(base_resume, dict):
        raise HTTPException(
            status_code=409,
            detail="no base structured resume available to apply suggestions onto",
        )

    suggestions = doc.get("suggestions", [])
    accepted_count = sum(1 for s in suggestions if s.get("status") == "accepted")
    working_resume = apply_accepted(base_resume, suggestions)
    applied_at = datetime.now(timezone.utc)

    review_state["working_resume_json"] = working_resume
    review_state["applied_at"] = applied_at.isoformat()
    review_state.setdefault("base_resume_json", base_resume)
    _render_applied_docx(version, working_resume, review_state)
    version.suggestion_review_state = json.dumps(review_state)
    db.commit()
    db.refresh(version)

    return ApplySuggestionsRead(
        resume_version_id=version.id,
        applied_at=applied_at,
        accepted_count=accepted_count,
        working_resume=working_resume,
    )


def _render_applied_docx(
    version: ResumeVersion, working_resume: dict, review_state: dict
) -> None:
    """Best-effort render of the applied working resume to a DOCX.

    Records the rendered path on ``review_state`` when successful. Any
    validation/render/IO failure is swallowed — the JSON working state is the
    source of truth and the DOCX is a convenience artifact.
    """
    if not version.docx_path:
        return
    try:
        output_dir = Path(version.docx_path).parent
        if not output_dir.is_dir():
            return
        payload = validate_resume_payload(working_resume)
        applied_path = output_dir / "applied_resume.docx"
        render_resume(payload, applied_path)
        review_state["working_resume_docx_path"] = str(applied_path)
    except (RendererError, OSError, ValueError):
        review_state.pop("working_resume_docx_path", None)


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
    # Stage the structured projection of the prior draft when available so the
    # worker can reuse its section/entry ids across revisions. Prefer the
    # applied working resume over the captured base.
    current_json: Optional[str] = None
    prior_review_state = source_version.review_state or {}
    prior_structured = prior_review_state.get(
        "working_resume_json"
    ) or prior_review_state.get("base_resume_json")
    if isinstance(prior_structured, dict) and prior_structured:
        current_json = json.dumps(prior_structured, indent=2)
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
            current_tailored_resume_json=current_json,
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
