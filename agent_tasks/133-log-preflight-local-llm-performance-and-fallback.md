# Task 133: Log local LLM performance and surface "attempted but fell back" in the preflight manifest

## Goal

Make every preflight run carry an auditable record of *how* the local LLM
behaved, and make it obvious when the local provider was tried but the run fell
back. Today the manifest records `fallback_used` and a single `fallback_reason`,
but it does not record the prompt token estimate, how long each local call took,
the timeout that bounded it, or — clearly — that the local LLM was *attempted*
and then degraded/skipped. When a local model is slow or wedged (task 132), the
operator currently cannot see why a run quietly used the deterministic
extractor. This task logs the prompt token estimate, elapsed time, effective
timeout, and fallback reason per task, and surfaces a clear "local LLM attempted
but fell back" signal in the manifest and the human-readable preflight summary.
It builds on the degraded/skip state exposed by task 132.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — preflight artifacts are advisory;
  the manifest is the auditable record of what the run budgeted and used.
- `docs/llm_providers.md` — "Preflight analysis pipeline (task 124)" and the
  existing manifest examples.
- `docs/contracts/claude_run_directory.md` — the
  `preflight/preflight_manifest.json` section, the per-task entry shape, and the
  per-task `context` object (extended by tasks 125 and 127).
- `agent_tasks/127-detect-and-log-local-server-context.md` — added context
  fields to the manifest; follow the same additive, backward-compatible style.
- `agent_tasks/132-add-preflight-provider-degradation-guardrails.md` — the
  immediately preceding task; this task reads the degraded/skip state and
  per-task `fallback_reason` it exposes.
- `backend/app/preflight.py` — `PreflightTaskResult.manifest_entry` (around
  lines 157–171), `run_preflight` manifest assembly (around lines 325–345),
  `render_preflight_summary` (around lines 1046–1072), `_prepare_local_messages`
  (the per-task `context` dict with `estimated_input_tokens_*` around lines
  484–525), and `_run_one`.
- `backend/app/local_llm.py` — `LLMCallResult.latency_ms`, `error`, and the
  context estimate fields (read-only here).

## Scope

- Record per-task local LLM performance in the manifest (additive fields on each
  task entry; do not remove or rename existing fields):
  - **Prompt token estimate** — reuse the estimate already computed in
    `_prepare_local_messages` (`estimated_input_tokens_final`) rather than
    recomputing; expose it on the task entry (e.g. inside the existing `context`
    object or a new top-level key on the entry).
  - **Elapsed time** — the local call's `latency_ms` from `LLMCallResult`, when a
    local call was actually attempted.
  - **Effective timeout** — the per-call timeout that bounded the attempt (the
    value resolved in task 130).
  - **Fallback reason** — already present on fallback entries; ensure timeout and
    "skipped after repeated timeouts" reasons (from task 132) flow through.
- Surface the degraded / "attempted but fell back" state:
  - Add a top-level manifest flag that the local provider was **attempted** for
    this run (distinct from `fallback_used`), plus a clear indication when the
    provider was **degraded** or **skipped** after timeouts (read from the
    task-131 state). Choose explicit, documented key names.
  - In `render_preflight_summary`, when the local provider was attempted but the
    run fell back, print a clear line such as
    **"Local LLM attempted but fell back: <reason>"** (and note degraded/skipped
    when applicable), so the run trace makes the situation obvious at a glance.
  - Emit the same "Local LLM attempted but fell back: <reason>" wording through
    the preflight `progress`/`log` callbacks so it lands in the run's
    user-facing trace (run.log / progress stream). Use a single, stable,
    documented phrasing the frontend task (134) can key on; do not change the
    callback signatures.
- Keep the manifest valid and backward compatible: `validate_manifest` must still
  pass, existing keys keep their meaning, and a deterministic-only run (local
  never attempted) must not gain misleading "attempted" fields.
- Update `docs/contracts/claude_run_directory.md` to document the new manifest
  fields (per-task performance fields and the attempted/degraded/skipped
  signals), and update `docs/llm_providers.md` (Preflight section) to describe
  the new summary line and what the performance fields mean.

## Allowed files

- `backend/app/preflight.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/133-log-preflight-local-llm-performance-and-fallback.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/local_llm.py` (read-only for this task; its fields already exist)
- `backend/app/routers/**`, `backend/app/schemas.py`
- `frontend/**` (run-trace UI is task 134)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Computing new token estimates or changing the budgeting math (reuse the
  existing estimate from `_prepare_local_messages`).
- Changing the degraded/skip *behavior* (task 132); this task only reports it.
- Any frontend display of these fields (task 134).
- Changing `LocalLLMConfig`, settings endpoints, or request plumbing
  (tasks 130/131).

## Acceptance criteria

- Each preflight task manifest entry records the prompt token estimate, and —
  when a local call was attempted — its elapsed time and the effective timeout;
  tests assert these appear for a local-attempted task and are absent/neutral for
  a deterministic-only task.
- The manifest distinguishes "local attempted" from "fallback used", and records
  a degraded/skipped indicator when the provider degraded or was skipped after
  timeouts; a test covers the timeout-degraded path.
- `render_preflight_summary` prints a clear "Local LLM attempted but fell back:
  <reason>" line when the local provider was attempted and the run fell back; a
  test asserts the line is present in that case and absent on a clean local
  success and on a deterministic-only run.
- The same wording is emitted through the preflight `progress`/`log` callbacks so
  it reaches the run trace; a test asserts the marker line is emitted on the
  attempted-but-fell-back path and not on a clean local success.
- `validate_manifest` still passes for the new manifest shape; existing fields
  are unchanged.
- `docs/contracts/claude_run_directory.md` and `docs/llm_providers.md` document
  the new fields and the summary line.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_preflight.py
python -m pytest
```

## Git instructions

Commit message:

```
Log local LLM performance and surface attempted-but-fell-back in preflight
```

Do not push.
