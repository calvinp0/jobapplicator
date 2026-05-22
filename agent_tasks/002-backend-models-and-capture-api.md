# Task 002: Backend Models and Capture API

## Goal

Implement the first backend layer for the local-first job application cockpit.

The backend should own job captures, jobs, candidate context references, Claude runs, resume versions, applications, and application events.

## Background

Read:

- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/contracts/claude_run_directory.md`
- `docs/adr/*.md`
- `runtime_prompts/resume_tailoring.md`

## Scope

Create a small FastAPI backend using:

- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- SQLite for local development
- pytest

Implement persistent models for:

- JobCapture
- Job
- MasterResume
- EvidenceBank
- ClaudeRun
- ResumeVersion
- Application
- ApplicationEvent
- EmailLink

Implement a generic capture intake endpoint that accepts normalized payloads from capture providers.

## Important Architecture Rules

Claude Code is a worker and must not mutate the database directly.

The backend is the source of truth.

Browser capture is only one capture provider. Do not hardcode the backend as LinkedIn-only.

Captured data is untrusted until user confirmation.

Do not implement scraping, browser automation, Easy Apply clicking, resume attachment, or application submission.

## Models

Use UUID primary keys.

### JobCapture

Represents raw or structured data received from a capture provider.

Fields:

- id
- source_platform
- capture_method
- external_url
- external_job_id nullable
- company nullable
- title nullable
- location nullable
- description_text
- application_method nullable
- raw_text nullable
- captured_at
- user_confirmed boolean default false
- created_at

### Job

Represents a confirmed job record.

Fields:

- id
- source_platform
- external_url nullable
- external_job_id nullable
- company
- title
- location nullable
- description_text
- application_method nullable
- created_from_capture_id nullable
- created_at
- updated_at

### MasterResume

Represents a selectable baseline resume.

Fields:

- id
- name
- source_path nullable
- content_markdown
- created_at
- updated_at

### EvidenceBank

Represents reusable factual support material.

Fields:

- id
- name
- source_path nullable
- content_markdown
- created_at
- updated_at

### ClaudeRun

Represents one resume generation run.

Fields:

- id
- job_id
- master_resume_id
- evidence_bank_id nullable
- run_dir
- status
- prompt_hash nullable
- input_hash nullable
- output_hash nullable
- created_at
- started_at nullable
- completed_at nullable
- error_message nullable

Statuses:

- created
- running
- completed
- failed
- imported

### ResumeVersion

Represents an approved or generated resume version.

Fields:

- id
- job_id
- master_resume_id
- claude_run_id nullable
- version_number
- content_markdown nullable
- docx_path nullable
- pdf_path nullable
- content_hash nullable
- prompt_hash nullable
- source
- approved_at nullable
- created_at

### Application

Represents an application to a confirmed job.

Fields:

- id
- job_id
- resume_version_id nullable
- status
- submitted_at nullable
- created_at
- updated_at

Statuses:

- draft
- generated
- approved
- submitted
- response_received
- rejected
- interview
- offer
- withdrawn

### ApplicationEvent

Represents an event in an application timeline.

Fields:

- id
- application_id
- event_type
- event_time
- notes nullable
- source nullable
- created_at

### EmailLink

Future Gmail link placeholder.

Fields:

- id
- application_id
- gmail_message_id
- gmail_thread_id nullable
- subject nullable
- sender nullable
- received_at nullable
- classified_status nullable
- confidence nullable
- created_at

## API Endpoints

Implement:

```text
GET /health

POST /captures
GET /captures
GET /captures/{capture_id}
POST /captures/{capture_id}/confirm

POST /jobs
GET /jobs
GET /jobs/{job_id}

POST /master-resumes
GET /master-resumes
GET /master-resumes/{resume_id}

POST /evidence-banks
GET /evidence-banks
GET /evidence-banks/{evidence_bank_id}

POST /applications
GET /applications
GET /applications/{application_id}
```

## Capture Confirmation Behavior

`POST /captures/{capture_id}/confirm` should:

1. Load the capture.
2. Validate that required job fields are present:
   - company
   - title
   - description_text
3. Create a Job from the capture.
4. Mark the capture as `user_confirmed = true`.
5. Return the created job.

Do not create an Application during capture confirmation.

## Out of Scope

Do not implement run directory creation.

Do not invoke Claude Code.

Do not implement resume generation.

Do not implement frontend UI.

Do not implement the browser extension.

Do not implement Gmail.

Do not auto-submit applications.

## Tests

Add pytest tests for:

- health endpoint
- creating a capture
- confirming a capture creates a job
- confirming a capture without required fields fails clearly
- creating a job directly
- creating a master resume
- creating an evidence bank
- creating an application linked to a job
- application cannot reference a nonexistent job
- model relationships for job, ClaudeRun, ResumeVersion, and Application

## Verification

Run:

```bash
pytest
```

## Git

After changes:

1. Run tests.
2. Stage all files.
3. Commit locally with:

```text
Add backend models and capture API
```

Do not push.
