# Task 049: Enforce Tailoring Output Contract

## Goal

Fix the backend run lifecycle so a tailoring run is not marked successfully completed unless it produced the required output files.

Currently a run can reach `completed`, but `/runs/{id}/import` fails with:

```text
expected output file missing: output/tailored_resume.docx
```

This creates a confusing state: the frontend sees the run as completed, but no reviewable draft exists.

Do not change frontend behavior in this task except tests if strictly necessary.

## Scope

Inspect and update:

```text
backend/app/claude_worker.py
backend/app/run_import.py
backend/app/run_directory.py
backend/app/routers/runs.py
backend/tests/test_claude_worker.py
backend/tests/test_run_import.py
docs/contracts/claude_run_directory.md
```

Do not edit frontend unless absolutely required.

## Required Behavior

After Claude invocation exits with code `0`, the worker must validate that all required output files exist:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

If any required output file is missing:

```text
run.status = failed
run.completed_at = now
run.error_message = "expected output file missing: output/tailored_resume.docx"
```

Do not set status to `completed`.

If multiple required files are missing, `error_message` should clearly list all missing files.

If all required output files exist:

```text
run.status = completed
```

Import remains responsible for creating the `ResumeVersion` and setting:

```text
run.status = imported
```

## Dry-Run Behavior

Make dry-run behavior explicit.

Choose one of these approaches:

1. Dry-run writes valid placeholder outputs so it can be imported.
2. Dry-run does not write outputs and is documented as not importable.

Prefer option 1 if it is simple, because it improves local smoke testing.

If option 1 is chosen, dry-run should create:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

The DOCX must be valid enough for the existing import/open-file flow.

## Acceptance Criteria

- A zero-exit Claude process with missing required outputs results in `failed`, not `completed`.
- `error_message` clearly lists missing output files.
- `/runs/{id}/import` is not the first place the user discovers missing outputs.
- Existing successful run import tests still pass.
- Dry-run behavior is explicit and covered by tests.
- Backend tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py backend/tests/test_run_import.py
pytest
```

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Enforce tailoring output contract
```

Do not push.
