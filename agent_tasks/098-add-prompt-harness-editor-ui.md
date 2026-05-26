# Task 098: Add Prompt Harness Viewer and Local Override Editor

## Goal

Add a web UI for viewing and optionally editing the prompt/harness setup used by the resume tailor.

The user wants to inspect and manually adjust the prompt instructions for:

```text
resume tailoring
resume revision
ATS optimization
DOCX / Word MCP behavior
claim audit behavior
evidence handling
```

The UI should allow reading the default prompt files and saving local overrides.

Do not require users to edit files manually in the terminal.  
Do not overwrite repo prompt files by default.  
Do not change Gmail behavior.  
Do not change LinkedIn behavior.  
Do not change browser extension behavior.

## Background

Runtime prompts currently live in files such as:

```text
runtime_prompts/resume_tailoring.md
runtime_prompts/resume_revision.md
```

The backend worker uses these prompts to instruct Claude Code.

The user wants access from the web page to:

```text
read the current harness/prompt
edit it manually if needed
restore default
see which prompt version was used for a run
```

This is especially important as the tailoring harness now includes:

```text
non-interactive backend job constraints
DOCX / Word MCP instructions
multiple evidence source instructions
revision instructions
ATS optimization
claim audit requirements
```

## Inspect

Inspect:

```text
runtime_prompts/
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/settings*
backend/app/routers/
backend/app/schemas.py
backend/tests/
frontend/src/pages/
frontend/src/components/
frontend/src/api/
frontend/src/test/
docs/contracts/
README_INSTALL.md
```

Search:

```bash
rg "runtime_prompts|resume_tailoring|resume_revision|prompt|harness|tailoring_prompt" backend frontend runtime_prompts docs
```

Use the existing project architecture.

## Prompt Model

Support these prompt/harness templates at minimum:

```text
resume_tailoring
resume_revision
```

If additional runtime prompts exist, include them.

Each prompt should expose:

```json
{
  "id": "resume_tailoring",
  "label": "Resume Tailoring",
  "description": "Prompt used to create tailored resumes from a job, master resume, and evidence sources.",
  "default_path": "runtime_prompts/resume_tailoring.md",
  "has_override": true,
  "effective_source": "override",
  "default_content": "...",
  "override_content": "...",
  "effective_content": "...",
  "updated_at": "..."
}
```

## Storage Requirements

Default prompts remain in:

```text
runtime_prompts/
```

Local overrides should be stored outside tracked repo prompt files.

Suggested location:

```text
candidate_context/settings/prompt_overrides/
  resume_tailoring.md
  resume_revision.md
```

If the project already has a settings storage location, use it.

Add override files to `.gitignore` if needed:

```text
candidate_context/settings/prompt_overrides/
```

Do not store prompt overrides in a database unless that is the existing settings pattern.

## Backend Requirements

Add a prompt service/module.

Suggested file:

```text
backend/app/prompt_harness.py
```

Responsibilities:

```text
list known prompts
read default prompt
read override prompt
return effective prompt
save override prompt
delete override prompt
restore default
compute prompt hash
```

Use safe path handling. Do not allow arbitrary file reads/writes.

Only allow editing known prompt IDs.

Reject unknown prompt IDs.

## Backend API Requirements

Add endpoints following current route style.

Suggested endpoints:

```text
GET    /api/prompts
GET    /api/prompts/{prompt_id}
PUT    /api/prompts/{prompt_id}/override
DELETE /api/prompts/{prompt_id}/override
POST   /api/prompts/{prompt_id}/validate
```

Use actual project conventions.

### GET /api/prompts

Returns prompt summaries:

```json
[
  {
    "id": "resume_tailoring",
    "label": "Resume Tailoring",
    "has_override": true,
    "effective_source": "override",
    "default_path": "runtime_prompts/resume_tailoring.md",
    "updated_at": "..."
  }
]
```

### GET /api/prompts/{prompt_id}

Returns default, override, and effective content.

### PUT /api/prompts/{prompt_id}/override

Request:

```json
{
  "content": "# Resume Tailoring Prompt\n..."
}
```

Behavior:

```text
- validate prompt ID
- validate content is non-empty
- save local override
- return updated prompt metadata
```

### DELETE /api/prompts/{prompt_id}/override

Deletes local override and restores default effective prompt.

### POST /api/prompts/{prompt_id}/validate

Validate obvious requirements.

For `resume_tailoring`, ensure effective content includes required concepts:

