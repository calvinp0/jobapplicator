from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import Base, engine, ensure_runtime_columns, get_db
from .models import ClaudeRun
from .routers import (
    activity,
    applications,
    captures,
    evidence_banks,
    evidence_sources,
    files,
    gmail,
    jobs,
    llm_providers,
    master_resumes,
    prompts,
    resume_versions,
    runs,
    settings,
)
from .run_directory import (
    TAILORING_METHOD_WORD_HANDOFF,
    get_run_status,
    get_tailoring_method,
)
from .word_handoff import (
    EXPECTED_WORD_OUTPUT_RELPATH,
    FINAL_RESUME_FILENAME,
    INSTRUCTIONS_FILENAME,
    OUTPUT_DIRNAME,
    PROMPT_FILENAME,
    RESUME_DOCX_FILENAME,
    WORD_HANDOFF_DIRNAME,
    WORD_RESULT_FILENAME,
    WordHandoffError,
    WordHandoffStatusInfo,
    create_word_handoff_package,
    get_word_handoff_status,
    import_word_result,
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


class WordResultImportResponse(BaseModel):
    run_id: str
    status: str
    message: str
    word_result: Optional[str] = None
    final_resume: Optional[str] = None
    expected_output: Optional[str] = None


class WordHandoffFileStatusRead(BaseModel):
    name: str
    path: str
    exists: bool


class WordHandoffStatusRead(BaseModel):
    """Filesystem-derived view of the handoff package — see task 112.

    ``state`` is one of ``not_prepared``, ``prepared``, ``missing_files``,
    ``import_ready``, or ``imported``. The UI uses ``state`` to decide
    which controls and copy to render, and the file map to show which
    artifacts already exist on disk.
    """

    run_id: str
    state: str
    handoff_dir: str
    handoff_dir_exists: bool
    files: dict[str, WordHandoffFileStatusRead]
    missing_required_files: list[str]
    message: str


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


def _file_status_to_read(
    run_id: str, file_status
) -> WordHandoffFileStatusRead:
    return WordHandoffFileStatusRead(
        name=file_status.name,
        path=_rel_run_path(run_id, *file_status.path.split("/")),
        exists=file_status.exists,
    )


def _build_status_response(
    run_id: str, info: WordHandoffStatusInfo
) -> WordHandoffStatusRead:
    files = {
        "resume_docx": _file_status_to_read(run_id, info.resume_docx),
        "prompt_txt": _file_status_to_read(run_id, info.prompt_txt),
        "instructions_md": _file_status_to_read(run_id, info.instructions_md),
        "expected_output_docx": _file_status_to_read(
            run_id, info.expected_output_docx
        ),
        "final_resume_docx": _file_status_to_read(
            run_id, info.final_resume_docx
        ),
    }
    return WordHandoffStatusRead(
        run_id=run_id,
        state=info.state,
        handoff_dir=_rel_run_path(run_id, info.handoff_dir_relpath),
        handoff_dir_exists=info.handoff_dir_exists,
        files=files,
        missing_required_files=list(info.missing_required_files),
        message=info.message,
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
    "/{run_id}/word-handoff/status",
    response_model=WordHandoffStatusRead,
)
def get_word_handoff_status_endpoint(
    run_id: str, db: Session = Depends(get_db)
) -> WordHandoffStatusRead:
    """Filesystem-derived view of the handoff package.

    Always returns 200 with a ``state`` describing where the run is in
    the handoff lifecycle, so the UI can render the right copy without
    a try/catch around a 404. See task 112 for the state machine.
    """
    run = _get_run_or_404(run_id, db)
    info = get_word_handoff_status(Path(run.run_dir))
    return _build_status_response(run.id, info)


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


@word_handoff_router.post(
    "/{run_id}/import-word-result",
    response_model=WordResultImportResponse,
)
def import_word_result_endpoint(
    run_id: str, db: Session = Depends(get_db)
) -> WordResultImportResponse:
    run = _get_run_or_404(run_id, db)
    try:
        info = import_word_result(Path(run.run_dir))
    except WordHandoffError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not info.imported:
        return WordResultImportResponse(
            run_id=run.id,
            status="waiting_for_word_result",
            message=(
                "Save the completed Word document to the expected output "
                "path, then import again"
            ),
            expected_output=_rel_run_path(
                run.id, OUTPUT_DIRNAME, WORD_RESULT_FILENAME
            ),
        )

    return WordResultImportResponse(
        run_id=run.id,
        status="completed",
        message="Imported Claude for Word result",
        word_result=_rel_run_path(run.id, OUTPUT_DIRNAME, WORD_RESULT_FILENAME),
        final_resume=_rel_run_path(run.id, OUTPUT_DIRNAME, FINAL_RESUME_FILENAME),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="jobapply backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        # Browser extensions issue requests from their own scheme-specific
        # origin (``moz-extension://<uuid>`` in Firefox,
        # ``chrome-extension://<id>`` in Chrome). Allow those so the
        # current-page capture extension can talk to the local backend
        # without per-installation configuration. The regex is intentionally
        # narrow: it only matches the two extension schemes, not arbitrary
        # web origins.
        allow_origin_regex=r"^(moz|chrome)-extension://[A-Za-z0-9_\-{}.]+$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Base.metadata.create_all(bind=engine)
    # Backfill columns added after the initial schema. ``create_all`` only
    # creates missing tables; columns added in later tasks (currently just
    # ``claude_runs.llm_provider``) need an explicit ALTER on existing DBs.
    ensure_runtime_columns()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(captures.router)
    app.include_router(activity.router)
    app.include_router(jobs.router)
    app.include_router(master_resumes.router)
    app.include_router(evidence_banks.router)
    app.include_router(evidence_sources.router)
    app.include_router(applications.router)
    app.include_router(runs.router)
    app.include_router(word_handoff_router)
    app.include_router(resume_versions.router)
    app.include_router(files.router)
    app.include_router(llm_providers.router)
    app.include_router(settings.router)
    app.include_router(gmail.router)
    app.include_router(prompts.router)

    return app


app = create_app()
