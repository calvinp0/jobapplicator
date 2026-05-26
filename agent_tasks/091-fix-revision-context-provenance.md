# Task 091: Fix Revision Context Provenance

## Goal

Fix the resume draft revision flow so revision requests have access to the original tailoring context.

A revision should include:

```text
- the master resume used for the original draft
- the evidence sources used for the original draft
- the generated tailored draft being revised
- the user's revision instructions
- optional additional evidence selected/provided during revision
```

Current observed UI failure:

```text
master resume not found for source resume version
```

This indicates the revision flow cannot reliably reconstruct the master resume or source context from the selected draft/resume version.

Do not change Gmail behavior.  
Do not change LinkedIn behavior.  
Do not change Gmail OAuth behavior.  
Do not remove existing draft approval behavior.  
Do not remove existing tailoring output validation.

## Background

The revision UI currently allows the user to request changes against a generated draft.

Example revision instruction:

```text
habstraction.homecalvin.com is a side project...
...
```

But submitting the revision failed with:

```text
master resume not found for source resume version
```

The intended revision workflow is:

```text
Source master resume
  +
Original evidence sources
  +
Current tailored draft
  +
Revision request
  +
Optional additional evidence
  ↓
LLM revision run
  ↓
New resume version / draft
```

The revision should not be a blind rewrite.

## Inspect

Inspect:

```text
backend/app/models.py
backend/app/schemas.py
backend/app/run_directory.py
backend/app/run_import.py
backend/app/routers/resume_versions.py
backend/app/routers/revision_feedback.py
backend/tests/test_revision_feedback_model.py
backend/tests/test_revision_feedback_api.py
backend/tests/test_run_import.py
frontend/src/pages/
frontend/src/api/
frontend/src/test/
runtime_prompts/resume_tailoring.md
docs/contracts/
```

Search:

```bash
rg "revision|Revision|resume_version|source_version|master_resume|evidence_source|evidence_bank|tailored_resume" backend frontend docs
```

Use the existing project architecture.

## Required Behavior

Revision requests must be able to resolve the full provenance of the draft being revised.

For a `ResumeVersion` or draft, persist or derive:

```text
job_id
master_resume_id
source_run_id
source_resume_version_id
evidence_bank_id, if legacy
evidence_source_ids, if multiple evidence sources exist
tailored_resume_path or content
change_log_path or content
claim_audit_path or content
created_at
```

If the current model already has some of these, preserve and use them.

If missing fields caused the failure, add migrations or compatibility logic.

## Provenance Rules

When a run produces/imports a resume version, the imported `ResumeVersion` must store enough context to support revisions later.

At minimum:

```text
master_resume_id
job_id
source_run_id
```

If Task 090 multiple evidence sources exists, also store:

```text
evidence_source_ids
```

or a normalized relationship table.

If the original run used legacy `evidence_bank_id`, preserve it and translate it into revision context.

## Revision Run Directory Requirements

When a revision is requested, create a new run directory or revision directory that stages:

```text
input/master_resume.md
input/master_resume.docx, if available
input/master_resume_extracted.md, if available
input/current_tailored_resume.md
input/current_tailored_resume.docx, if available
input/revision_request.md
input/evidence_sources/
input/evidence_sources_index.md
```

If the source master resume was filesystem-backed `.docx`, stage:

```text
input/master_resume.docx
```

If markdown exists, also stage:

```text
input/master_resume.md
```

If the source tailored draft has a DOCX file, stage it as:

```text
input/current_tailored_resume.docx
```

If a markdown draft exists, stage it as:

```text
input/current_tailored_resume.md
```

## Revision Prompt Requirements

Create or update a dedicated revision prompt.

Suggested file:

```text
runtime_prompts/resume_revision.md
```

or reuse the existing prompt with a clear revision mode.

The prompt should say:

```text
You are revising an existing tailored resume draft.

Use the master resume as the truth source.
Use the original evidence sources as supporting factual evidence.
Use the current tailored resume as the document to revise.
Apply the user's revision request.
Do not invent claims.
Do not remove truthful relevant content unless the user asks or the revision requires it.
If the user provides new facts in the revision request, treat them as user-provided evidence but flag them in the claim audit.
If optional additional evidence files are provided, use them as supporting evidence.
```

Required revision outputs:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

The output should create a new version/draft, not overwrite the approved/source version.

## Additional Evidence During Revision

The revision UI/backend should support optional extra evidence.

At minimum, the API should allow:

```json
{
  "revision_text": "...",
  "additional_evidence_source_ids": []
}
```

