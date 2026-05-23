"""Seed the local SQLite database with a demo job + run + resume + application.

Run from the repo root:

    python scripts/seed_demo_data.py

The script is idempotent: if the demo job (matched by its stable URL) already
exists, it prints the existing IDs and exits without recreating anything.

This is for local development and smoke testing only. It does not call
Claude, does not contact LinkedIn or Gmail, and does not submit anything.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Make the backend package importable without installing it.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Application,
    ApplicationEvent,
    ClaudeRun,
    EvidenceBank,
    Job,
    JobCapture,
    MasterResume,
)
from app.run_directory import (  # noqa: E402
    create_run_directory,
    default_candidate_context_root,
    default_runs_root,
    default_runtime_prompts_root,
)
from app.run_import import approve_resume_version, import_run_outputs  # noqa: E402


DEMO_JOB_URL = "https://www.linkedin.com/jobs/view/demo-sciml-engineer"
DEMO_RUN_ID = "demo-run-0001"
DEMO_MASTER_RESUME_NAME = "Demo Master Resume"
DEMO_EVIDENCE_BANK_NAME = "Demo Evidence Bank"


JOB_DESCRIPTION = """Example Aero Labs is hiring a Scientific Machine Learning Engineer to build graph neural network models for chemical kinetics and molecular simulation workflows.

Responsibilities:
- Build Python and PyTorch models for molecular and reaction data.
- Develop backend workflows for scientific data provenance.
- Work with computational chemistry datasets.
- Collaborate with researchers and software engineers.

Requirements:
- Python
- PyTorch
- Graph neural networks
- Scientific software engineering
- Chemistry, materials, or molecular simulation experience
- API/backend experience preferred
"""

MASTER_RESUME_MD = """# Demo Master Resume

## Summary

PhD researcher in quantum chemistry working at the intersection of computational chemistry, machine learning, and scientific software engineering.

## Experience

### Research Software / Scientific ML
- Developed Python workflows for computational chemistry and reaction kinetics.
- Built graph neural network models for molecular and reaction-property prediction.
- Worked with PyTorch, RDKit, FastAPI, SQLAlchemy, and scientific data pipelines.

## Projects

### ARC / RMG Workflows
- Worked on automated electronic-structure and kinetic-modeling workflows.
- Used Gaussian, ORCA, CREST, and Arkane-style calculation pipelines.

### TCKDB
- Designed backend schemas and APIs for scientific chemistry data, provenance, and calculation results.
"""

EVIDENCE_BANK_MD = """# Demo Evidence Bank

- Strong evidence for Python, PyTorch, graph neural networks, computational chemistry, scientific software, FastAPI, SQLAlchemy, and RDKit.
- Strong evidence for reaction kinetics and quantum chemistry workflows.
- Moderate evidence for frontend/UI work.
- Weak evidence for large-scale production ML infrastructure.
"""

TAILORED_RESUME_MD = """# Demo Tailored Resume

## Summary

Scientific machine learning researcher with experience in computational chemistry, graph neural networks, Python, PyTorch, and backend infrastructure for scientific data workflows.

## Selected Experience

- Built graph neural network workflows for molecular and reaction-property prediction using Python and PyTorch.
- Developed computational chemistry automation workflows involving reaction kinetics and electronic-structure calculations.
- Designed backend APIs and data models for provenance-aware scientific datasets.
"""

CLAIM_AUDIT_MD = """# Claim Audit

## Supported Claims

- Python and PyTorch experience: supported by master resume and evidence bank.
- Graph neural networks: supported by master resume and evidence bank.
- Computational chemistry workflows: supported by master resume and evidence bank.
- Backend/API experience: supported by TCKDB project evidence.

## Weak or Unsupported

- Large-scale production ML infrastructure: weak support; not added as a strong claim.
"""

CHANGE_LOG_MD = """# Change Log

