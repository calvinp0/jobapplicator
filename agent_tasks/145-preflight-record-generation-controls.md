# 145 — Surface generation controls and metrics in the preflight manifest

## Goal

Wire the new local LLM generation controls (tasks 140–144) into the preflight
pipeline so each local preflight task records, in the manifest, the
server-reported generation metrics, whether reasoning was returned, and (when a
timeout occurred) the timeout cause. This is the wiring that makes *cap output
before fallback*, *log Ollama eval counts*, and *thinking returned* observable on
a real run, completing the backend half of the goal.

## Background

Read first:

- `docs/llm_providers.md` — the **Preflight analysis pipeline (task 124)** and
  **Local LLM performance and attempted-but-fell-back (task 133)** sections (the
  manifest `performance` object and per-run `local_*` flags).
- `docs/contracts/claude_run_directory.md` — the `input/preflight/` manifest
  schema and per-task entry shape.
- `backend/app/preflight.py` — `TaskOutcome.manifest_entry`, the local-call
  block in the per-task runner (around the `client.chat_json(...)` call where
  `prompt_token_estimate` / `latency_ms` / `effective_timeout_seconds` are set),
  and `_is_timeout`.
- `backend/app/local_llm.py` — the `LLMCallResult` fields added by tasks 142
  (`thinking_returned`), 143 (`generation_metrics`/tokens-per-second), and 144
  (timeout `error_kind`); and the `max_output_tokens` config from task 140.
- `backend/tests/test_preflight.py` — existing manifest assertions.

## Scope

- In the preflight per-task local-call path, read the new `LLMCallResult` fields
  and record them on the `TaskOutcome` / `manifest_entry`:
  - Add the Ollama generation metrics (`prompt_eval_count`, `eval_count`,
    `total_duration_ms`, `eval_duration_ms`, `tokens_per_second`) to the existing
    per-task `performance` object when present. Keep `prompt_token_estimate`
    (the estimate) distinct from `prompt_eval_count` (the server-reported count).
  - Record `thinking_returned` on the task entry when a local call was attempted.
  - When a task fell back due to a timeout, record the timeout cause
    (`error_kind` from task 144) in the `fallback_reason` or a dedicated field,
    so a generation timeout reads differently from an unreachable server.
- Confirm the output cap (`max_output_tokens`, task 140) is actually in force on
  preflight calls — preflight constructs the client from the saved config, so it
  should be sent automatically; add a test asserting the configured cap reaches
  the request so "cap before fallback" is verified end to end. No new plumbing
  if the existing config path already carries it.
- Update `docs/llm_providers.md` (the manifest example) and
  `docs/contracts/claude_run_directory.md` (the per-task entry schema) to include
  the new fields. Keep the manifest shape additive and backward compatible —
  deterministic-only tasks must not gain misleading local fields.

## Allowed files

- `backend/app/preflight.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/145-preflight-record-generation-controls.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/local_llm.py` (the result fields/config come from tasks 140–144;
  do not change them here)
- `frontend/**` (UI is task 146)
- `backend/app/claude_worker.py`, `backend/app/routers/**`,
  `backend/app/schemas.py`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`

## Out of scope

- Any frontend display of the new manifest fields (task 146).
- Changing how `LLMCallResult`/config fields are computed (tasks 140–144 own
  that).
- Adding metrics to the non-preflight (`auto` tailoring) Claude flow.

## Acceptance criteria

- For an attempted local preflight task on Ollama, the manifest `performance`
  object includes the server-reported generation metrics and tokens/sec
  alongside the existing estimate/latency/timeout fields.
- Each attempted-local task entry records `thinking_returned`.
- A task that fell back on a timeout records the timeout cause distinctly from an
  unreachable-server fallback.
- A test asserts the configured `max_output_tokens` reaches the local request via
  the normal preflight config path (cap enforced before fallback).
- Deterministic-only tasks gain none of the new local fields.
- `docs/llm_providers.md` and `docs/contracts/claude_run_directory.md` document
  the additive manifest fields.
- `backend/tests/test_preflight.py` covers the new fields (attempted-local,
  fallback-on-timeout, and deterministic-only cases).

## Verification

- `python -m pytest backend/tests/test_preflight.py`
- `python -m pytest`

## Git instructions

Commit with the message:

```
Record local LLM generation metrics, thinking, and timeout cause in preflight manifest
```

Do not push.
