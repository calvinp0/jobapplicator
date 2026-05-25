# Task 081: Discover Master Resumes from Candidate Context

## Goal

Make real master resume files placed in:

```text
candidate_context/master_resumes/
```

appear in the frontend master resume selector/list.

Currently the frontend shows seeded/demo database data such as:

```text
Demo Master Resume
```

but newly added `.docx` files under `candidate_context/master_resumes/` do not appear.

Do not change Claude tailoring behavior in this task.  
Do not implement Gmail.  
Do not implement LinkedIn automation.  
Do not implement new DOCX extraction for runs unless needed for integration.  
Do not solve this by editing demo seed constants.

## Observed Evidence

Running:

```bash
rg "Demo"
```

shows:

```text
scripts/seed_demo_data.py
DEMO_MASTER_RESUME_NAME = "Demo Master Resume"
MASTER_RESUME_MD = """# Demo Master Resume
```

Running:

```bash
rg "master_resume" backend frontend scripts
rg "candidate_context" backend frontend scripts
```

shows:

```text
backend/app/routers/master_resumes.py
backend/app/models.py
backend/app/run_directory.py
backend/app/docx_extract.py
scripts/seed_demo_data.py
frontend/src/api/types.ts
frontend/src/api/index.ts
frontend/src/pages/JobDetailPage.tsx
```

The run directory layer already writes selected database resume content to:

```text
runs/<run_id>/input/master_resume.md
```

via:

```text
backend/app/run_directory.py
_write_text(input_dir / "master_resume.md", master_resume.content_markdown)
```

The project also already has DOCX extraction logic for run inputs:

```text
backend/app/docx_extract.py
```

and tests referencing:

```text
master_resume_extracted.md
master_resume.docx
```

Therefore, the missing piece is likely that `backend/app/routers/master_resumes.py` lists database `MasterResume` rows only and does not discover/import filesystem files from:

```text
candidate_context/master_resumes/
```

## Inspect

Inspect:

```text
backend/app/routers/master_resumes.py
backend/app/models.py
backend/app/schemas.py
backend/app/database.py
backend/app/run_directory.py
backend/app/docx_extract.py
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/pages/JobDetailPage.tsx
scripts/seed_demo_data.py
backend/tests/test_master_resumes.py
backend/tests/test_api.py
frontend tests if present
```

Also inspect the actual directory:

```bash
find candidate_context/master_resumes -maxdepth 2 -type f
```

## Required Behavior

The backend should discover master resume files from:

```text
candidate_context/master_resumes/
```

Supported file types for this task:

```text
.docx
.md
.txt
```

For every discovered file, expose it through the master resume API so the frontend can show/select it.

The frontend should no longer show only the seeded demo resume when real files exist.

## Important Design Requirement

Do not make real resumes appear by editing:

```text
scripts/seed_demo_data.py
DEMO_MASTER_RESUME_NAME
MASTER_RESUME_MD
```

The app should discover actual files from:

```text
candidate_context/master_resumes/
```

Demo seed data may remain as fallback only.

## Data Model Options

Use whichever approach best fits the existing architecture.

### Option A: Filesystem-backed records returned by API

The list endpoint can combine:

```text
database MasterResume rows
filesystem master resume files
```

Filesystem entries should have stable IDs derived from their relative path, for example:

```text
fs:<hash-or-slug>
```

They should include metadata:

```json
{
  "id": "fs:<stable-id>",
  "name": "calvin_resume.docx",
  "content_markdown": "",
  "source_path": "candidate_context/master_resumes/calvin_resume.docx",
  "source_format": "docx",
  "source": "filesystem"
}
```

When a run is created using a filesystem-backed resume, the backend must be able to resolve that ID and stage the real file into the run input directory.

For `.docx`, stage it as:

```text
runs/<run_id>/input/master_resume.docx
```

If extracted markdown is available or can be created, also stage:

```text
runs/<run_id>/input/master_resume_extracted.md
```

But do not duplicate existing DOCX extraction logic unnecessarily.

### Option B: Import/sync filesystem files into database

Add a discovery/import step that creates or updates `MasterResume` database rows for files in:

```text
candidate_context/master_resumes/
```

Each imported row should preserve:

```text
source_path
source_format
source = filesystem
```

