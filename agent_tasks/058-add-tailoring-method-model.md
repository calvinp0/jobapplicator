# Task 058: Add Tailoring Method Model and Run State Support

## Goal

Add backend support for multiple resume tailoring methods without changing the frontend UI yet.

The system should support:

```text
auto
word_handoff
```

Where:

```text
auto = existing Claude Code backend generation path
word_handoff = prepares files for Claude for Word manual/semi-automated editing
```

Do not implement the Word handoff package yet.
Do not change frontend UI.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

Inspect:

```text
backend/app/run_directory.py
backend/app/claude_worker.py
backend/app/main.py
backend/tests/test_run_directory.py
backend/tests/test_claude_worker.py
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
agent_tasks/queue.yaml
```

The current system assumes a single tailoring flow. We now need explicit run metadata so future tasks can create either:

```text
1. fully automated Claude Code runs
2. Claude for Word handoff runs
```

## Required Behavior

Each run should persist a tailoring method field.

Allowed methods:

```text
auto
word_handoff
```

Default method:

```text
auto
```

The run metadata should also support these statuses:

```text
created
input_ready
auto_tailoring_running
auto_tailoring_failed
auto_tailoring_complete
word_handoff_ready
waiting_for_word_result
word_result_imported
validation_failed
completed
failed
```

Do not remove existing statuses if other tests rely on them. Add compatibility where needed.

## Run Directory Contract

Update the run directory contract documentation to describe:

```text
runs/<run_id>/
  input/
  output/
  logs/
  word_handoff/
  metadata.json
```

The `metadata.json` should be able to contain:

```json
{
  "run_id": "<run_id>",
  "tailoring_method": "auto",
  "status": "created",
  "created_at": "...",
  "updated_at": "..."
}
```

If the current metadata shape differs, preserve backwards compatibility.

## Backend Requirements

Add helper functions where appropriate:

```text
get_tailoring_method(run_dir)
set_tailoring_method(run_dir, method)
set_run_status(run_dir, status)
get_run_status(run_dir)
```

Exact function names may follow the existing code style.

Invalid tailoring method should raise a clear error.

Invalid status should raise a clear error unless the current code intentionally allows arbitrary status strings.

## Tests

Update tests to prove:

1. New runs default to `auto`.
2. A run can be marked as `word_handoff`.
3. Invalid tailoring methods are rejected.
4. New statuses can be persisted and read back.
5. Existing run directory tests still pass.
6. Backwards compatibility is preserved for older metadata that has no tailoring method.

Do not require the real Claude binary in tests.

## Acceptance Criteria

- Run metadata supports `tailoring_method`.
- Default method is `auto`.
- `word_handoff` is accepted.
- Invalid methods are rejected.
- New statuses are documented.
- Run directory contract documents `word_handoff/`.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_run_directory.py
pytest backend/tests/test_claude_worker.py
pytest
```

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add tailoring method run metadata
```

Do not push.
