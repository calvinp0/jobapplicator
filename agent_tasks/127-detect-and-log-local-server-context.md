# Task 127: Detect local server context and log effective assumed context in the preflight manifest

## Goal

Make the gap between JobApplicator's *assumed* context and the model server's
*actual* context observable. After task 126 a user can set an Ollama `num_ctx`,
but JobApplicator still cannot tell the user what context the running server is
really using, and the preflight manifest does not record the context it assumed
for a run. This task (1) detects the server-reported context when the provider
makes it discoverable (Ollama), (2) returns that plus a `context_verified` flag
and an explanatory warning from the connection test, and (3) logs the effective
assumed context (and, when known, the server-reported context and `num_ctx`) in
the preflight manifest so every run carries an auditable record of the context
it budgeted against. The Settings UI that consumes these fields is task 128.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — provider selection; preflight
  artifacts are advisory and never required.
- `docs/llm_providers.md` — Configuration, "Testing the connection", and
  "Preflight analysis pipeline (task 124)" sections, including the existing
  manifest `context` block example.
- `docs/contracts/claude_run_directory.md` — the
  `preflight/preflight_manifest.json` section (search for
  `preflight_manifest.json` and the per-task `context` object) and the
  provider-routed preflight pipeline description.
- `agent_tasks/124-add-provider-routed-preflight-analysis-pipeline.md` and
  `agent_tasks/125-add-local-llm-context-budget-safeguards.md` — introduced
  `backend/app/preflight.py`, the manifest, and the per-task `context` dict.
- `agent_tasks/126-add-ollama-num-ctx-setting.md` — the immediately preceding
  task that added the `num_ctx` config field and Ollama request plumbing this
  task builds on.
- `backend/app/local_llm.py` — `LocalLLMClient`, `_chat_url`, the provider
  modes, and `LocalLLMConfig`.
- `backend/app/routers/local_llm.py` — the `POST /llm/local/test-connection`
  endpoint and its `LocalLLMTestResult` (currently returns
  `context_window_tokens` and `max_input_tokens`).
- `backend/app/preflight.py` — `_prepare_local_messages` (builds the per-task
  `context_info` dict around lines 480–525) and `run_preflight` (assembles the
  top-level `manifest` dict around lines 332–344).

## Scope

- Add a server-context detection helper to `backend/app/local_llm.py`:
  - For the Ollama-native provider, query the server for the running model's
    context length (Ollama exposes model metadata via its native `/api/show`
    endpoint, which reports the model's context length / the effective
    `num_ctx`). Derive the base host from the configured `base_url`.
  - Return a small structured result: the detected server context (int or
    `None`), whether detection succeeded (`context_verified`), and a short
    human-readable note. Network/parse failures must degrade to
    `context_verified = False` with a clear note — never raise into the caller.
  - For the `openai_compatible` provider, do not attempt detection: return
    `context_verified = False` with a note explaining that an OpenAI-compatible
    endpoint does not expose its context window, so JobApplicator cannot verify
    that the server's real context matches the configured budget.
- Extend `POST /llm/local/test-connection`
  (`backend/app/routers/local_llm.py`, schema and route):
  - Add `server_reported_context_tokens: int | None`, `context_verified: bool`,
    and a `context_warning: str | None` to the result.
  - Populate them from the detection helper. When the provider is
    OpenAI-compatible, or detection fails, set `context_verified = false` and a
    `context_warning` explaining the context could not be verified.
  - Accept an optional `num_ctx` override in the test request (mirroring the
    existing override fields) so task 128 can test unsaved edits.
- Log effective context in the preflight manifest (`backend/app/preflight.py`):
  - Add `effective_assumed_context_tokens` to each local task's `context` dict —
    the context window JobApplicator budgeted against for that task
    (`cfg.context_window_tokens`). When `cfg.num_ctx` is set, also record it as
    `requested_num_ctx`.
  - Record the server-reported context and verification status once at the
    manifest top level when the run intends the local provider (e.g.
    `assumed_context_tokens`, `server_reported_context_tokens`,
    `context_verified`). Detection is best-effort: a detection failure must not
    fail preflight; record `context_verified = false` and continue.
- Update `docs/contracts/claude_run_directory.md` to document the new manifest
  context fields, and update `docs/llm_providers.md` (Testing the connection +
  Preflight sections) to describe server-context detection, the
  `context_verified` semantics, and the OpenAI-compatible "cannot verify"
  warning.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/preflight.py`
- `backend/app/routers/local_llm.py`
- `backend/app/schemas.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/127-detect-and-log-local-server-context.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/routers/settings.py` (persisted-config shape is task 126)
- `frontend/**` (UI is task 128)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Adding or renaming any Settings UI control or label (task 128).
- Changing the budgeting math, the over-budget handling, or the task-risk
  policy.
- Auto-applying a detected context to the budget (detection is reporting only;
  the user stays in control of the budget).
- Detection mechanisms for non-Ollama servers beyond returning the
  "cannot verify" warning.

## Acceptance criteria

- A detection helper in `backend/app/local_llm.py` returns the server-reported
  context, a `context_verified` flag, and a note, and never raises on network or
  parse failure; tests cover the Ollama success path, the Ollama failure
  (degrade) path, and the OpenAI-compatible "cannot verify" path.
- `POST /llm/local/test-connection` returns `server_reported_context_tokens`,
  `context_verified`, and `context_warning`, and accepts a `num_ctx` override.
- The preflight manifest records `effective_assumed_context_tokens` per local
  task and a top-level assumed/server/verified context summary for local runs; a
  detection failure leaves `context_verified = false` without failing preflight.
- `docs/contracts/claude_run_directory.md` and `docs/llm_providers.md` document
  the new fields and the verification/warning semantics.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest backend/tests/test_preflight.py
python -m pytest
```

## Git instructions

Commit message:

```
Detect local server context and log assumed context in preflight manifest
```

Do not push.
