# Task 090: Support Multiple Evidence Sources for Tailoring Runs

## Goal

Change tailoring run creation so the user can select multiple evidence sources instead of a single evidence bank.

A run should support:

```text
one primary master resume
zero or more evidence banks
zero or more additional resume variants
zero or more project notes / candidate context files
```

This allows workflows like:

```text
Primary resume:
  ML software resume.docx

Evidence sources:
  quantum chemistry resume.docx
  RMG resume.docx
  ARC project notes.md
  publications.md
  evidence bank.md
```

Do not remove existing single evidence bank support until compatibility is preserved.  
Do not change Gmail behavior.  
Do not change LinkedIn behavior.  
Do not change Claude OAuth behavior.  
Do not remove demo seed data unless it is clearly only fallback data.

## Background

The current UI/model appears to treat evidence as a single selected item, such as one evidence bank.

This is too restrictive.

The user may have:

```text
candidate_context/master_resumes/
candidate_context/evidence_banks/
candidate_context/project_notes/
candidate_context/resume_variants/
```

or similar subfolders containing useful evidence.

The app should let the user select multiple items as evidence for a tailoring run.

Also, the seeded demo data may be hiding or replacing real files from `candidate_context/`. The implementation should verify whether the backend reads real files from candidate context subfolders or only returns database seed records.

## Inspect

Inspect:

```text
backend/app/models.py
backend/app/schemas.py
backend/app/run_directory.py
backend/app/routers/runs.py
backend/app/routers/master_resumes.py
backend/app/routers/evidence_banks.py
backend/tests/
frontend/src/pages/JobDetailPage.tsx
frontend/src/api/types.ts
frontend/src/api/index.ts
frontend/src/test/
scripts/seed_demo_data.py
docs/contracts/
candidate_context/
```

Search:

```bash
rg "EvidenceBank|evidence_bank|evidence_banks|candidate_context|master_resume|selectedResume" backend frontend scripts docs
```

Use the existing project architecture.

## Desired Data Model

A tailoring run should distinguish:

```text
primary_master_resume_id
evidence_source_ids[]
```

The existing field may be:

```text
master_resume_id
evidence_bank_id
```

Preserve backwards compatibility.

Suggested evolution:

```json
{
  "job_id": "...",
  "master_resume_id": "...",
  "evidence_bank_id": "legacy-single-id",
  "evidence_source_ids": [
    "evidence-bank-1",
    "resume-variant-1",
    "project-note-1"
  ]
}
```

If `evidence_source_ids` is omitted, preserve current behavior.

If `evidence_bank_id` is provided, include it as one evidence source.

## Evidence Source Types

Represent evidence sources with a common shape:

```json
{
  "id": "stable-id",
  "name": "ARC project notes.md",
  "source_type": "project_note",
  "source_format": "md",
  "source": "filesystem",
  "source_path": "candidate_context/project_notes/arc.md",
  "updated_at": "..."
}
```

Supported `source_type` values:

```text
evidence_bank
resume_variant
master_resume
project_note
candidate_note
other
```

Supported formats for this task:

```text
.md
.txt
.docx
```

PDF support may be a later task.

## Candidate Context Discovery

Add or extend filesystem discovery for candidate context evidence files.

The backend should discover useful files from subfolders such as:

```text
candidate_context/evidence_banks/
candidate_context/project_notes/
candidate_context/resume_variants/
candidate_context/master_resumes/
candidate_context/
```

Do not assume every folder exists.

Supported files:

```text
.md
.txt
.docx
```

Ignore:

```text
.DS_Store
.~lock*
~$*
__pycache__
unsupported binary files
```

If existing discovery only scans one folder, generalize it.

If the project already has separate database models for evidence banks and master resumes, combine them at the API layer rather than forcing a large migration.

## Backend API Requirements

Add or update an endpoint to list selectable evidence sources.

Suggested endpoint:

```text
GET /api/evidence-sources
```

or use existing route conventions.

Response:

```json
[
  {
    "id": "evidence-bank-1",
    "name": "Demo Evidence Bank",
    "source_type": "evidence_bank",
    "source_format": "md",
    "source": "database",
    "updated_at": "..."
  },
  {
    "id": "fs:resume-variant-ml",
    "name": "ML resume variant.docx",
    "source_type": "resume_variant",
    "source_format": "docx",
    "source": "filesystem",
    "source_path": "candidate_context/resume_variants/ml_resume.docx",
    "updated_at": "..."
  }
]
```

Avoid exposing absolute paths if existing API avoids them.

## Run Creation Requirements

Update run creation payload to accept:

```json
{
  "job_id": "...",
  "master_resume_id": "...",
  "evidence_source_ids": [
    "...",
    "..."
  ]
}
```

Backwards compatibility:

```json
{
  "job_id": "...",
  "master_resume_id": "...",
  "evidence_bank_id": "..."
}
```

should still work.

## Run Directory Requirements

