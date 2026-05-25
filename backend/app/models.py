from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Status string constants. Kept as module-level tuples (not Enum) because SQLite
# stores them as TEXT and we want to keep migrations simple.
CLAUDE_RUN_STATUSES = ("created", "running", "completed", "failed", "imported")
REVISION_FEEDBACK_STATUSES = ("created", "used", "superseded")
APPLICATION_STATUSES = (
    "draft",
    "generated",
    "approved",
    "submitted",
    "response_received",
    "rejected",
    "interview",
    "offer",
    "withdrawn",
)
EMAIL_CLASSIFIED_STATUSES = (
    "confirmation",
    "rejection",
    "next_step",
    "offer",
    "other",
)
# Per-application Gmail tracking state surfaced on ApplicationRead. The full
# vocabulary and derivation rules live in docs/contracts/gmail_integration.md;
# the manual-entry path only emits a subset today, but ``no_match`` and
# ``error`` are pinned here so the future Gmail-poll path can land without a
# contract change.
EMAIL_STATUSES = (
    "not_watching",
    "watching",
    "confirmation_found",
    "email_received",
    "needs_review",
    "classified_rejection",
    "classified_interview",
    "classified_assessment",
    "classified_offer",
    "classified_neutral",
    "no_match",
    "error",
)


class JobCapture(Base):
    __tablename__ = "job_captures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    capture_method: Mapped[str] = mapped_column(String(64), nullable=False)
    external_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    external_job_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    application_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    created_job: Mapped[Optional["Job"]] = relationship(
        back_populates="source_capture", uselist=False
    )

    @property
    def job_id(self) -> Optional[str]:
        return self.created_job.id if self.created_job is not None else None


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    external_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    external_job_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    company: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    application_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_from_capture_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("job_captures.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    source_capture: Mapped[Optional[JobCapture]] = relationship(
        back_populates="created_job", foreign_keys=[created_from_capture_id]
    )

    claude_runs: Mapped[list["ClaudeRun"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    resume_versions: Mapped[list["ResumeVersion"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class MasterResume(Base):
    __tablename__ = "master_resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class EvidenceBank(Base):
    __tablename__ = "evidence_banks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class ClaudeRun(Base):
    __tablename__ = "claude_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    master_resume_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("master_resumes.id"), nullable=False
    )
    evidence_bank_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("evidence_banks.id"), nullable=True
    )
    run_dir: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    # ``llm_provider`` records which CLI worker produced the run's artifacts.
    # Per ADR-009 this is persisted on the run so provenance survives the
    # user later changing the application-wide default. Default ``claude_code``
    # preserves the pre-registry behavior for existing rows and for runs
    # that do not opt into a different provider explicitly.
    llm_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="claude_code", server_default="claude_code"
    )
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    input_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    output_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="claude_runs")
    resume_versions: Mapped[list["ResumeVersion"]] = relationship(back_populates="claude_run")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    master_resume_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("master_resumes.id"), nullable=False
    )
    claude_run_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("claude_runs.id"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docx_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="claude_run")
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    job: Mapped[Job] = relationship(back_populates="resume_versions")
    claude_run: Mapped[Optional[ClaudeRun]] = relationship(back_populates="resume_versions")
    applications: Mapped[list["Application"]] = relationship(back_populates="resume_version")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    resume_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("resume_versions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Gmail tracking columns. See docs/contracts/gmail_integration.md.
    # ``gmail_query`` holds an optional user override for the auto-built
    # search query; ``last_gmail_check_at`` records the wall-clock of the
    # most recent Gmail poll attempt. Both are NULL on existing rows and
    # for any application that has not opted into Gmail tracking yet.
    gmail_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_gmail_check_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Outcome of the most recent Gmail application-search (task 083). Stores
    # only the small derived label ``"no_match"`` / ``"email_received"`` /
    # ``"error"`` produced by the search endpoint; full candidate metadata
    # is returned in the search response, not persisted here. ``NULL``
    # means "no search has run yet" and falls back to the EmailLink-driven
    # derivation in ``derive_email_status``.
    email_search_state: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    job: Mapped[Job] = relationship(back_populates="applications")
    resume_version: Mapped[Optional[ResumeVersion]] = relationship(back_populates="applications")
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    email_links: Mapped[list["EmailLink"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    application: Mapped[Application] = relationship(back_populates="events")


class RevisionFeedback(Base):
    """User feedback on a prior ResumeVersion, joining that draft to a follow-up ClaudeRun.

    See ADR-008. Storage shape is intentionally a join row, not columns on
    Run or ResumeVersion, so that one draft can collect multiple feedback
    attempts over time. `followup_claude_run_id` is nullable so the row can
    be inserted before / independently of its run; status lifecycle is
    `created -> used | superseded` (run-level failure stays on ClaudeRun,
    per ADR-008's explicit non-rule).
    """

    __tablename__ = "revision_feedbacks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=False)
    source_resume_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("resume_versions.id"), nullable=False
    )
    followup_claude_run_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("claude_runs.id"), nullable=True
    )
    feedback_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    job: Mapped[Job] = relationship()
    source_resume_version: Mapped[ResumeVersion] = relationship(
        foreign_keys=[source_resume_version_id]
    )
    followup_claude_run: Mapped[Optional[ClaudeRun]] = relationship(
        foreign_keys=[followup_claude_run_id]
    )


class AppSetting(Base):
    """Singleton-style key/value store for application-wide settings.

    Used today only for ``default_llm_provider`` (ADR-009 / task 066). The
    table is intentionally a simple key/value shape — not a general-purpose
    feature-flag system — so additional settings, if ever needed, slot in
    without a schema change. ``value`` is TEXT; callers serialize/parse
    typed values themselves.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class EmailLink(Base):
    __tablename__ = "email_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )
    gmail_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    classified_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    application: Mapped[Application] = relationship(back_populates="email_links")
