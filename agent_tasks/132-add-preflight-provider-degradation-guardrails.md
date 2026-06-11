# Task 132: Add preflight provider-degradation guardrails and a smaller default preflight context

## Goal

Stop a slow or unresponsive local LLM from making every preflight run pay a full
timeout on **each** task. Today the preflight pipeline tries the local provider
for every eligible task independently, so a local server that times out on the
first task will also be attempted (and time out again) on the next three — a
single cold or wedged server can add several multiples of the timeout to a run
before everything falls back. This task introduces a per-run "degraded" state:
after the first local-LLM timeout the provider is marked degraded for the rest of
that run, and after repeated timeouts the remaining local calls are skipped and
routed straight to the deterministic extractor. It also lowers the default
context JobApplicator budgets against for preflight (local preflight prompts are
short and reasoning models waste a large context), and reaffirms that the
preflight pipeline never adds a sequential-thinking / reasoning step. It builds
on tasks 130 (timeout) and 131 (reasoning controls).

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — preflight artifacts are advisory
  and never required; a local failure must never fail the run.
- `docs/llm_providers.md` — "Preflight analysis pipeline (task 124)" and
  Configuration sections.
- `docs/contracts/claude_run_directory.md` — the
  `preflight/preflight_manifest.json` section and the per-task `context` object.
- `agent_tasks/124-add-provider-routed-preflight-analysis-pipeline.md` and
  `agent_tasks/125-add-local-llm-context-budget-safeguards.md` — introduced
  `backend/app/preflight.py`, `run_preflight`, `_run_one`,
  `_prepare_local_messages`, and the per-task `context` dict and budgeting math.
- `agent_tasks/130-add-local-llm-task-timeout-and-ollama-default.md` and
  `agent_tasks/131-add-local-llm-reasoning-controls.md` — the immediately
  preceding tasks this builds on (effective timeout + reasoning controls).
- `backend/app/preflight.py` — `run_preflight` (the four sequential `_run_one`
  calls around lines 261–321), `_run_one` (around lines 376–470),
  `_prepare_local_messages` (around lines 473–535), and `PreflightTaskResult`.
- `backend/app/local_llm.py` — `LLMCallResult` (`error`, `latency_ms`),
  `LocalLLMClient.chat` (how a timeout is surfaced as `error="timeout after Ns"`
  around lines 667–685), and the `DEFAULT_CONTEXT_WINDOW_TOKENS` /
  `DEFAULT_MAX_INPUT_TOKENS` defaults (around lines 67–69).

## Scope

- Add a per-run degraded-state tracker to the preflight run (a small object or
  counters threaded through the `_run_one` calls — do **not** use module-level or
  process-global state). It must:
  - Detect a **timeout** outcome from a local call. A timeout is identifiable
    from the `LLMCallResult` (`call.ok is False` and its `error` indicates a
    timeout, e.g. starts with `"timeout after"`). Distinguish it from ordinary
    schema-validation failures, which do **not** count as a timeout.
  - Mark the provider **degraded** after the **first** local timeout in the run.
    A degraded provider is still allowed to attempt subsequent tasks unless the
    skip threshold below is reached, but the degraded state is recorded so it can
    be surfaced (the manifest/run-trace wiring is task 133).
  - **Skip** the local provider for all remaining tasks after **repeated**
    timeouts (define a small, documented threshold — e.g. 2 timeouts — as a named
    constant). Skipped tasks go straight to the deterministic extractor with a
    clear `fallback_reason` such as `"local provider skipped after repeated
    timeouts"`. Skipping must never raise; the deterministic path already
    guarantees a valid artifact.
  - The degraded/skip decision is **per run only** — a fresh `run_preflight` call
    starts clean.
- Lower the default context budget used for preflight:
  - Introduce a smaller preflight-specific default context (a named constant,
    smaller than `DEFAULT_CONTEXT_WINDOW_TOKENS`) that preflight budgets against
    when the user has **not** explicitly raised `context_window_tokens`. Never
    override an explicit user-configured context window — the smaller value is a
    default, not a cap. Document the rationale in a code comment.
  - Keep the existing over-budget handling (compression / fallback / abort)
    semantics intact; this only changes the default the budgeting starts from.
- Reaffirm the no-reasoning guardrail for preflight: the preflight prompts must
  continue to request only a single JSON object and must **not** introduce any
  sequential-thinking / chain-of-thought step or call the sequential-thinking
  tool. Add a test or assertion that the preflight messages do not instruct the
  model to "think step by step" / produce reasoning, and rely on task 131's
  reasoning controls to suppress model-side thinking.
- Surface the degraded/skip state on `PreflightTaskResult` and/or the aggregate
  `PreflightResult` (e.g. a `local_degraded` / `local_skipped` flag and per-task
  `fallback_reason`) so the manifest/run-trace task (133) can read it. Do **not**
  change the manifest JSON shape or summary rendering in this task — only expose
  the in-memory state and per-task `fallback_reason`.

## Allowed files

- `backend/app/preflight.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/132-add-preflight-provider-degradation-guardrails.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/local_llm.py` (config/client changes are tasks 130/131; this task
  only reads `LLMCallResult`)
- `backend/app/routers/**`, `backend/app/schemas.py`
- `frontend/**` (UI is task 134)
- `docs/contracts/**` (manifest contract changes are task 133)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Recording elapsed time, token estimate, timeout, or the degraded/fell-back
  state **into the manifest JSON or summary markdown** (task 133).
- Any frontend run-trace display (task 134).
- Changing `LocalLLMConfig`, the settings endpoints, or the timeout/reasoning
  request plumbing (tasks 130/131).
- Adding any reasoning/sequential-thinking step (explicitly forbidden here).

## Acceptance criteria

- A local timeout on an early preflight task marks the provider degraded for the
  rest of that run; a test asserts the degraded state is set and that a
  non-timeout schema failure does **not** set it.
- After the repeated-timeout threshold is reached, the remaining preflight tasks
  skip the local provider and use the deterministic extractor with a clear
  `fallback_reason`; a test asserts the later tasks did not attempt a local call.
- The degraded/skip state is per-run: a second `run_preflight` with a healthy
  client attempts the local provider normally.
- Preflight budgets against a smaller default context when the user has not
  raised `context_window_tokens`, and an explicit user value is still honoured;
  a test covers both.
- A test asserts the preflight messages contain no "think step by step" /
  reasoning instruction (no sequential-thinking step is added).
- Every preflight task still produces a valid artifact (no run failure on local
  timeout/skip).
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_preflight.py
python -m pytest
```

## Git instructions

Commit message:

```
Add preflight provider-degradation guardrails and smaller default context
```

Do not push.
