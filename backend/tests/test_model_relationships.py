"""Direct ORM-level tests for relationships between Job, ClaudeRun,
ResumeVersion, and Application.

These bypass the HTTP layer because the corresponding write endpoints
(ClaudeRun, ResumeVersion) are intentionally out of scope for task 002.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def session():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["JOBAPPLY_DATABASE_URL"] = f"sqlite:///{tmp.name}"

    for mod_name in ["app.models", "app.db", "app"]:
        sys.modules.pop(mod_name, None)

    from app.db import Base, SessionLocal, engine  # noqa: E402
    import app.models  # noqa: F401, E402  (register tables on Base.metadata)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        os.unlink(tmp.name)


def test_job_to_runs_versions_applications(session):
    from app.models import Application, ClaudeRun, Job, MasterResume, ResumeVersion

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
        run_dir=f"runs/{job.id}-run",
        status="created",
    )
    session.add(run)
    session.flush()

    version = ResumeVersion(
        job_id=job.id,
        master_resume_id=master.id,
        claude_run_id=run.id,
        version_number=1,
        content_markdown="# tailored",
        source="claude_run",
    )
    session.add(version)
    session.flush()

    application = Application(
        job_id=job.id,
        resume_version_id=version.id,
        status="generated",
    )
    session.add(application)
    session.commit()

    session.refresh(job)
    assert len(job.claude_runs) == 1
    assert job.claude_runs[0].id == run.id
    assert len(job.resume_versions) == 1
    assert job.resume_versions[0].id == version.id
    assert len(job.applications) == 1
    assert job.applications[0].id == application.id

    # ClaudeRun <-> ResumeVersion bidirectional
    assert version.claude_run.id == run.id
    assert run.resume_versions[0].id == version.id

    # Application <-> ResumeVersion bidirectional
    assert application.resume_version.id == version.id
    assert version.applications[0].id == application.id
