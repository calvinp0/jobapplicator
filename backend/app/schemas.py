from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import APPLICATION_STATUSES, REVISION_FEEDBACK_STATUSES


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- JobCapture ----

class JobCaptureCreate(BaseModel):
    source_platform: str
    capture_method: str
    external_url: str
    external_job_id: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    description_text: str = ""
    application_method: Optional[str] = None
    raw_text: Optional[str] = None
    captured_at: Optional[datetime] = None


class JobCaptureRead(_ORMModel):
    id: str
    source_platform: str
    capture_method: str
    external_url: str
    external_job_id: Optional[str]
    company: Optional[str]
    title: Optional[str]
    location: Optional[str]
    description_text: str
    application_method: Optional[str]
    raw_text: Optional[str]
    captured_at: datetime
    user_confirmed: bool
    created_at: datetime
    job_id: Optional[str] = None


class JobCaptureCreateResponse(JobCaptureRead):
    """Response shape for POST /captures.

    Extends JobCaptureRead so the extension can act on the auto-confirm
    outcome without a follow-up round trip: ``auto_confirmed`` tells the
    popup whether to surface an "Open job workspace" link, ``job_id`` is
    populated for both freshly created and reused (dedup-by-url) jobs,
    and ``job_reused`` distinguishes the two so the popup can say "Job
    created" vs "Job already exists".
    """

    auto_confirmed: bool = False
    job_reused: bool = False


# ---- Job ----

class JobCreate(BaseModel):
    source_platform: str
    external_url: Optional[str] = None
    external_job_id: Optional[str] = None
    company: str
    title: str
    location: Optional[str] = None
    description_text: str
    application_method: Optional[str] = None
    created_from_capture_id: Optional[str] = None


class JobRead(_ORMModel):
    id: str
    source_platform: str
    external_url: Optional[str]
    external_job_id: Optional[str]
    company: str
    title: str
    location: Optional[str]
    description_text: str
    application_method: Optional[str]
    created_from_capture_id: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---- MasterResume ----

class MasterResumeCreate(BaseModel):
    name: str
    source_path: Optional[str] = None
    content_markdown: str


class MasterResumeRead(_ORMModel):
    id: str
    name: str
    source_path: Optional[str]
    content_markdown: str
    created_at: datetime
    updated_at: datetime


# ---- EvidenceBank ----

class EvidenceBankCreate(BaseModel):
    name: str
    source_path: Optional[str] = None
    content_markdown: str


class EvidenceBankRead(_ORMModel):
    id: str
    name: str
    source_path: Optional[str]
    content_markdown: str
    created_at: datetime
    updated_at: datetime


# ---- Application ----

class ApplicationCreate(BaseModel):
    job_id: str
    resume_version_id: Optional[str] = None
    status: str = Field(default="draft")


class ApplicationRead(_ORMModel):
    id: str
    job_id: str
    resume_version_id: Optional[str]
    status: str
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


APPLICATION_STATUS_SET = set(APPLICATION_STATUSES)


# ---- ApplicationEvent ----

class ApplicationEventCreate(BaseModel):
    event_type: str
    notes: Optional[str] = None
    source: Optional[str] = None


class ApplicationEventRead(_ORMModel):
    id: str
    application_id: str
    event_type: str
    event_time: datetime
    notes: Optional[str]
    source: Optional[str]
    created_at: datetime


# ---- File open ----

class FileOpenRequest(BaseModel):
    path: Optional[str] = None
    resume_version_id: Optional[str] = None


# ---- ClaudeRun ----

class ClaudeRunCreate(BaseModel):
    job_id: str
    master_resume_id: str
    evidence_bank_id: Optional[str] = None
    # Optional provider override. When omitted the route falls back to the
    # application-wide default (currently stubbed to ``claude_code``;
    # task 066 wires it to a persisted setting). Unknown ids are rejected
    # at the route layer against the provider registry, not by this schema,
    # so the error returns a clean 400 with a registry-aware message.
    llm_provider: Optional[str] = None


class ClaudeRunRead(_ORMModel):
    id: str
    job_id: str
    master_resume_id: str
    evidence_bank_id: Optional[str]
    run_dir: str
    status: str
    llm_provider: str
    prompt_hash: Optional[str]
    input_hash: Optional[str]
    output_hash: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]


# ---- LLMProvider ----


class LLMProviderRead(BaseModel):
    """Read shape for the provider registry listing endpoint (ADR-009).

    Returned by ``GET /llm-providers`` so the frontend can render a
    selector without having to embed the registry. Only fields that are
    safe to surface to the UI live here — the argv builder and the
    prompt-delivery sentinel stay server-side.
    """

    id: str
    display_name: str
    default_binary: str
    binary_env_var: str


class ClaudeRunLogRead(BaseModel):
    """Tail of recent ``run.log`` lines for live progress polling.

    Empty ``lines`` means either the run hasn't started writing yet or the
    log file does not exist; either way the UI should show its "waiting"
    state instead of an error. ``truncated`` signals the log is longer than
    the returned tail.
    """

    run_id: str
    lines: list[str]
    truncated: bool


class ClaudeRunProgressRead(BaseModel):
    """Tail of recent user-facing progress events from ``progress/progress.log``.

    Separate from ``ClaudeRunLogRead`` so the UI can show plain-language
    phase events (and worker heartbeats) as the default ``Recent activity``
    feed without having to filter the technical ``run.log`` stream. Empty
    ``lines`` means the worker has not started writing yet — the UI should
    keep its "waiting" state or fall back to the technical log if it has
    user-facing material to show.
    """

    run_id: str
    lines: list[str]
    truncated: bool


# ---- ResumeVersion ----

class ResumeVersionRead(_ORMModel):
    id: str
    job_id: str
    master_resume_id: str
    claude_run_id: Optional[str]
    version_number: int
    content_markdown: Optional[str]
    docx_path: Optional[str]
    pdf_path: Optional[str]
    content_hash: Optional[str]
    prompt_hash: Optional[str]
    source: str
    approved_at: Optional[datetime]
    created_at: datetime


# ---- RevisionFeedback ----

# Request body shape for the (future, task 045) endpoint at
# POST /api/resume-versions/{resume_version_id}/revision-feedback.
# The source ResumeVersion is supplied via the path, not the body.
# `structured_flags` is accepted here but not persisted as a column;
# the endpoint renders it into runs/<run_id>/input/revision_feedback.md
# as frontmatter, per ADR-008.
class RevisionFeedbackCreate(BaseModel):
    feedback_markdown: str = Field(min_length=1)
    structured_flags: Optional[Dict[str, Any]] = None


class RevisionFeedbackRead(_ORMModel):
    id: str
    job_id: str
    source_resume_version_id: str
    followup_claude_run_id: Optional[str]
    feedback_markdown: str
    status: str
    created_at: datetime


REVISION_FEEDBACK_STATUS_SET = set(REVISION_FEEDBACK_STATUSES)
