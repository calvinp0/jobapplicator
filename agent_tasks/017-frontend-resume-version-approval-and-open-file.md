# Task 017: Frontend resume-version review, approval, and open generated file

## Goal

Give the operator a UI for the approval step required by the product
requirements: list a job's resume versions, review the one produced
by a run, open the generated DOCX from the OS, and mark a version
approved before it can be attached to an application. This is the
human-in-the-loop checkpoint between Claude's output and submitting
the application.

## Background

Read:

- `docs/product_requirements.md` (resume versioning, human approval
  rule, MMVP step 10)
- `docs/adr/003-human-in-the-loop-submission.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `backend/app/routers/resume_versions.py` (existing list, get,
  approve)
- `backend/app/routers/files.py` (open-file endpoint added by task
  014)
- `agent_tasks/008-resume-version-import.md`
- `agent_tasks/014-backend-application-submit-and-open-file.md`
- `agent_tasks/016-frontend-runs-list-and-detail.md` (the
  `ResumeVersion` type and `listResumeVersions` / `getResumeVersion`
  helpers added there are reused here)
- `frontend/src/pages/JobDetailPage.tsx`

## Scope

Within `frontend/src/`:

- Add API client functions in `frontend/src/api/index.ts`:
  - `approveResumeVersion(id)` → `POST /resume-versions/{id}/approve`
  - `openResumeVersionFile(id)` → `POST /files/open` with the
    resume-version id (or its `docx_path`), as defined by the
    endpoint added in task 014
- Add a new page `frontend/src/pages/ResumeVersionDetailPage.tsx`
  with route `/resume-versions/:versionId`:
  - Show version number, job, source, hashes (truncated), created_at,
    approved_at.
  - Show paths to `docx_path` and `pdf_path`/`content_markdown` if
    present.
  - Buttons:
    - **Open DOCX** — calls `openResumeVersionFile` if a `docx_path`
      is set; disabled otherwise.
    - **Approve** — calls `approveResumeVersion`; disabled when
      `approved_at` is already set. After approval, refresh the row
      and reflect "Approved on …".
  - Surface backend errors using the existing `ApiError.message` /
    body pattern.
- Register the new route in `frontend/src/App.tsx`.
- Extend `frontend/src/pages/JobDetailPage.tsx` with a "Resume
  versions" section listing the versions for this job (using
  `listResumeVersions` filtered client-side by `job_id`), showing
  version number, status (approved or pending), and a link to the
  detail page. Place this section above the "Generate tailored
  resume" form so the operator sees existing versions first.
- Update `frontend/src/pages/RunDetailPage.tsx` only to make the
  "imported version" link target the new `/resume-versions/:id`
  route. Do not refactor anything else.
- Tests in `frontend/src/test/`:
  - Resume version detail: renders with mocked API.
  - Approve flow: clicking Approve calls the API and the page
    reflects the approved state.
  - Open DOCX: clicking Open calls `openResumeVersionFile` exactly
    once; the button is disabled when `docx_path` is null.
  - Job detail: the "Resume versions" section lists versions for the
    job and links to detail.

## Allowed files

- `frontend/src/pages/ResumeVersionDetailPage.tsx`
- `frontend/src/pages/JobDetailPage.tsx`
- `frontend/src/pages/RunDetailPage.tsx` (link target only)
- `frontend/src/App.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly
  instructed)

## Forbidden files

- `backend/**`
- `extension/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/**`
- Other `agent_tasks/*.md`
- Other frontend pages and layout

## Out of scope

- Applications submit flow (task 018).
- Editing resume version content from the UI.
- Re-running a Claude run from this page.
- Comparing two resume versions or showing diffs.
- Re-approval semantics beyond what the backend already enforces.

## Acceptance criteria

- `/jobs/:jobId` shows existing resume versions and links to them.
- `/resume-versions/:versionId` shows version metadata and exposes
  Approve and Open DOCX actions consistent with the backend.
- Approval state is reflected after a successful approve call without
  a full page reload.
- Open DOCX is gated on the presence of `docx_path`.
- `npm test` and `npm run build` pass from `frontend/`.
- No backend, extension, or doc files are touched.

## Verification

Run from `frontend/`:

```bash
npm test
npm run build
```

## Git instructions

Commit message:

```text
Add resume version approval and open generated file flow
```

Do not push.
