from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import ClaudeRun
from .routers import (
    applications,
    captures,
    evidence_banks,
    files,
    jobs,
    master_resumes,
    resume_versions,
    runs,
)
from .run_directory import (
    TAILORING_METHOD_WORD_HANDOFF,
    get_run_status,
    get_tailoring_method,
)
from .word_handoff import (
    EXPECTED_WORD_OUTPUT_RELPATH,
    INSTRUCTIONS_FILENAME,
    PROMPT_FILENAME,
    RESUME_DOCX_FILENAME,
    WORD_HANDOFF_DIRNAME,
    WordHandoffError,
    create_word_handoff_package,
)


# Project-relative path helper. The contract in
# docs/contracts/claude_run_directory.md describes the run layout as
# ``runs/<run_id>/...``; the frontend joins these against its own runs root
# rather than relying on the backend's absolute filesystem paths.
def _rel_run_path(run_id: str, *parts: str) -> str:
    return "/".join(("runs", run_id, *parts))


class WordHandoffMetadata(BaseModel):
    run_id: str
    status: str
    tailoring_method: str
    handoff_dir: str
    resume_docx: Optional[str]
    prompt_file: Optional[str]
    instructions_file: Optional[str]
    expected_output: str


class WordHandoffTextRead(BaseModel):
    run_id: str
    content: str


word_handoff_router = APIRouter(prefix="/runs", tags=["word_handoff"])


def _get_run_or_404(run_id: str, db: Session) -> ClaudeRun:
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="claude run not found")
    return run


def _build_metadata_response(run: ClaudeRun) -> WordHandoffMetadata:
    run_dir = Path(run.run_dir)
    handoff_dir = run_dir / WORD_HANDOFF_DIRNAME
    resume_path = handoff_dir / RESUME_DOCX_FILENAME
    prompt_path = handoff_dir / PROMPT_FILENAME
    instructions_path = handoff_dir / INSTRUCTIONS_FILENAME

    # Fall back to the DB-level status / the word_handoff method label if
    # metadata.json cannot be read — we still want to give the frontend
    # something useful to render.
    try:
        run_status = get_run_status(run_dir)
    except Exception:
        run_status = run.status
    try:
        method = get_tailoring_method(run_dir)
    except Exception:
        method = TAILORING_METHOD_WORD_HANDOFF

    return WordHandoffMetadata(
        run_id=run.id,
        status=run_status,
        tailoring_method=method,
        handoff_dir=_rel_run_path(run.id, WORD_HANDOFF_DIRNAME),
        resume_docx=(
            _rel_run_path(run.id, WORD_HANDOFF_DIRNAME, RESUME_DOCX_FILENAME)
            if resume_path.is_file()
            else None
        ),
        prompt_file=(
            _rel_run_path(run.id, WORD_HANDOFF_DIRNAME, PROMPT_FILENAME)
            if prompt_path.is_file()
            else None
        ),
        instructions_file=(
            _rel_run_path(run.id, WORD_HANDOFF_DIRNAME, INSTRUCTIONS_FILENAME)
            if instructions_path.is_file()
            else None
        ),
        expected_output=_rel_run_path(run.id, EXPECTED_WORD_OUTPUT_RELPATH),
    )


@word_handoff_router.post(
    "/{run_id}/word-handoff",
    response_model=WordHandoffMetadata,
    status_code=status.HTTP_200_OK,
)
def create_or_refresh_word_handoff(
    run_id: str, db: Session = Depends(get_db)
) -> WordHandoffMetadata:
    run = _get_run_or_404(run_id, db)
    try:
        create_word_handoff_package(Path(run.run_dir))
    except WordHandoffError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _build_metadata_response(run)


@word_handoff_router.get(
    "/{run_id}/word-handoff",
    response_model=WordHandoffMetadata,
)
def get_word_handoff(
    run_id: str, db: Session = Depends(get_db)
) -> WordHandoffMetadata:
    run = _get_run_or_404(run_id, db)
    handoff_dir = Path(run.run_dir) / WORD_HANDOFF_DIRNAME
    if not handoff_dir.is_dir():
        raise HTTPException(
            status_code=404, detail="word handoff package not created"
        )
    return _build_metadata_response(run)


@word_handoff_router.get(
    "/{run_id}/word-handoff/prompt",
    response_model=WordHandoffTextRead,
)
def get_word_handoff_prompt(
    run_id: str, db: Session = Depends(get_db)
) -> WordHandoffTextRead:
    run = _get_run_or_404(run_id, db)
    prompt_path = Path(run.run_dir) / WORD_HANDOFF_DIRNAME / PROMPT_FILENAME
    if not prompt_path.is_file():
        raise HTTPException(
            status_code=404, detail="word handoff prompt not found"
        )
    return WordHandoffTextRead(
        run_id=run.id,
        content=prompt_path.read_text(encoding="utf-8"),
    )


@word_handoff_router.get(
    "/{run_id}/word-handoff/instructions",
    response_model=WordHandoffTextRead,
)
def get_word_handoff_instructions(
    run_id: str, db: Session = Depends(get_db)
) -> WordHandoffTextRead:
    run = _get_run_or_404(run_id, db)
    instructions_path = (
        Path(run.run_dir) / WORD_HANDOFF_DIRNAME / INSTRUCTIONS_FILENAME
    )
    if not instructions_path.is_file():
        raise HTTPException(
            status_code=404, detail="word handoff instructions not found"
        )
    return WordHandoffTextRead(
        run_id=run.id,
        content=instructions_path.read_text(encoding="utf-8"),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="jobapply backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Base.metadata.create_all(bind=engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(captures.router)
    app.include_router(jobs.router)
    app.include_router(master_resumes.router)
    app.include_router(evidence_banks.router)
    app.include_router(applications.router)
    app.include_router(runs.router)
    app.include_router(word_handoff_router)
    app.include_router(resume_versions.router)
    app.include_router(files.router)

    return app


app = create_app()
