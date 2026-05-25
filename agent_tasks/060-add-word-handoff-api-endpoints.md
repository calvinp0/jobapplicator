# Task 060: Add Word Handoff API Endpoints

## Goal

Expose backend API endpoints for the Claude for Word handoff flow.

This task should make the backend usable by the frontend, but should not implement frontend UI yet.

Do not change the existing Auto / Claude Code generation behavior.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

Inspect:

```text
backend/app/main.py
backend/app/run_directory.py
backend/app/word_handoff.py
backend/tests/
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
```

This task depends on Task 059.

## Required Endpoints

Add endpoints following the existing project route style.

Suggested endpoints:

```text
POST /api/runs/{run_id}/word-handoff
GET  /api/runs/{run_id}/word-handoff
GET  /api/runs/{run_id}/word-handoff/prompt
GET  /api/runs/{run_id}/word-handoff/instructions
```

Use the actual route conventions already present in the backend.

## Endpoint Behavior

### POST word handoff

Creates or refreshes the Word handoff package.

Returns JSON including:

```json
{
  "run_id": "<run_id>",
  "status": "word_handoff_ready",
  "tailoring_method": "word_handoff",
  "handoff_dir": "runs/<run_id>/word_handoff",
  "resume_docx": "runs/<run_id>/word_handoff/01_resume_for_claude_word.docx",
  "prompt_file": "runs/<run_id>/word_handoff/02_prompt_for_claude_word.txt",
  "instructions_file": "runs/<run_id>/word_handoff/04_instructions.md",
  "expected_output": "runs/<run_id>/output/word_tailored_resume.docx"
}
```

If no DOCX exists, `resume_docx` may be null, but prompt/instructions should still be returned if created.

### GET word handoff

Returns the current handoff status and file paths.

### GET prompt

Returns the prompt text.

### GET instructions

Returns the instructions markdown.

## Error Handling

If the run does not exist:

```text
404
```

If required input is missing so no useful handoff can be created:

```text
400
```

Do not expose absolute paths if the existing API avoids them. Match current conventions.

Do not print secrets.

## Tests

Add/update backend API tests proving:

1. POST creates the handoff package.
2. POST returns `word_handoff_ready`.
3. GET returns handoff metadata.
4. GET prompt returns prompt text.
5. GET instructions returns instructions markdown.
6. Missing run returns 404.
7. Missing usable input returns a clear 400 or existing project-standard error.
8. Existing auto endpoints still work.

Do not require Microsoft Word.
Do not require Claude for Word.
Do not require real Claude Code.

## Acceptance Criteria

- Backend exposes Word handoff creation endpoint.
- Backend exposes prompt/instructions retrieval.
- API returns paths/status needed by frontend.
- Auto mode behavior is unchanged.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_word_handoff.py
pytest backend/tests/test_api.py
pytest
```

If `test_api.py` does not exist, use the existing backend API test file.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Word handoff API endpoints
```

Do not push.
