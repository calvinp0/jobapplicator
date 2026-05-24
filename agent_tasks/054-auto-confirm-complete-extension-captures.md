# Task 054: Auto-Confirm Complete Extension Captures

## Goal

Make browser extension capture feel seamless.

Current browser flow:

```text
Extension captures a LinkedIn job
→ backend stores it as a Capture
→ user must open Captures
→ user must confirm it manually
→ backend creates Job
→ user navigates to Job
```

This is too clunky now that the extension can reliably capture title, company, location, URL, and description.

New desired flow:

```text
Extension captures a complete LinkedIn job
→ backend stores the Capture
→ backend automatically confirms it into a Job
→ extension receives job_id
→ user can open the Job workspace directly
```

The Captures page should remain useful for incomplete or ambiguous captures.

Do not implement LinkedIn Easy Apply automation.
Do not implement Gmail.
Do not change resume tailoring behavior.

## Background

Inspect:

```text
extension/**
backend/app/routers/captures.py
backend/app/schemas.py
backend/app/models.py
backend/tests/**
frontend/src/pages/CapturesPage.tsx
frontend/src/pages/CaptureDetailPage.tsx
frontend/src/pages/JobDetailPage.tsx
docs/product_requirements.md
```

The extension now captures LinkedIn descriptions reliably. A complete extension capture should not force the user through an extra approval step unless required fields are missing.

## Scope

Update as needed:

```text
backend/app/routers/captures.py
backend/app/schemas.py
backend/app/models.py
backend/tests/**
extension/**
frontend/src/pages/CapturesPage.tsx
frontend/src/pages/CaptureDetailPage.tsx
frontend/src/test/**
```

Do not edit unrelated backend/frontend behavior.

## Required Behavior

### 1. Define a complete capture

A capture is complete if it has non-empty:

```text
title
company
url
description
```

Location is useful but should not block auto-confirm, because some remote roles or scraped pages may omit it.

### 2. Auto-confirm complete extension captures

When the extension sends a complete capture to the backend, the backend should:

```text
1. create the Capture row
2. create or reuse the corresponding Job row
3. mark the Capture as confirmed, if the model supports that state
4. return the created/reused job_id in the response
```

If existing backend design uses a separate confirm endpoint, preserve it for incomplete/manual captures.

### 3. Preserve manual review for incomplete captures

If required fields are missing, keep the current behavior:

```text
create Capture only
do not create Job
frontend Captures page shows missing fields
user can review/confirm manually
```

### 4. Avoid duplicate jobs

If the same URL is captured again, prefer reusing the existing Job instead of creating duplicates.

Suggested matching key:

```text
url
```

If the current models do not enforce URL uniqueness, implement safe lookup-before-create rather than a broad schema migration unless already needed.

### 5. Extension UX

After sending a complete capture, the extension popup should show:

```text
Job created
Open job workspace
```

or:

```text
Job already exists
Open job workspace
```

The extension should use the returned `job_id` to build a frontend link:

```text
http://localhost:5173/jobs/<job_id>
```

If the capture is incomplete, keep current popup behavior:

```text
Captured. Review fields, then send.
```

or:

```text
Sent to backend. Review in Captures.
```

### 6. API response shape

If needed, extend the capture create response with optional fields:

```json
{
  "id": "...",
  "title": "...",
  "company": "...",
  "url": "...",
  "description": "...",
  "job_id": "...",
  "auto_confirmed": true
}
```

Use the existing schema style in the project.

### 7. Frontend Captures behavior

If a capture is already auto-confirmed, the Captures page/detail page should make that clear:

```text
Job created
Open job
```

It should not invite the user to confirm it again.

If changing frontend is too much for this task, keep it minimal and ensure the extension can open the job directly.

## Acceptance Criteria

- Complete extension captures create/reuse a Job automatically.
- Incomplete captures still go to Captures for manual review.
- Duplicate captures by URL do not create duplicate Jobs.
- Backend response includes enough information for the extension to open the Job workspace.
- Extension popup offers an `Open job workspace` action after successful auto-confirm.
- Existing manual capture confirmation still works.
- Backend tests pass.
- Extension build passes.
- Frontend tests pass if frontend is touched.

## Verification

Run:

```bash
pytest backend/tests
cd extension && npm install
cd extension && npm run build
```

If frontend is touched, also run:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Manual verification:

1. Start backend and frontend.
2. Load the unpacked extension.
3. Open a LinkedIn job page with title, company, URL, and description.
4. Capture/send from the extension.
5. Confirm the popup says the job was created or reused.
6. Click/open the job workspace link.
7. Confirm the frontend opens `/jobs/<job_id>`.
8. Repeat capture on the same URL and confirm it reuses the same job.
9. Test an incomplete capture and confirm it still appears in Captures for manual review.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Auto-confirm complete extension captures
```

Do not push.
