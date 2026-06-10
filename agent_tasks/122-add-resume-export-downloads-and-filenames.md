# Task 122: Add Resume Export Downloads, Human-Readable Filenames, and Managed Export Folders

## Goal

Make tailored resume outputs easy to find, download, and identify.

Current problem:
- Final DOCX output is always internally named `tailored_resume.docx`.
- If the user generates many tailored resumes, filenames are generic and hard to distinguish.
- Finding generated DOCX files inside run directories is painful.
- The UI should provide a clear download/export action.
- The app should optionally collect exports into a managed folder with per-application or per-run subfolders.

Do not change Gmail behavior.
Do not change browser extension behavior.
Do not remove internal run artifacts.
Do not break existing output validation.
Do not rename internal required artifacts in a way that breaks workers/tests unless aliases are preserved.

## Design Principle

Keep stable internal artifact names for machine validation:

```text
runs/<run_id>/output/tailored_resume.docx
runs/<run_id>/output/tailored_resume.json
runs/<run_id>/output/tailored_resume.md
runs/<run_id>/output/claim_audit.md
runs/<run_id>/output/ats_audit.md
runs/<run_id>/output/recruiter_review.md
```

But expose human-readable user-facing export/download names:

```text
Calvin_Pieters__Amazon__Software_Development_Engineer__2026-05-27.docx
Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx
```

The internal artifact can remain `tailored_resume.docx`; the download/export filename should be descriptive.

## Inspect

Inspect:

```text
backend/app/routers/
backend/app/run_directory.py
backend/app/run_import.py
backend/app/resume_docx_renderer.py
backend/app/models.py
backend/app/schemas.py
backend/tests/
frontend/src/pages/
frontend/src/components/
frontend/src/api/
docs/contracts/claude_run_directory.md
```

Search:

```bash
rg "tailored_resume.docx|download|artifact|output|resume.docx|run detail|Resume Review|Open resume|View run|export" backend frontend docs tests
```

Use existing project conventions.

## Part A: Human-Readable Export Filename

Add a utility that generates safe filenames from:

```text
candidate name
company
job title
date
run id short suffix if needed
```

Suggested format:

```text
Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx
```

Rules:
- replace unsafe filesystem characters
- collapse whitespace
- avoid overly long filenames
- preserve extension
- include date
- optionally include short run id for uniqueness
- no slashes
- no shell-special unsafe characters
- deterministic for a run

Suggested function:

```text
build_resume_export_filename(candidate_name, company, job_title, created_at, run_id, ext)
```

If candidate name is unavailable:

```text
Resume__Company__Job_Title__Date.docx
```

## Part B: Download Endpoint

Add or update a backend endpoint to download run artifacts.

Suggested route:

```text
GET /api/runs/{run_id}/artifacts/{artifact_name}/download
```

or use existing route conventions.

For DOCX specifically, support:

```text
GET /api/runs/{run_id}/download-resume
```

The response should:
- stream/send the artifact file
- set `Content-Disposition: attachment`
- use the human-readable filename
- return 404 if missing
- prevent path traversal
- only allow known artifact names/extensions

Allowed artifacts initially:

```text
tailored_resume.docx
tailored_resume.md
claim_audit.md
ats_audit.md
recruiter_review.md
template_fidelity_audit.md
change_log.md
```

Do not allow arbitrary file reads by user-controlled path.

## Part C: Frontend Download Buttons

Add clear download/export actions in relevant UI places:

1. Run detail page
2. Resume review workspace
3. Application detail page if a latest tailored resume exists
4. Dashboard/Application card if resume approved or draft ready, if simple

Minimum required:
- Run detail page: `Download DOCX`
- Resume review workspace: `Download DOCX`
- Application detail page/latest draft area: `Download resume`

Button behavior:
- disabled or hidden when DOCX missing
- clear error if artifact missing
- downloads with human-readable filename
- does not navigate away

Also include:
- `Download Markdown` if available
- optional `Download all artifacts` later, not required in first pass

## Part D: Managed Export Folder

Add a managed export-copy feature.

The app should be able to copy final resume artifacts to:

```text
candidate_context/exports/
```

with a subfolder per export:

