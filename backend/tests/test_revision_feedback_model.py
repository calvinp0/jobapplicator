"""Model-layer tests for RevisionFeedback (task 044, ADR-008).

These bypass the HTTP layer because the revision-feedback endpoint is
intentionally out of scope for this task (it lands in task 045). The
tests cover the persistence concerns the task is responsible for:

- the revision_feedbacks table is created on a fresh DB initialized via
  db.init_db() and has the columns ADR-008 specifies
- the followup_claude_run_id FK column is nullable, can be left null on
  insert, and resolves to the correct ClaudeRun when set
- the Pydantic create/read schemas validate a representative payload
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def session():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["JOBAPPLY_DATABASE_URL"] = f"sqlite:///{tmp.name}"

    for mod_name in ["app.schemas", "app.models", "app.db", "app"]:
        sys.modules.pop(mod_name, None)

    from app.db import SessionLocal, init_db  # noqa: E402

    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        os.unlink(tmp.name)


def _make_job_and_draft(session):
    """Insert a Job + MasterResume + ClaudeRun + ResumeVersion and return them."""
    from app.models import ClaudeRun, Job, MasterResume, ResumeVersion

    job = Job(
        source_platform="linkedin",
        company="Acme",
        title="Engineer",
        description_text="...",
    )
    master = MasterResume(name="m", content_markdown="x")
    session.add_all([job, master])
    session.flush()

    run = ClaudeRun(
        job_id=job.id,
        master_resume_id=master.id,
        run_dir=f"runs/{job.id}-first",
        status="completed",
    )
    session.add(run)
    session.flush()

    draft = ResumeVersion(
        job_id=job.id,
        master_resume_id=master.id,
        claude_run_id=run.id,
        version_number=1,
        content_markdown="# first draft",
        source="claude_run",
    )
    session.add(draft)
    session.commit()

    return job, master, run, draft


def test_table_and_columns_exist_on_fresh_db(session):
    """ADR-008 fixes the column set; a fresh DB must expose it."""
    from app.db import engine

    inspector = inspect(engine)
    assert "revision_feedbacks" in inspector.get_table_names()

    columns = {c["name"]: c for c in inspector.get_columns("revision_feedbacks")}
    assert set(columns) == {
        "id",
        "job_id",
        "source_resume_version_id",
        "followup_claude_run_id",
        "feedback_markdown",
        "status",
        "created_at",
    }

    # followup_claude_run_id is the only FK that should be nullable
    # (ADR-008: "FK -> claude_runs.id, nullable"). The other FKs anchor
    # the row to its job/source draft and must be required.
    assert columns["followup_claude_run_id"]["nullable"] is True
    assert columns["job_id"]["nullable"] is False
    assert columns["source_resume_version_id"]["nullable"] is False
    assert columns["feedback_markdown"]["nullable"] is False
    assert columns["status"]["nullable"] is False


def test_fk_targets_are_correct(session):
    """source_resume_version_id -> resume_versions, followup_claude_run_id -> claude_runs."""
    from app.db import engine

    inspector = inspect(engine)
    fks_by_local_col = {
        tuple(fk["constrained_columns"]): fk for fk in inspector.get_foreign_keys("revision_feedbacks")
    }

    assert fks_by_local_col[("job_id",)]["referred_table"] == "jobs"
    assert (
        fks_by_local_col[("source_resume_version_id",)]["referred_table"]
        == "resume_versions"
    )
    assert (
        fks_by_local_col[("followup_claude_run_id",)]["referred_table"]
        == "claude_runs"
    )


def test_insert_with_null_followup_run(session):
    """A feedback row may be inserted before its follow-up run exists."""
    from app.models import RevisionFeedback

    job, _master, _run, draft = _make_job_and_draft(session)

    fb = RevisionFeedback(
        job_id=job.id,
        source_resume_version_id=draft.id,
        feedback_markdown="Please de-emphasize the leadership framing.",
    )
    session.add(fb)
    session.commit()
    session.refresh(fb)

    assert fb.id is not None
    assert fb.followup_claude_run_id is None
    assert fb.followup_claude_run is None
    assert fb.status == "created"
    assert fb.source_resume_version.id == draft.id


def test_insert_with_followup_run_resolves_relationship(session):
    """When a follow-up ClaudeRun is attached, the relationship resolves to it."""
    from app.models import ClaudeRun, RevisionFeedback

    job, master, _first_run, draft = _make_job_and_draft(session)

    followup_run = ClaudeRun(
        job_id=job.id,
        master_resume_id=master.id,
        run_dir=f"runs/{job.id}-followup",
        status="created",
    )
    session.add(followup_run)
    session.flush()

    fb = RevisionFeedback(
        job_id=job.id,
        source_resume_version_id=draft.id,
        followup_claude_run_id=followup_run.id,
        feedback_markdown="Trim the second bullet.",
    )
    session.add(fb)
    session.commit()
    session.refresh(fb)

    assert fb.followup_claude_run_id == followup_run.id
    assert fb.followup_claude_run.id == followup_run.id
    # The prior draft and the follow-up run are NOT the same run; the join
    # row is what links them, per ADR-008's "no parent_resume_version_id on
    # runs" decision.
    assert fb.source_resume_version.claude_run_id != fb.followup_claude_run_id


def test_status_lifecycle_values_are_settable(session):
    """ADR-008 lifecycle: created -> used | superseded. Run-level failures
    stay on ClaudeRun and must NOT appear as a status here."""
    from app.models import REVISION_FEEDBACK_STATUSES, RevisionFeedback

    assert REVISION_FEEDBACK_STATUSES == ("created", "used", "superseded")

    job, _master, _run, draft = _make_job_and_draft(session)

    for status in REVISION_FEEDBACK_STATUSES:
        fb = RevisionFeedback(
            job_id=job.id,
            source_resume_version_id=draft.id,
            feedback_markdown=f"feedback in status {status}",
            status=status,
        )
        session.add(fb)
    session.commit()


def test_create_schema_validates_minimal_payload(session):
    from app.schemas import RevisionFeedbackCreate

    payload = RevisionFeedbackCreate(
        feedback_markdown="Soften the executive framing in the summary.",
    )
    assert payload.feedback_markdown.startswith("Soften")
    assert payload.structured_flags is None


def test_create_schema_validates_with_structured_flags(session):
    from app.schemas import RevisionFeedbackCreate

    payload = RevisionFeedbackCreate(
        feedback_markdown="Trim the second bullet under Acme.",
        structured_flags={"too_long": True, "common_asks": ["shorten_bullets"]},
    )
    assert payload.structured_flags == {
        "too_long": True,
        "common_asks": ["shorten_bullets"],
    }


def test_create_schema_rejects_empty_feedback(session):
    from pydantic import ValidationError

    from app.schemas import RevisionFeedbackCreate

    with pytest.raises(ValidationError):
        RevisionFeedbackCreate(feedback_markdown="")


def test_read_schema_round_trips_orm(session):
    from app.models import RevisionFeedback
    from app.schemas import RevisionFeedbackRead

    job, _master, _run, draft = _make_job_and_draft(session)
    fb = RevisionFeedback(
        job_id=job.id,
        source_resume_version_id=draft.id,
        feedback_markdown="Make the summary one sentence shorter.",
    )
    session.add(fb)
    session.commit()
    session.refresh(fb)

    read = RevisionFeedbackRead.model_validate(fb)
    assert read.id == fb.id
    assert read.job_id == job.id
    assert read.source_resume_version_id == draft.id
    assert read.followup_claude_run_id is None
    assert read.feedback_markdown == "Make the summary one sentence shorter."
    assert read.status == "created"
    assert read.created_at == fb.created_at
