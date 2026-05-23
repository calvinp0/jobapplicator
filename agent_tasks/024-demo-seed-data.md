# Task 024: Add Demo Seed Data Script

## Goal

Add a local demo seed script so the app can be tested end-to-end without needing LinkedIn, Gmail, or a real job application.

The script should create realistic fake records for the local MVP workflow:

```text
job capture
confirmed job
master resume
evidence bank
Claude run
fake generated resume outputs
imported resume version
approved resume version
application
application event
```

This is for local development and smoke testing only.

Do not implement LinkedIn automation.
Do not implement Gmail.
Do not change production behavior.

## Background

Read:

```text
docs/product_requirements.md
docs/architecture.md
docs/contracts/claude_run_directory.md
backend/app/models or backend/app/db models
backend/app/routers/
backend/app/run_directory.py
backend/app/run_import.py
```

## Scope

Create:

```text
scripts/seed_demo_data.py
```

Optionally update:

```text
README.md
docs/smoke_tests/app_only_mvp.md
```

## Required Behavior

The script should be runnable from repo root:

```bash
python scripts/seed_demo_data.py
```

or, if the backend package requires module execution:

```bash
python -m scripts.seed_demo_data
```

The script should create a small demo dataset in the local SQLite database used by the app.

## Demo Content

Use a fake job:

```text
Company: Example Aero Labs
Title: Scientific Machine Learning Engineer
Location: Remote
Source platform: linkedin
Application method: easy_apply
URL: https://www.linkedin.com/jobs/view/demo-sciml-engineer
```

Job description:

```text
Example Aero Labs is hiring a Scientific Machine Learning Engineer to build graph neural network models for chemical kinetics and molecular simulation workflows.

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
```

Use a fake master resume:

```text
# Demo Master Resume

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
```

Use a fake evidence bank:

```text
# Demo Evidence Bank

- Strong evidence for Python, PyTorch, graph neural networks, computational chemistry, scientific software, FastAPI, SQLAlchemy, and RDKit.
- Strong evidence for reaction kinetics and quantum chemistry workflows.
- Moderate evidence for frontend/UI work.
- Weak evidence for large-scale production ML infrastructure.
```

## Run Directory

The script should create a demo run directory using the existing run-directory logic if possible.

It should create fake output files:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

The DOCX can be a simple placeholder file if real DOCX generation is not already available, but if the import logic requires a valid DOCX, create a minimal valid DOCX using `python-docx` if available or a simple backend utility.

Fake tailored resume markdown:

```text
# Demo Tailored Resume

## Summary

Scientific machine learning researcher with experience in computational chemistry, graph neural networks, Python, PyTorch, and backend infrastructure for scientific data workflows.

## Selected Experience

- Built graph neural network workflows for molecular and reaction-property prediction using Python and PyTorch.
- Developed computational chemistry automation workflows involving reaction kinetics and electronic-structure calculations.
- Designed backend APIs and data models for provenance-aware scientific datasets.
```

Fake claim audit:

```text
# Claim Audit

## Supported Claims

- Python and PyTorch experience: supported by master resume and evidence bank.
- Graph neural networks: supported by master resume and evidence bank.
- Computational chemistry workflows: supported by master resume and evidence bank.
- Backend/API experience: supported by TCKDB project evidence.

## Weak or Unsupported

- Large-scale production ML infrastructure: weak support; not added as a strong claim.
```

Fake change log:

```text
# Change Log

- Emphasized graph neural networks, PyTorch, computational chemistry, and backend scientific data workflows.
- Reordered project bullets toward the job requirements.
- Did not add unsupported production ML infrastructure claims.
```

## Idempotency

The script should be safe to rerun.

Use stable names/URLs to detect existing demo records.

If records already exist, either:

- update them in place, or
- print that demo data already exists and exit cleanly.

Do not create duplicate demo jobs on every run.

## Output

At the end, print:

```text
Demo data created.

Job:
  <job id>
Resume version:
  <resume version id>
Application:
  <application id>

Open frontend:
  http://127.0.0.1:5173
```

## Out of Scope

Do not implement Gmail.

Do not implement LinkedIn capture.

Do not call Claude.

Do not submit applications.

Do not require browser extension.

Do not change production app behavior.

## Verification

Run:

```bash
python scripts/seed_demo_data.py
pytest
```

If frontend is available:

```bash
cd frontend && npm test && npm run build
```

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Add demo seed data script
```

Do not push.
