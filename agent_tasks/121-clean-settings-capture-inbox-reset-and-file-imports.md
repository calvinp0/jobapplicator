# Task 121: Clean Settings, Capture Inbox, Reset Button, and File Imports

## Goal

Clean up several confusing parts of the app:

1. Capture Inbox currently serves no clear purpose.
2. Settings has “Reset local data” but it is not an actual usable in-app button/action.
3. Settings forms for “Add evidence bank” and “Add master resume” currently expose `Source Path` as a text field.
4. Instead of typing paths manually, users should choose a file through a file picker/upload flow.
5. Imported files should be copied into the app-managed candidate context folders so the app owns stable copies.

Do not change Gmail behavior.
Do not change browser extension capture submission unless needed to keep capture ingestion working.
Do not remove backend capture support if the extension still uses it.
Do not destroy user data without explicit confirmation.
Do not silently reset local data.

## Background

The app is evolving into a job application cockpit.

The current `Capture Inbox` route/nav is confusing because the user no longer directly works from it. Browser extension captures may still exist as an intake mechanism, but the page itself does not currently provide enough value.

Settings also needs to become the place where the user can:
- manage master resumes
- manage evidence banks / evidence sources
- import local files
- reset local development data safely

## Part A: Capture Inbox Cleanup

Inspect current capture usage.

Search:

```bash
rg "Capture Inbox|Captures|capture|pending capture|captures" frontend/src backend/app backend/tests extension
```

Determine whether:
- browser extension still posts captures to backend
- pending captures are still reviewed anywhere
- captures are converted into jobs/applications
- Capture Inbox route is still useful

### Required behavior

If Capture Inbox is unused from the user’s perspective:
- remove it from primary navigation
- keep route/backend support if extension depends on it
- optionally move it under Settings or Activity as “Capture intake”
- show it only when pending captures exist, if that data is available

If Capture Inbox still has pending-capture review functionality:
- rename it to something clearer, such as `Capture Intake`
- demote it from primary nav
- add an empty state explaining what it is for

Suggested empty state:

```text
No pending captures.
Jobs captured from the browser extension will appear here before they are converted into applications.
```

Acceptance:
- The sidebar should not prominently show a useless Capture Inbox page.
- Browser extension capture submission should still work.

## Part B: In-App Reset Local Data Button

Settings currently mentions reset/local data but does not provide a proper button/action.

Add a real Settings reset control.

### UI requirements

In Settings, add a section:

```text
Danger Zone
Reset local data
```

Include:
- clear explanation of what will be deleted
- a destructive button
- confirmation modal/dialog
- require explicit confirmation text if feasible, e.g. type `RESET`
- show success/failure message

Example copy:

```text
Reset local data
This will delete local jobs, applications, runs, captures, drafts, Gmail tracking state, and generated artifacts. It will not delete your source files outside JobApplicator.
```

Button:

```text
Reset local data
```

Confirmation:

```text
Type RESET to confirm.
```

### Backend requirements

Use existing backup/reset tooling if it exists.

Search:

```bash
rg "reset|backup|local data|delete all|database|candidate_context|runs" backend scripts docs frontend/src
```

If there is already safe reset code from the backup/reset task, wire the UI to it.

If no endpoint exists, add one carefully:

```text
POST /api/settings/reset-local-data
```

or project-conventional route.

The endpoint must:
- require explicit confirmation payload
- create a backup first if existing backup tooling exists
- delete/reset local app database data
- clean run/generated artifact data if that is the intended reset scope
- not delete arbitrary external files
- not delete source files outside the project
- return a clear result summary

Suggested request:

```json
{
  "confirmation": "RESET"
}
```

Suggested response:

```json
{
  "ok": true,
  "backup_path": "backups/reset-2026-...",
  "deleted": {
    "applications": 4,
    "jobs": 6,
    "runs": 12,
    "captures": 1
  }
}
```

If the app has dev/demo data, optionally include:

```text
Reset and reseed demo data
```

but keep that separate from plain reset.

## Part C: Replace Source Path Text Fields with File Import

Settings currently has forms for:
- Add evidence bank
- Add master resume

These include:
- Name
- Content
- Source Path

The `Source Path` field should not be a manual text field.

### Browser limitation

In a normal browser, file picker uploads do not reliably expose a full local source path for security reasons.

Therefore, implement file import as:

```text
Choose file -> upload file -> backend copies file into app-managed folder -> store managed path
```

Do not depend on a user-typed absolute local path.

### Master Resume import

For “Add master resume”:
- allow choosing `.docx`, `.md`, `.txt`, maybe `.pdf` only if supported
- send file to backend
- backend copies file into:

```text
candidate_context/master_resumes/
```

or existing project convention.

If DOCX:
- store original DOCX copy
- optionally extract text into `.md` companion if existing extraction logic supports it
- register it as a master resume source/version

Suggested managed path:

