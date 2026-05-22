# Product Requirements

## Goal

Build aq local-first job application cockpit that helps a user tailor resumes, track job applicaitons, version submitted resumes, and later link Gmail responses.

## MMVP Workflow

1. User opens LinkedIn job.
2. User selects the job description, title, and company block.
3. User presses a global hotkey.
4. App captures clipboard/selection text.
5. App extracts:
   - company
   - job title
   - job URL
   - description
   - Easy Apply/manual apply if visible
6. App shows extracted job card for confirmation.
7. User clicks Generate Resume.
8. App creates Claude Code run.
9. Claude generates DOCX.
10. App opens the generated DOCX path.
11. User attaches it in LinkedIn manually.
12. User clicks Mark Submitted in sidecar.

## Non-goals

- No automatic LinkedIn submission.
- No scraping job sites at scale.
- No autonomous application sending.
- No unsupported resume claims.

## Core Requirements

- Every submitted application must link to the exact resume version used.
- Resume generation must be evidence-constrained.
- Claude Code must not mutate the database directly.
- Human approval is required before a resume version is marked approved.

## Job Intake

The primary MVP intake path is browser-assisted current-page capture.

The user opens a job posting in their normal browser session and explicitly clicks a capture action in the browser extension or sidecar app. The capture action extracts structured job context from the currently loaded page and sends it to the local backend.

The extracted job card must be shown to the user for confirmation before the application record is created.

The system should support fallback intake through clipboard capture and manual paste.

Allowed capture behavior:
- extract from the currently loaded job page after explicit user action
- capture job title, company, location, URL, description, and application method if visible
- send the captured payload to the local backend
- require user confirmation before resume generation

Forbidden behavior:
- autonomous browsing
- background crawling
- batch scraping search results
- profile/contact harvesting
- auto-clicking Easy Apply
- auto-attaching files
- auto-submitting applications
- auto-messaging recruiters



## Resume Tailoring

Tailored resumes must be evidence-constrained.

The app may rewrite, reorder, and emphasize existing experience, but it must not invent unsupported claims.

## Resume Versioning

Every approved/generated resume must be stored as a version linked to:

- job
- master resume
- Claude run
- generated files
- prompt hash
- output hash
- approval state

## Application Tracking

The app tracks:

- company
- job title
- job URL
- source platform
- application method
- resume version used
- submitted date
- status
- events

## Non-Goals

- No autonomous job searching.
- No automatic Easy Apply clicking.
- No automatic resume attachment.
- No automatic submission.
- No recruiter messaging automation.
- No Gmail integration in the first MVP.
