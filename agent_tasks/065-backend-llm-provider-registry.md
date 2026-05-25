# Task 065: Backend LLM Provider Registry and Per-Run Persistence

## Goal

Refactor the backend `auto` tailoring path so the LLM CLI it invokes is
selected from a provider registry rather than hardcoded to Claude Code.
Add a per-run `llm_provider` field that records which provider executed
the run.

This task only adds the abstraction, the registry, and the persistence.
The user-facing default lives in app settings (task 066), and the UI is
added in task 067.

## Background

Read first:

- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/adr/009-llm-provider-selection.md` (added by task 063)
- `docs/contracts/claude_run_directory.md` (updated by task 064)
- `backend/app/claude_worker.py`
- `backend/app/run_directory.py`
- `backend/app/models.py` (the `ClaudeRun` model)
- `backend/app/schemas.py`
- `backend/app/routers/runs.py`
- `backend/tests/test_claude_worker.py`
- `backend/tests/test_run_directory.py`

The current worker hardcodes `claude` as the binary via
`JOBAPPLY_CLAUDE_BINARY` and builds a fixed argv. The runtime prompt is
provider-agnostic and consumed via stdin.

## Scope

1. Introduce a provider registry module (e.g. `backend/app/llm_providers.py`).
   Each provider entry contains, at minimum:
   - a stable lowercase snake_case id (`claude_code`, `codex`, `gemini`)
   - a human-readable display name
   - the default CLI binary name
   - an env var that overrides the binary
   - a function that builds the non-interactive argv given the binary
     and the permission mode (Claude Code keeps the current
     `--print --permission-mode <mode>` form; Codex and Gemini use
     their equivalents — pick the documented non-interactive switch for
     each tool, e.g. `codex exec` / `gemini --prompt-stdin`. Provider
     stubs whose exact CLI shape is uncertain should still produce a
     working dry-run path and a clearly named env var for overriding
     the argv).
   - a description of how the prompt is delivered (stdin in all cases
     for the initial three providers).

2. Add `llm_provider` to the `ClaudeRun` model as a non-nullable string
   column with a default of `claude_code`. Add a SQLAlchemy default and a
   migration-safe approach for existing rows (the project uses
   SQLite-without-alembic patterns elsewhere — match what tasks 044/058
   did when they added columns).

3. Update `run_directory.create_run_directory` (or the equivalent helper
   that writes `metadata.json`) so the metadata includes
   `llm_provider`. Default value: `claude_code`. For
   `tailoring_method == word_handoff` the value is `claude_for_word`.

4. Update `invoke_claude_run` in `backend/app/claude_worker.py` so:
   - It reads the run's `llm_provider` field.
   - It looks the provider up in the registry and builds argv from the
     provider entry.
   - The "claude binary not found" / "failed to launch" failure paths
     stay structurally identical but quote the provider's id and
     binary, not the literal string "claude".
   - The dry-run path is unchanged — providers are not consulted in
     dry-run mode.

5. Update `backend/app/schemas.py` so the run-creation request accepts
   an optional `llm_provider` and the run-response includes the field.
   If the request omits it, the route falls back to the global default
   (the route helper for that default may stub to `"claude_code"` for
   now; task 066 wires it to the real setting).

6. Update `backend/app/routers/runs.py` so the create-run endpoint:
   - Accepts the optional `llm_provider` field.
   - Validates it against the provider registry. Unknown values return
     a 400 with a clear message.
   - Stores it on the `ClaudeRun` row.

7. Add a read-only listing endpoint
   `GET /api/llm-providers` that returns the registered providers
   (id, display name, default binary, env var name) so the frontend can
   render a selector. The endpoint is anonymous (matches the existing
   local-first pattern) and lives in a new router or in `main.py` —
   match the project's conventions.

8. Tests:
   - The provider registry returns the three initial entries with
     non-empty ids and binaries.
   - A run created without `llm_provider` defaults to `claude_code`.
   - A run created with `llm_provider="codex"` persists that value and
     `metadata.json` records it.
   - An unknown `llm_provider` returns 400.
   - `invoke_claude_run` (in dry-run mode) records the run's provider
     id in its failure/success messages — extend an existing test by
     creating a run with `llm_provider="codex"` and checking the
     persisted column rather than mocking the subprocess.
   - `GET /api/llm-providers` returns the three providers.
   - Existing tests still pass.

## Allowed files

- `backend/app/llm_providers.py` (new)
- `backend/app/claude_worker.py`
- `backend/app/run_directory.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/db.py` (only if a column-add migration helper is needed)
- `backend/app/main.py`
- `backend/app/routers/**`
- `backend/tests/**`
- `agent_tasks/065-backend-llm-provider-registry.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `frontend/**`
- `extension/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `runs/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/contracts/claude_run_directory.md` (it was updated in task 064)

## Out of scope

- Storing or surfacing a global default provider (task 066).
- Frontend changes (tasks 067 / 068).
- Adding provider-specific runtime prompts.
- Hosted-API providers.
- Provider failover / cascade logic.

## Acceptance criteria

- `backend/app/llm_providers.py` exposes a registry containing
  `claude_code`, `codex`, and `gemini`.
- `ClaudeRun.llm_provider` is persisted and defaults to `claude_code`.
- `runs/<run_id>/metadata.json` contains `llm_provider`.
- `invoke_claude_run` dispatches to the selected provider's argv builder.
- `POST /api/runs` (or equivalent) accepts and validates `llm_provider`.
- `GET /api/llm-providers` returns the registered providers.
- All `pytest` tests pass.

## Verification

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_run_directory.py
pytest
```

## Git instructions

After verification passes:

1. Stage the changed backend files, the new provider module, the new
   tests, and this task file.
2. Commit locally with the message:

```text
Add LLM provider registry and per-run provider persistence
```

Do not push.