When creating a run, stage selected evidence sources into:

```text
runs/<run_id>/input/evidence_sources/
```

Example:

```text
input/evidence_sources/001_demo_evidence_bank.md
input/evidence_sources/002_quantum_chemistry_resume.docx
input/evidence_sources/003_arc_project_notes.md
```

Also create an index file:

```text
input/evidence_sources_index.md
```

The index should include:

```text
# Evidence Sources

## 1. Demo Evidence Bank
- Type: evidence_bank
- Format: md
- Source: database or filesystem
- Staged path: input/evidence_sources/001_demo_evidence_bank.md

## 2. Quantum Chemistry Resume
- Type: resume_variant
- Format: docx
- Source: filesystem
- Staged path: input/evidence_sources/002_quantum_chemistry_resume.docx
```

If a selected `.docx` evidence source is used, also extract markdown if existing DOCX extraction utilities support it:

```text
input/evidence_sources/002_quantum_chemistry_resume_extracted.md
```

If extraction is too large for this task, at least stage the DOCX and mention in the prompt that Word MCP can read DOCX evidence sources.

## Prompt Requirements

Update `runtime_prompts/resume_tailoring.md` so Claude understands:

```text
The primary resume is the formatting/base resume.
Evidence sources are supporting factual sources.
Use evidence sources to strengthen claims only when supported.
Do not invent claims.
If multiple resume variants are provided as evidence, treat them as evidence only unless explicitly selected as the primary resume.
Read input/evidence_sources_index.md before tailoring.
Review all files under input/evidence_sources/.
```

The prompt should say:

```text
If evidence sources include DOCX files, use word-document-server / Word MCP tools if available, or extracted markdown siblings if present.
```

## Frontend Requirements

Update the job detail/run creation UI.

Current likely behavior:

```text
Select one master resume
Select one evidence bank
Generate draft
```

Desired behavior:

```text
Select primary master resume
Select evidence sources
  [ ] Evidence bank
  [ ] Resume variant
  [ ] Project note
  [ ] Additional master resume as evidence
Generate draft
```

The evidence source selector should support multi-select.

It should show badges:

```text
DOCX
MD
TXT
database
filesystem
resume variant
evidence bank
project note
```

If frontend complexity is high, implement a simple checkbox list first.

## Demo Seed Compatibility

Do not remove demo seed data.

But demo data should not hide real files.

If real evidence files exist in candidate context, show them alongside seeded demo evidence.

Sort order:

```text
filesystem evidence sources first
database/demo evidence sources second
then alphabetical by name
```

or another clear stable order.

## Tests

Add/update backend tests to prove:

1. Evidence source list includes database evidence banks.
2. Evidence source list includes `.md` files from candidate context subfolders.
3. Evidence source list includes `.txt` files from candidate context subfolders.
4. Evidence source list includes `.docx` files from candidate context subfolders.
5. Unsupported/temp files are ignored.
6. Evidence source IDs are stable.
7. Run creation accepts multiple `evidence_source_ids`.
8. Legacy single `evidence_bank_id` still works.
9. Run directory stages all selected evidence sources.
10. Run directory writes `input/evidence_sources_index.md`.
11. Selected DOCX evidence source is staged.
12. Existing single-evidence tests still pass.
13. Prompt references `input/evidence_sources_index.md`.
14. Prompt distinguishes primary resume from evidence sources.

Add/update frontend tests if the project has test infrastructure:

1. Evidence selector shows multiple sources.
2. Evidence selector supports multiple checked items.
3. DOCX evidence source badge renders.
4. Filesystem and database sources both appear.
5. Generate draft sends `evidence_source_ids`.
6. Legacy/default path still works if no evidence sources are selected.

## Acceptance Criteria

- User can select multiple evidence sources for a tailoring run.
- Additional resume variants can be selected as evidence.
- Candidate context subfolders are scanned for evidence files.
- Demo seed data no longer hides real candidate context evidence.
- Run directory stages all selected evidence sources.
- Claude prompt instructs how to use primary resume vs evidence sources.
- Backwards compatibility with existing evidence bank behavior is preserved.
- Tests pass.

## Verification

Run:

```bash
pytest
cd frontend && npm run build
```

If frontend tests exist:

```bash
cd frontend && npm test -- --run
```

Manual verification:

1. Add files:

```text
candidate_context/evidence_banks/rmg_arc.md
candidate_context/project_notes/arc_notes.md
candidate_context/resume_variants/qchem_resume.docx
```

2. Start backend.
3. Start frontend.
4. Open a job.
5. Confirm evidence selector shows all three files plus demo evidence if seeded.
6. Select multiple evidence sources.
7. Generate a draft.
8. Confirm run directory contains:

```text
input/evidence_sources/
input/evidence_sources_index.md
```

9. Confirm all selected files were staged.
10. Confirm Claude tailoring prompt references the evidence source index.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Support multiple evidence sources
```

Do not push.
