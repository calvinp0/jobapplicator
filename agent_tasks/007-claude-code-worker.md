# Task 007: Claude Code Worker Invocation

## Goal

Add a backend service that invokes Claude Code as a local subprocess
against a prepared run directory, streams its output to a run log, and
updates the `ClaudeRun` row's status and timestamps as the process
progresses.

Claude Code is a worker. It must not mutate the database. This task wires
the subprocess and lifecycle only — output validation, hashing, and
ResumeVersion creation are task 008.

## Background

Read:

- `docs/architecture.md` (Claude Code worker boundary)
- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/003-human-in-the-loop-submission.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/006-run-directory-writer.md`
- `backend/app/models.py` (existing `ClaudeRun` model)

## Scope

Add to `backend/app/`:

- a `claude_worker.py` module exposing:
  - `invoke_claude_run(run_id)` which loads the `ClaudeRun`, resolves its
    `run_dir`, and launches Claude Code with the working directory set to
    that run directory, the prompt taken from `input/tailoring_prompt.md`,
    and a read/write scope limited to the run directory
  - streams stdout/stderr to `runs/<run_id>/run.log`
  - sets `status="running"` and `started_at` before launch, then
    `status="completed"` or `status="failed"` with `completed_at` and
    `error_message` on exit
  - never imports outputs into the DB — only records process lifecycle
- a `POST /runs/{run_id}/invoke` route that triggers `invoke_claude_run`
  synchronously and returns the updated `ClaudeRun` row
- a configuration surface (env vars) for the Claude binary path and
  optional dry-run mode used by tests
- pytest tests using a fake Claude binary (a small bash/python script
  fixture that writes plausible output files into `output/`) that verify:
  - status transitions and timestamps
  - `run.log` is written
  - non-zero exit produces `status="failed"` and an `error_message`
  - the subprocess working directory is the run directory, not the repo

## Allowed files

- `backend/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed)

## Forbidden files

- `extension/**`
- `frontend/**`
- `runs/**` at commit time (runtime output only)
- `runtime_prompts/**` (read only)
- `candidate_context/**`
- `docs/contracts/claude_run_directory.md`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- Other `agent_tasks/*.md`

## Out of scope

- Validating Claude's outputs, computing output hashes, or creating
  ResumeVersion rows (task 008).
- Async/background execution, job queues, or websockets.
- Retries, partial-run resumption, or speculative execution.
- Any frontend or extension work.
- Changing the run directory contract.

## Acceptance criteria

- Real Claude Code is never required to run the test suite — tests use a
  fake binary specified via env var.
- A successful run leaves `status="completed"`, `started_at` and
  `completed_at` populated, and `run.log` non-empty.
- A failing run leaves `status="failed"` with a useful `error_message`.
- Database writes happen in the backend, never in the subprocess.
- `pytest` passes.

## Verification

```bash
pytest
```

## Git commit message

```text
Add Claude Code worker invocation
```

Do not push.