```text
candidate_context/master_resumes/<safe_slug>.<ext>
```

### Evidence Bank import

For “Add evidence bank”:
- allow choosing `.md`, `.txt`, `.docx`, maybe `.pdf` only if supported
- backend copies file into a managed evidence folder.

Preferred target depends on source type:
- evidence bank text file:

```text
candidate_context/evidence_banks/
```

- project notes:

```text
candidate_context/project_notes/
```

- resume variants:

```text
candidate_context/resume_variants/
```

For first implementation, use:

```text
candidate_context/evidence_banks/
```

unless the UI lets user select evidence type.

### UI requirements

Replace `Source Path` text input with:

```text
Source file
[Choose file]
selected-file.docx
```

Keep:
- Name field
- Content field for manual paste/edit

But clarify modes:

```text
Option A: Upload a source file
Option B: Paste content manually
```

If both file and content are provided, define behavior clearly:
- either reject as ambiguous
- or use file as source and content as notes
- preferred: allow one mode at a time for first implementation

Recommended first version:
- File upload mode OR manual content mode
- disable/source-path field entirely

### Backend upload endpoints

Add endpoints such as:

```text
POST /api/settings/master-resumes/import-file
POST /api/settings/evidence-sources/import-file
```

or use existing settings routes.

Use multipart file upload.

Backend should:
- validate extension
- sanitize filename
- prevent path traversal
- copy into managed candidate_context folder
- avoid overwriting existing files without versioning
- store metadata in existing database/settings structure
- return created source object

Filename collision behavior:
- append timestamp or numeric suffix

Example:

```text
calvin_pieters_resume.docx
calvin_pieters_resume_2.docx
```

### Original path metadata

If the frontend can provide a filename, store it as:

```text
original_filename
```

Do not require full source path.

If the app currently has `source_path`, it should become:
- managed app path
- or display as `stored_path`

Avoid showing it as a user-editable field.

## Part D: Copy vs Keep Original File

Decision:

```text
Copy imported files into app-managed folders.
```

Reason:
- app remains stable if original file moves
- tailoring runs can reliably access evidence
- backups/export are easier
- no dependency on arbitrary local paths
- safer than letting users type paths

Store metadata:

```text
original_filename
stored_path
source_type
imported_at
```

Do not rely on the original source location after import.

## Part E: Settings Information Architecture

Settings should have clearer sections:

```text
Profile / Candidate Context
Master Resumes
Evidence Sources
Gmail Connection
Data Management
Danger Zone
```

This task only needs to polish the relevant sections, not fully redesign all Settings.

## Tests

Add/update backend tests:

1. Master resume file import accepts `.docx`.
2. Master resume file import copies file into managed folder.
3. Evidence source file import accepts `.md`/`.txt`.
4. Evidence source file import copies file into managed folder.
5. Import rejects unsupported extension.
6. Import sanitizes unsafe filenames.
7. Import prevents path traversal.
8. Import handles duplicate filenames without overwriting.
9. Reset endpoint rejects missing/wrong confirmation.
10. Reset endpoint succeeds with correct confirmation.
11. Reset endpoint does not delete files outside project.
12. Capture backend routes still work if extension depends on them.

Add/update frontend tests if infrastructure exists:

1. Settings shows file picker for master resume import.
2. Settings no longer shows editable Source Path field.
3. Settings shows file picker for evidence import.
4. File selection displays selected filename.
5. Manual content mode still works if supported.
6. Reset local data button opens confirmation dialog.
7. Reset action requires explicit confirmation.
8. Capture Inbox is hidden/demoted when no pending captures.
9. Capture route still renders empty state if visited directly.

## Acceptance Criteria

- Capture Inbox no longer appears as a useless primary nav item.
- Browser extension capture ingestion still works.
- Settings has a real Reset local data button.
- Reset requires confirmation and is safe.
- Add master resume uses a file picker/upload flow, not manual Source Path editing.
- Add evidence bank/source uses a file picker/upload flow, not manual Source Path editing.
- Imported files are copied into app-managed candidate context folders.
- Metadata stores managed path/original filename.
- Existing manually pasted content flow still works or is clearly separated.
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

1. Start backend/frontend.
2. Open sidebar.
3. Confirm Capture Inbox is gone, demoted, or only appears when useful.
4. Open Settings.
5. Confirm Reset local data is a real button.
6. Click Reset local data.
7. Confirm confirmation dialog appears.
8. Confirm wrong confirmation does not reset.
9. Import a master resume DOCX.
10. Confirm file is copied into:

```text
candidate_context/master_resumes/
```

11. Import an evidence `.md` or `.txt`.
12. Confirm file is copied into:

```text
candidate_context/evidence_banks/
```

13. Confirm Settings shows imported source metadata.
14. Confirm no editable `Source Path` text field remains.
15. Confirm existing tailoring can see the imported master resume/evidence source.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Clean settings imports and reset local data
```

Do not push.
