from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    APPLICATION_STATUSES,
    EMAIL_CLASSIFIED_STATUSES,
    EMAIL_STATUSES,
    REVISION_FEEDBACK_STATUSES,
)


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
    # Task 109 fallback fields populated by the browser extension when
    # LinkedIn's structured selectors fail to resolve. ``diagnostics`` is a
    # free-form dict the extension fills with which selectors matched and
    # which fallbacks were exercised; the router serializes it to JSON
    # before storing.
    page_title: Optional[str] = None
    page_text: Optional[str] = None
    selected_text: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = None
    captured_at: Optional[datetime] = None


class JobCaptureRead(_ORMModel):
    id: str
    source_platform: str
    capture_method: str
    external_url: str
    # Task 110: ``source_url`` is the raw URL the extension captured;
    # ``canonical_url`` is the deterministically cleaned form. Both are
    # nullable so historical captures (pre-canonicalizer) still serialize.
    source_url: Optional[str] = None
    canonical_url: Optional[str] = None
    external_job_id: Optional[str]
    company: Optional[str]
    title: Optional[str]
    location: Optional[str]
    description_text: str
    application_method: Optional[str]
    raw_text: Optional[str]
    page_title: Optional[str] = None
    page_text: Optional[str] = None
    selected_text: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = Field(default=None)
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
    # Task 110: same canonical/source URL pair surfaced by JobCaptureRead.
    source_url: Optional[str] = None
    canonical_url: Optional[str] = None
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
    # ``source`` distinguishes database-backed rows from filesystem
    # discoveries (``candidate_context/master_resumes/``). ``source_format``
    # is the lowercase extension for filesystem entries (``docx``, ``md``,
    # ``txt``) and ``None`` for database rows. ``is_demo`` flags the seeded
    # demo record so the UI can sort real files ahead of it.
    source: str = "database"
    source_format: Optional[str] = None
    is_demo: bool = False


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


# ---- EvidenceSource ----

# Supported ``source_type`` values surfaced to the API. The list is
# intentionally short — adding a new type means adding a new subfolder to
# ``evidence_source_discovery.SUBFOLDER_SOURCE_TYPES`` (and probably a UI
# badge) rather than introducing a parallel storage shape.
EVIDENCE_SOURCE_TYPES = (
    "evidence_bank",
    "resume_variant",
    "master_resume",
    "project_note",
    "candidate_note",
    "other",
)


class EvidenceSourceRead(BaseModel):
    """Selector-shaped view of a tailoring run evidence source.

    Combines database-backed ``EvidenceBank`` rows and filesystem
    discoveries from ``candidate_context/`` under a single shape so the
    frontend's multi-select picker can render both kinds with a uniform
    badge set. ``source`` is ``"database"`` for DB rows and
    ``"filesystem"`` for discoveries; ``source_path`` is only set for
    filesystem entries. ``is_demo`` flags the seeded demo evidence bank
    so the UI can push it below real files.
    """

    id: str
    name: str
    source_type: str
    source_format: Optional[str] = None
    source: str
    source_path: Optional[str] = None
    updated_at: datetime
    is_demo: bool = False


# ---- Application ----

class ApplicationCreate(BaseModel):
    job_id: str
    resume_version_id: Optional[str] = None
    status: str = Field(default="draft")


class EmailLinkRead(_ORMModel):
    id: str
    application_id: str
    gmail_message_id: str
    gmail_thread_id: Optional[str]
    subject: Optional[str]
    sender: Optional[str]
    snippet: Optional[str] = None
    received_at: Optional[datetime]
    classified_status: Optional[str]
    confidence: Optional[float]
    match_method: Optional[str] = None
    match_score: Optional[float] = None
    linked_by_user: bool = False
    evidence: Optional[list[Dict[str, Any]]] = None
    created_at: datetime


class EmailLinkCreate(BaseModel):
    gmail_message_id: str = Field(min_length=1)
    gmail_thread_id: Optional[str] = None
    subject: Optional[str] = None
    sender: Optional[str] = None
    snippet: Optional[str] = None
    received_at: Optional[datetime] = None
    classified_status: str
    confidence: Optional[float] = None


