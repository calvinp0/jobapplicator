from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import APPLICATION_STATUSES


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
