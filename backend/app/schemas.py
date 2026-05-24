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


class ClaudeRunRead(_ORMModel):
    id: str
    job_id: str
    master_resume_id: str
    evidence_bank_id: Optional[str]
    run_dir: str
    status: str
    prompt_hash: Optional[str]
    input_hash: Optional[str]
    output_hash: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]


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