```text
candidate_context/exports/
  2026-05-27__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__d6df714b/
    Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx
    tailored_resume.md
    claim_audit.md
    ats_audit.md
    recruiter_review.md
```

Add a backend action:

```text
POST /api/runs/{run_id}/export
```

or project-conventional route.

It should:
- create export folder
- copy DOCX if available
- copy markdown/audits if available
- use human-readable DOCX filename
- return export folder path and copied file list
- not overwrite existing export folders unless versioned/suffixed
- prevent path traversal

Suggested response:

```json
{
  "ok": true,
  "export_dir": "candidate_context/exports/2026-05-27__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__d6df714b",
  "files": [
    {
      "name": "Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx",
      "source": "runs/<run_id>/output/tailored_resume.docx"
    }
  ]
}
```

## Part E: Export Folder Setting

In Settings, add:

```text
Exports
Default export folder
```

First implementation can default to:

```text
candidate_context/exports/
```

If allowing a user-selected folder is complex in browser context, do not build fake local path selection. Use a backend-managed folder setting or text path with clear caveats.

Preferred first version:
- app-managed exports folder only
- show the resolved path
- provide “Open/copy path” if supported
- let user change it later as a separate task

Do not claim browser can freely choose local folders unless using Electron/native file system APIs.

## Part F: Open Folder / Copy Path

If possible, add:
- `Copy export path`
- `Open export folder`

Opening a local folder from a web browser may not be generally possible.

If not supported, show:
- exact export folder path
- copy button

Do not fake an “Open folder” button that does nothing.

## Part G: Artifact Manifest

If `output/artifact_manifest.json` exists or is planned, include export filename/provenance there.

If not, add lightweight metadata where appropriate.

Suggested:

```json
{
  "tailored_resume.docx": {
    "download_filename": "Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx",
    "created_by": "deterministic_renderer"
  }
}
```

Do not block this task on artifact manifest if not implemented.

## Tests

Add/update backend tests:

1. Filename utility sanitizes company/job/candidate names.
2. Filename utility includes candidate/company/job/date.
3. Filename utility prevents slashes/path traversal.
4. Download endpoint returns DOCX with attachment Content-Disposition.
5. Download endpoint uses human-readable filename.
6. Download endpoint returns 404 for missing artifact.
7. Download endpoint rejects unknown artifact/path traversal.
8. Export endpoint creates export subfolder.
9. Export endpoint copies DOCX with human-readable filename.
10. Export endpoint copies markdown/audit artifacts when present.
11. Export endpoint handles duplicate export folder names safely.
12. Export endpoint does not read/write outside managed export root.

Add/update frontend tests if infrastructure exists:

1. Run detail shows Download DOCX when artifact exists.
2. Run detail hides/disables Download DOCX when missing.
3. Resume review workspace shows Download DOCX.
4. Download action calls correct endpoint.
5. Export action shows exported folder path.
6. Application detail shows Download resume for latest draft.
7. Error state appears when artifact missing.

## Acceptance Criteria

- User can download a tailored resume DOCX from the UI.
- Downloaded DOCX has a descriptive filename, not just `tailored_resume.docx`.
- Internal run artifact path can remain `output/tailored_resume.docx`.
- User can export/copy artifacts into a managed exports folder.
- Export folder uses per-run/per-application subfolders.
- UI clearly shows export/download success and path.
- Missing DOCX is handled gracefully.
- Existing run validation still works.
- Frontend builds and tests pass.
- Backend tests pass.

## Verification

Run:

```bash
python -m pytest
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Generate or use a run with `output/tailored_resume.docx`.
2. Open run detail page.
3. Click `Download DOCX`.
4. Confirm downloaded filename is descriptive, e.g.:

```text
Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx
```

5. Open resume review workspace.
6. Confirm `Download DOCX` is available.
7. Click export/copy to managed export folder.
8. Confirm files exist under:

```text
candidate_context/exports/<date>__<company>__<job>__<run>/
```

9. Confirm internal artifact still exists at:

```text
runs/<run_id>/output/tailored_resume.docx
```

10. Confirm missing DOCX shows a clear disabled/error state.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add resume export downloads
```

Do not push.