If the existing `MasterResume` model lacks these fields, add them with a migration or equivalent storage update.

For `.docx`, the database row may store extracted markdown in `content_markdown`, but the original source path must be preserved so run creation can copy the DOCX into:

```text
runs/<run_id>/input/master_resume.docx
```

Choose this option only if it fits the existing persistence model.

## Required API Metadata

The master resume list API should expose enough for the frontend to show file-backed resumes.

Include fields where possible:

```json
{
  "id": "stable-id",
  "name": "calvin_resume.docx",
  "source": "filesystem",
  "source_path": "candidate_context/master_resumes/calvin_resume.docx",
  "source_format": "docx",
  "updated_at": "...",
  "is_demo": false
}
```

Avoid exposing absolute filesystem paths if the existing API avoids them.

## Run Creation Requirement

When creating a run with a discovered `.docx` master resume, the run input directory must include:

```text
input/master_resume.docx
```

The existing worker/docx extraction layer can then produce:

```text
input/master_resume_extracted.md
```

The run should still include `input/master_resume.md` if markdown content is available or extracted. If not available at run creation time, the worker extraction step must still be able to proceed from `master_resume.docx`.

Do not break existing database-backed markdown resumes.

## Frontend Requirements

The master resume selector/list should display discovered files from the backend.

For `.docx` files, show a clear badge:

```text
DOCX
```

For markdown/text files:

```text
MD
TXT
```

If both seeded demo data and filesystem resumes exist, prefer showing filesystem resumes first.

If no filesystem resumes exist, keeping the existing demo fallback is acceptable.

## Refresh Behavior

The app should pick up newly added files after backend restart at minimum.

If easy, make the master resume list endpoint scan on request so a backend restart is not required.

Do not require a full database seed reset to see new files.

## File Filtering

Ignore hidden/temp files:

```text
.~lock*
~$*
.DS_Store
```

Ignore unsupported extensions.

If two files have the same display name, keep both but generate distinct stable IDs.

## Tests

Add or update backend tests to prove:

1. `.docx` files in `candidate_context/master_resumes/` are discovered.
2. `.md` files in `candidate_context/master_resumes/` are discovered.
3. `.txt` files in `candidate_context/master_resumes/` are discovered.
4. Unsupported files are ignored.
5. Temporary Word lock files are ignored.
6. Returned IDs are stable across repeated list calls.
7. Returned metadata includes name/filename, source, source_format, and source_path or equivalent.
8. Existing demo/database resume remains available as fallback.
9. Filesystem resumes sort before demo resumes when present.
10. Creating a run with a discovered `.docx` resume copies it to `input/master_resume.docx`.
11. Creating a run with an existing database markdown resume still writes `input/master_resume.md`.
12. API response includes discovered master resumes.

Add or update frontend tests if the project has them to prove:

1. Master resume selector/list shows discovered `.docx` files.
2. DOCX badge appears.
3. Demo resume is not the only visible item when real files exist.
4. Selecting a discovered DOCX resume sends its ID in the run creation payload.

If no frontend tests exist, document manual verification.

## Acceptance Criteria

- Files placed in `candidate_context/master_resumes/` appear in the frontend.
- `.docx` master resumes are supported.
- Existing seeded demo data does not hide real files.
- Newly added files appear after backend restart or API refresh.
- Creating a run from a discovered `.docx` stages `input/master_resume.docx`.
- Existing markdown/database resume flow still works.
- Backend tests pass.
- Frontend build passes.

## Verification

Run:

```bash
pytest backend/tests/test_master_resumes.py
pytest backend/tests/test_run_directory.py
pytest backend/tests/test_api.py
pytest
cd frontend && npm run build
```

Manual verification:

1. Add a file:

```text
candidate_context/master_resumes/test_resume.docx
```

2. Start backend.
3. Start frontend.
4. Open the page with the master resume selector/list.
5. Confirm `test_resume.docx` appears.
6. Confirm it is marked as DOCX.
7. Confirm `Demo Master Resume` is not the only option.
8. Select `test_resume.docx`.
9. Create a run.
10. Confirm the run directory contains:

```text
input/master_resume.docx
```

11. Confirm the worker can extract or use the DOCX during tailoring.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Discover master resumes from candidate context
```

Do not push.
