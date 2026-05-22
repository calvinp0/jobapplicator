# Architecture

## Components

- Frontend: local web UI for job review, resume generation, run status, application tracking, and resume approval.
- Backend: FastAPI service that owns the database, run directories, file hashes, resume versions, and application records.
- Browser extension: optional current-page capture helper for job pages.
- Claude Code worker: local process invoked by the backend to generate resume artifacts.
- Database: local SQLite for MVP.
- Runtime prompts: versioned prompt files used by Claude Code.


## Components

- Frontend: local UI for reviewing jobs, runs, resumes, and applications.
- Backend: FastAPI service that owns the database, run directories, hashes, and application records.
- Browser extension: optional current-page capture provider.
- Claude Code worker: local process used to generate resume artifacts.
- Database: local SQLite for MVP.
- Runtime prompts: markdown prompts used by Claude Code.
- Candidate context: reusable markdown source material for resume tailoring.

## Capture Provider Architecture

Job intake is handled by pluggable capture providers.

Initial providers:

- manual paste capture
- clipboard capture
- selected-text capture
- browser-extension current-page capture

All capture providers produce a normalized job capture payload.

The core backend should not depend on LinkedIn-specific logic.

## Browser Assistance Boundary

Allowed:

- user-triggered current-page job capture
- user-triggered clipboard capture
- user-triggered selected-text capture
- storing job URL
- extracting structured fields from captured job text
- detecting visible application method such as Easy Apply
- opening generated resume files
- recording user-confirmed workflow events

Forbidden:

- autonomous browsing
- background crawling
- batch scraping job search results
- profile/contact harvesting
- automatic Easy Apply clicking
- automatic resume attachment
- automatic form submission
- automatic recruiter messaging

## Claude Code Worker Boundary

Claude Code is a worker, not the source of truth.

The backend creates run directories, writes inputs, invokes Claude Code, validates outputs, computes hashes, and imports approved files.

Claude Code must not directly mutate the database.

## Candidate Context

Persistent candidate context lives in `candidate_context/`.

Each Claude run receives a snapshot of selected candidate context under `runs/<run_id>/input/`.

## Human-in-the-Loop Rule

The system may capture job context, generate resumes, and track applications.

The user confirms the job, approves the resume, attaches the resume, and submits the application manually.

## Capture Provider Architecture

Job intake is handled through pluggable capture providers.

Initial providers:

- manual paste capture
- clipboard capture
- selected-text capture
- browser-extension current-page capture

The core backend should not depend on LinkedIn-specific logic. LinkedIn parsing belongs in the browser extension or a narrow capture parser module.

All capture providers must produce a normalized job capture payload.

Example payload:

```json
{
  "source_platform": "linkedin",
  "capture_method": "browser_extension_current_page",
  "external_url": "https://www.linkedin.com/jobs/view/...",
  "external_job_id": "optional",
  "company": "Example Corp",
  "title": "Machine Learning Engineer",
  "location": "Remote",
  "description_text": "...",
  "application_method": "easy_apply",
  "captured_at": "2026-05-22T12:00:00+03:00",
  "raw_text": "...",
  "user_confirmed": false
}