class ApplicationRead(_ORMModel):
    id: str
    job_id: str
    resume_version_id: Optional[str]
    status: str
    submitted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    timeline_stage: str
    last_email_link: Optional[EmailLinkRead] = None
    email_link_count: int = 0
    # Richer dashboard fields. All are derived server-side from the
    # existing status/submitted_at/email_links/resume_version data so no
    # schema migration is required.
    submission_status: str = "not_submitted"
    email_status: str = "not_watching"
    next_action: str = ""
    latest_run_id: Optional[str] = None
    latest_run_status: Optional[str] = None
    last_email_at: Optional[datetime] = None
    # Gmail tracking surface. See docs/contracts/gmail_integration.md.
    # ``gmail_query`` and ``last_gmail_check_at`` mirror persisted columns
    # on Application; the rest are derived from the most recent attached
    # EmailLink (``latest_email_snippet`` and ``latest_email_evidence``
    # are reserved for the future Gmail-poll path and are always null
    # today).
    gmail_query: Optional[str] = None
    last_gmail_check_at: Optional[datetime] = None
    last_matched_email_at: Optional[datetime] = None
    matched_email_count: int = 0
    latest_email_subject: Optional[str] = None
    latest_email_from: Optional[str] = None
    latest_email_snippet: Optional[str] = None
    latest_email_classification: Optional[str] = None
    latest_email_confidence: Optional[float] = None
    latest_email_evidence: Optional[str] = None


APPLICATION_STATUS_SET = set(APPLICATION_STATUSES)
EMAIL_CLASSIFIED_STATUS_SET = set(EMAIL_CLASSIFIED_STATUSES)
EMAIL_STATUS_SET = frozenset(EMAIL_STATUSES)


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
    # ``evidence_bank_id`` is the legacy single-source field — preserved
    # so older clients (and the existing tests/demo seed) keep working.
    # When ``evidence_source_ids`` is also supplied, it is merged in as
    # a first entry; callers that send both are not ambiguous, they are
    # additive. A future task may deprecate the singular form.
    evidence_bank_id: Optional[str] = None
    evidence_source_ids: Optional[list[str]] = None
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
    # Multi-source selections live in metadata.json (not on the DB
    # row), so this is best-effort: the router populates it after the
    # ClaudeRun is created; older runs without the field default to [].
    evidence_source_ids: list[str] = []


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


class ClaudeRunRecruiterReviewRead(BaseModel):
    """Contents of the recruiter review file for a run, when present.

    ``available`` is False (and ``content`` is None) when the file has
    not been written yet — the UI shows a "review not produced" hint
    rather than treating the absence as an error.
    """

    run_id: str
    available: bool
    content: Optional[str] = None
    path: Optional[str] = None


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


# ---- Resume Suggestions (task 113) ----


class EvidenceRefRead(BaseModel):
    """A single piece of evidence backing a suggestion."""

    source: str = ""
    quote: str = ""


class ResumeSuggestionRead(BaseModel):
    """One section-level suggestion in the interactive review surface.

    Shapes the normalized suggestion stored in
    ``ResumeVersion.suggestions_json``. ``status`` walks the
    ``pending -> accepted | rejected | revised`` lifecycle;
    ``revision_instruction`` is the free-text captured by "Ask to revise"
    (empty until the user requests one).
    """

    id: str
    section_id: str
    section_heading: str = ""
    operation: str
    current_text: str = ""
    suggested_text: str = ""
    reason: str
    evidence_refs: list[EvidenceRefRead] = []
    ats_keywords: list[str] = []
    confidence: Optional[float] = None
    risk: str = "medium"
    status: str = "pending"
    revision_instruction: str = ""


class ResumeSuggestionsRead(BaseModel):
    """The full suggestions surface for a resume version."""

    resume_version_id: str
    target_company: str = ""
    target_job_title: str = ""
    suggestions: list[ResumeSuggestionRead] = []
    # Review working state. ``applied_at`` is set once the user applies the
    # accepted suggestions; ``has_working_resume`` tells the UI whether an
    # applied structured resume exists to preview/download.
    applied_at: Optional[datetime] = None
    has_working_resume: bool = False


class SuggestionReviseRequest(BaseModel):
    instruction: str = Field(min_length=1)


class ApplySuggestionsRead(BaseModel):
    """Result of rebuilding the working resume from accepted suggestions."""

    resume_version_id: str
    applied_at: datetime
    accepted_count: int
    working_resume: Optional[Dict[str, Any]] = None


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
    # Optional additional evidence to stage on the revision run alongside
    # the original evidence sources. Each id is resolved through the same
    # database + filesystem discovery path used for first-draft runs (see
    # ``backend/app/routers/runs.py``). The field is accepted even when no
    # additional evidence is wanted — callers may send an empty list or
    # omit the key entirely.
    additional_evidence_source_ids: Optional[list[str]] = None


class RevisionFeedbackRead(_ORMModel):
    id: str
    job_id: str
    source_resume_version_id: str
    followup_claude_run_id: Optional[str]
    feedback_markdown: str
    status: str
    created_at: datetime


REVISION_FEEDBACK_STATUS_SET = set(REVISION_FEEDBACK_STATUSES)