```text
non-interactive backend job
do not ask clarifying questions
write required output files
tailored_resume.md
tailored_resume.docx
change_log.md
claim_audit.md
ATS
evidence
```

If ATS audit is required, also validate:

```text
ats_audit.md
```

For `resume_revision`, validate:

```text
current tailored resume
revision request
master resume
evidence sources
do not invent claims
write required output files
```

Return warnings, not necessarily hard failures:

```json
{
  "valid": false,
  "warnings": [
    "Prompt does not mention claim_audit.md",
    "Prompt does not mention non-interactive backend job"
  ]
}
```

## Worker Integration

Update the backend worker so it uses the effective prompt:

```text
override if present
otherwise default runtime prompt
```

Do not duplicate prompt-loading logic.

When a run is created, store prompt provenance in run metadata:

```json
{
  "prompt_id": "resume_tailoring",
  "prompt_source": "override",
  "prompt_hash": "...",
  "prompt_snapshot_path": "input/prompt_snapshot.md"
}
```

The run directory should include:

```text
input/prompt_snapshot.md
```

This ensures old runs remain reproducible even if the prompt changes later.

For revision runs, use:

```text
prompt_id = resume_revision
```

## Frontend Requirements

Add prompt UI under Settings or Advanced.

Suggested navigation:

```text
Settings → Prompt harnesses
```

or:

```text
Advanced → Prompts
```

The UI should show:

```text
Prompt list
Selected prompt
Default/override/effective tabs
Editable override textarea/editor
Validation warnings
Save override
Restore default
Copy prompt
```

The UI should clearly show:

```text
Using default prompt
```

or:

```text
Using local override
```

Do not make the default prompt directly editable. To edit, user edits override content.

## Editing UX

Recommended behavior:

```text
- Show effective prompt read-only by default.
- Button: Create override from default.
- Once override exists, show editable override textarea.
- Button: Save override.
- Button: Restore default.
- Button: Validate.
```

Warn:

```text
Changing prompts can break run output validation if required files are omitted.
```

## Run Detail UI

If easy, show prompt provenance on run detail page:

```text
Prompt: Resume Tailoring
Source: default / override
Hash: abc123
Open prompt snapshot
```

If run detail artifact display already exists, add:

```text
Open prompt snapshot
```

## Security Requirements

Do not allow arbitrary path access.

Only known prompt IDs can be read/edited.

Do not expose secrets.

Prompt overrides are local settings.

## Documentation

Update:

```text
docs/contracts/agent_orchestration.md
docs/contracts/claude_run_directory.md
README_INSTALL.md
docs/install.md
```

Document:

```text
default runtime prompts
local prompt overrides
prompt validation
prompt snapshots per run
how to restore default
risk of breaking output contracts
```

## Tests

Add/update backend tests:

1. Prompt list returns known prompt IDs.
2. Prompt detail returns default content.
3. Saving override changes effective source to override.
4. Deleting override restores default.
5. Unknown prompt ID is rejected.
6. Empty override is rejected.
7. Validate tailoring prompt catches missing required output names.
8. Validate revision prompt catches missing revision concepts.
9. Worker uses override when present.
10. Worker uses default when no override exists.
11. Run directory writes `input/prompt_snapshot.md`.
12. Run metadata stores prompt ID/source/hash.
13. Prompt override path cannot escape settings directory.

Add/update frontend tests if test infrastructure exists:

1. Prompt page lists prompt harnesses.
2. Effective prompt is visible.
3. Create override from default works.
4. Save override calls API.
5. Restore default calls API.
6. Validation warnings render.
7. UI warns that prompt changes can break output validation.

## Acceptance Criteria

- User can view resume tailoring and revision prompts in the web UI.
- User can create/edit local prompt overrides.
- User can restore defaults.
- Worker uses effective prompt.
- Every run stores prompt snapshot and prompt hash.
- Prompt validation warns about missing required contract elements.
- Prompt override files are local and gitignored.
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

1. Start backend.
2. Start frontend.
3. Open Settings or Advanced prompt page.
4. Open Resume Tailoring prompt.
5. Confirm default prompt is visible.
6. Create override from default.
7. Edit a harmless line.
8. Save override.
9. Validate prompt.
10. Generate a tailoring run.
11. Confirm run metadata records:
    - prompt_id
    - prompt_source
    - prompt_hash
12. Confirm run input contains:

```text
input/prompt_snapshot.md
```

13. Restore default.
14. Confirm future runs use default again.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add prompt harness editor UI
```

Do not push.