- Emphasized graph neural networks, PyTorch, computational chemistry, and backend scientific data workflows.
- Reordered project bullets toward the job requirements.
- Did not add unsupported production ML infrastructure claims.
"""


def _write_placeholder_docx(path: Path) -> None:
    """Write a minimal DOCX file for the demo output.

    Tries python-docx first so the file is openable in real Word readers.
    Falls back to a placeholder byte string — the importer hashes the
    bytes but does not validate OOXML structure, so this is acceptable
    for local smoke testing.
    """
    try:
        from docx import Document  # type: ignore[import-not-found]

        doc = Document()
        for line in TAILORED_RESUME_MD.splitlines():
            doc.add_paragraph(line)
        doc.save(str(path))
    except Exception:
        path.write_bytes(b"DEMO-PLACEHOLDER-DOCX\n" + TAILORED_RESUME_MD.encode("utf-8"))


def _existing_demo_job(db) -> Job | None:
    return db.query(Job).filter(Job.external_url == DEMO_JOB_URL).first()


def remove_stale_demo_run_dir(repo_root: Path) -> None:
    """Remove runs/demo-run-0001 if it exists.

    The seed script owns the fixed demo run id, so it's allowed to clear
    its own namespace before recreating it. Refuses to delete anything
    that isn't exactly runs/demo-run-0001 under repo_root.
    """
    demo_run_dir = (repo_root / "runs" / DEMO_RUN_ID).resolve()
    allowed_parent = (repo_root / "runs").resolve()

    if not demo_run_dir.exists():
        return

    if demo_run_dir.parent != allowed_parent or demo_run_dir.name != DEMO_RUN_ID:
        raise RuntimeError(f"Refusing to remove unexpected path: {demo_run_dir}")

    print(f"Removing stale demo run directory: {demo_run_dir}")
    shutil.rmtree(demo_run_dir)


def _print_summary(
    job_id: str,
    resume_version_id: str,
    application_id: str,
    *,
    header: str = "Demo data created.",
) -> None:
    print(header)
    print()
    print("Job:")
    print(f"  {job_id}")
    print("Resume version:")
    print(f"  {resume_version_id}")
    print("Application:")
    print(f"  {application_id}")
    print()
    print("Open frontend:")
    print("  http://127.0.0.1:5173")


def seed() -> int:
    Base.metadata.create_all(bind=engine)
    remove_stale_demo_run_dir(REPO_ROOT)

    db = SessionLocal()
    try:
        existing = _existing_demo_job(db)
        if existing is not None:
            resume_version = (
                existing.resume_versions[0]
                if existing.resume_versions
                else None
            )
            application = (
                existing.applications[0] if existing.applications else None
            )
            _print_summary(
                job_id=existing.id,
                resume_version_id=resume_version.id if resume_version else "(none)",
                application_id=application.id if application else "(none)",
                header="Demo data already exists.",
            )
            return 0

        capture = JobCapture(
            source_platform="linkedin",
            capture_method="manual_paste",
            external_url=DEMO_JOB_URL,
            company="Example Aero Labs",
            title="Scientific Machine Learning Engineer",
            location="Remote",
            description_text=JOB_DESCRIPTION,
            application_method="easy_apply",
            user_confirmed=True,
        )
        db.add(capture)
        db.flush()

        job = Job(
            source_platform="linkedin",
            external_url=DEMO_JOB_URL,
            company="Example Aero Labs",
            title="Scientific Machine Learning Engineer",
            location="Remote",
            description_text=JOB_DESCRIPTION,
            application_method="easy_apply",
            created_from_capture_id=capture.id,
        )
        db.add(job)
        db.flush()

        master_resume = MasterResume(
            name=DEMO_MASTER_RESUME_NAME,
            content_markdown=MASTER_RESUME_MD,
        )
        evidence_bank = EvidenceBank(
            name=DEMO_EVIDENCE_BANK_NAME,
            content_markdown=EVIDENCE_BANK_MD,
        )
        db.add_all([master_resume, evidence_bank])
        db.flush()

        info = create_run_directory(
            job=job,
            master_resume=master_resume,
            evidence_bank=evidence_bank,
            candidate_context_root=default_candidate_context_root(),
            runs_root=default_runs_root(),
            runtime_prompts_root=default_runtime_prompts_root(),
            job_capture=capture,
            run_id=DEMO_RUN_ID,
        )

        run = ClaudeRun(
            id=info.run_id,
            job_id=job.id,
            master_resume_id=master_resume.id,
            evidence_bank_id=evidence_bank.id,
            run_dir=str(info.run_dir),
            status="completed",
            prompt_hash=info.prompt_hash,
            input_hash=info.input_hash,
        )
        db.add(run)
        db.flush()

        output_dir = info.run_dir / "output"
        (output_dir / "tailored_resume.md").write_text(
            TAILORED_RESUME_MD, encoding="utf-8"
        )
        (output_dir / "change_log.md").write_text(CHANGE_LOG_MD, encoding="utf-8")
        (output_dir / "claim_audit.md").write_text(CLAIM_AUDIT_MD, encoding="utf-8")
        _write_placeholder_docx(output_dir / "tailored_resume.docx")

        db.commit()

        import_result = import_run_outputs(run.id, db)
        approved = approve_resume_version(import_result.resume_version.id, db)

        application = Application(
            job_id=job.id,
            resume_version_id=approved.id,
            status="approved",
        )
        db.add(application)
        db.flush()

        event = ApplicationEvent(
            application_id=application.id,
            event_type="resume_approved",
            notes="Demo seed: resume approved for Example Aero Labs role.",
            source="seed_demo_data",
        )
        db.add(event)
        db.commit()

        _print_summary(
            job_id=job.id,
            resume_version_id=approved.id,
            application_id=application.id,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(seed())