If Task 090 is not complete yet, this field can be accepted but optional/no-op.

If additional evidence is selected, stage it under:

```text
input/evidence_sources/
```

and include it in:

```text
input/evidence_sources_index.md
```

The prompt should clearly distinguish:

```text
Original evidence sources
Additional revision evidence
User-provided revision text
```

## Backend API Requirements

Update the revision endpoint so it:

```text
1. validates the source resume version exists
2. resolves its master resume
3. resolves its job
4. resolves original run/evidence context where available
5. creates a revision run directory
6. writes revision_request.md
7. stages source draft and evidence
8. launches Claude revision worker or existing worker in revision mode
9. imports the result as a new resume version/draft
```

If the current implementation already does some of this, fix the missing provenance resolution.

The user-facing error should be specific and actionable.

Instead of:

```text
master resume not found for source resume version
```

return something like:

```json
{
  "detail": {
    "error": "revision_missing_master_resume",
    "message": "This draft cannot be revised because its source master resume record is missing. Regenerate the draft or relink a master resume.",
    "source_resume_version_id": "..."
  }
}
```

But the main goal is to avoid this error for normal generated drafts.

## Frontend Requirements

Update the revision UI so it can show the context being used.

Display:

```text
Base master resume: <name>
Original evidence sources: <count/list>
Current draft: Draft N
```

Add optional evidence selector if Task 090 multiple evidence sources exists:

```text
Additional evidence for this revision
[ ] evidence item 1
[ ] evidence item 2
```

If additional evidence selector is too large, defer UI but keep backend/API support.

When revision fails, show useful error text rather than a raw message.

## Compatibility Requirements

Existing drafts created before provenance fields existed may lack some context.

For old versions:

```text
- try to resolve context from source_run_id/run metadata
- try to resolve from job_id/master_resume_id if present
- if impossible, return a clear non-500 error
```

Do not crash.

## Tests

Add/update backend tests to prove:

1. ResumeVersion created from a run stores `master_resume_id`.
2. ResumeVersion created from a run stores `source_run_id` or equivalent.
3. Revision endpoint resolves the original master resume.
4. Revision endpoint stages `input/master_resume.md` when markdown master exists.
5. Revision endpoint stages `input/master_resume.docx` when source master is DOCX-backed.
6. Revision endpoint stages current tailored resume markdown.
7. Revision endpoint stages current tailored resume DOCX if available.
8. Revision endpoint writes `input/revision_request.md`.
9. Revision endpoint stages original evidence sources if available.
10. Revision endpoint accepts `additional_evidence_source_ids`.
11. Revision prompt includes master resume, current tailored draft, evidence, and revision request.
12. Revision creates a new draft/version instead of overwriting the source.
13. Missing master resume returns structured non-500 error.
14. Old versions without provenance return clear error or use fallback resolution.
15. Existing revision feedback tests still pass.

Add/update frontend tests if test infrastructure exists:

1. Revision page shows base master resume name.
2. Revision page shows original evidence source count/list.
3. Revision request sends revision text.
4. Revision request sends additional evidence IDs if selected.
5. Missing provenance error is shown clearly.

## Acceptance Criteria

- Normal generated drafts can be revised without `master resume not found`.
- Revision flow stages the original master resume.
- Revision flow stages the current tailored draft.
- Revision flow stages original evidence sources where available.
- Revision flow supports optional additional evidence.
- Revision prompt clearly distinguishes master resume, tailored draft, revision request, and evidence.
- Revision creates a new version/draft.
- Missing provenance returns a structured, non-500, actionable error.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_revision_feedback_model.py
pytest backend/tests/test_revision_feedback_api.py
pytest backend/tests/test_run_import.py
pytest backend/tests/test_run_directory.py
pytest
cd frontend && npm run build
```

If frontend tests exist:

```bash
cd frontend && npm test -- --run
```

Manual verification:

1. Generate a draft from a master resume and evidence sources.
2. Open the draft detail page.
3. Confirm it shows:
   - base master resume
   - evidence source count/list
4. Enter a revision request.
5. Submit revision.
6. Confirm no error appears:

```text
master resume not found for source resume version
```

7. Confirm a new revision run/version is created.
8. Confirm the revision run directory contains:

```text
input/master_resume.md or input/master_resume.docx
input/current_tailored_resume.md or input/current_tailored_resume.docx
input/revision_request.md
input/evidence_sources/
input/evidence_sources_index.md
```

9. Confirm revised outputs exist:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

10. Confirm the source draft is not overwritten.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix revision context provenance
```

Do not push.

