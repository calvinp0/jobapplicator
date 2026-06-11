# Task 130: Make the local LLM per-call timeout configurable with an Ollama-aware default

## Goal

Give the experimental local LLM subsystem a configurable per-call timeout with a
recommended default of **180 seconds for Ollama**, so slow local models (which
often pay a large first-token / model-load cost) are not cut off at the current
60-second default and silently forced into the deterministic fallback on every
run. Today `timeout_seconds` defaults to `60` regardless of provider; a freshly
loaded Ollama model can take well over a minute to answer the first preflight
task, so the local provider looks "broken" when it is merely cold. This task
keeps the timeout user-configurable and validated, but raises the effective
default for the Ollama-native provider to 180s and documents the change. It is
the first task in the local-LLM performance-guardrails pack (131–134 build on
it).

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — local LLM is an experimental,
  opt-in provider for low-risk tasks; Claude Code remains the default for
  high-risk tailoring. Do not change that policy.
- `docs/llm_providers.md` — the user-facing local LLM documentation, including
  the Configuration and "Setting up Ollama / an OpenAI-compatible endpoint"
  sections.
- `agent_tasks/123-add-experimental-local-llm-provider.md` — introduced
  `backend/app/local_llm.py`, the `openai_compatible` vs `ollama` provider
  modes, and the persisted `LocalLLMConfig`.
- `agent_tasks/126-add-ollama-num-ctx-setting.md` and
  `agent_tasks/127-detect-and-log-local-server-context.md` — the immediately
  preceding local-LLM tasks this pack lands on top of.
- `backend/app/local_llm.py` — `DEFAULT_TIMEOUT_SECONDS` (currently `60`, around
  line 66), `LocalLLMConfig.timeout_seconds`, `get_config`, `save_config` (the
  `timeout_seconds` validation around lines 305–309), `get_settings_view`, and
  `LocalLLMClient.chat` (the `effective_timeout` resolution around lines
  647–648).
- `backend/app/schemas.py` and `backend/app/routers/settings.py` — the
  `GET`/`PUT /settings/local-llm` read/update shapes the timeout is exposed
  through.

## Scope

- Introduce a recommended Ollama timeout default of `180` seconds in
  `backend/app/local_llm.py` (e.g. a `DEFAULT_OLLAMA_TIMEOUT_SECONDS = 180`
  constant alongside the existing `DEFAULT_TIMEOUT_SECONDS = 60`).
- Resolve the *effective* per-call timeout in a provider-aware way:
  - When `provider == "ollama"` and the user has **not** explicitly configured a
    timeout, the effective timeout is 180s.
  - When the user has explicitly configured `timeout_seconds`, that value is used
    verbatim for every provider (the user override always wins).
  - The OpenAI-compatible provider keeps the existing 60s default when no
    explicit value is set.
  - Pick the smallest correct mechanism (e.g. resolve the default at
    `get_config` time based on provider, or compute an effective timeout in
    `LocalLLMClient`), and document the choice in a short code comment. Do not
    silently overwrite a user's stored value with the provider default.
- Keep `timeout_seconds` user-configurable and validated: `save_config` must
  continue to reject a non-integer or non-positive timeout with
  `LocalLLMValidationError`.
- Ensure the resolved effective timeout is the value actually passed to the
  outbound request in `LocalLLMClient.chat` (the per-call bound), so a configured
  or defaulted timeout is honoured per local LLM call.
- Surface the effective/recommended timeout through the persisted-settings read
  path (`get_settings_view` → `GET /settings/local-llm`) so the UI in a later
  task can show the value in force. Keep the stored field name `timeout_seconds`.
- Update `docs/llm_providers.md` Configuration section to document the new
  Ollama-aware default (180s), why it exists (cold-model first-token latency),
  and that an explicit user-configured timeout overrides it.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/schemas.py`
- `backend/app/routers/settings.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/130-add-local-llm-task-timeout-and-ollama-default.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (degraded-state / skip-remaining is task 132)
- `frontend/**` (UI is task 134)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Per-run degraded state or skipping remaining local calls after a timeout
  (task 132).
- Any reasoning / thinking controls (task 131).
- Manifest / run-trace logging of elapsed time or timeout (task 133).
- Any Settings UI control or label change (task 134).
- Changing the over-budget handling, the deterministic fallback chain, or the
  task-risk policy.

## Acceptance criteria

- A 180-second Ollama timeout default exists and is applied when the provider is
  `ollama` and the user has not explicitly set a timeout; a test asserts the
  effective timeout passed to the request is 180 in that case.
- An explicitly configured `timeout_seconds` is used verbatim for any provider
  (a test asserts the user value wins over the provider default).
- The OpenAI-compatible provider keeps a 60s default when no explicit timeout is
  set; a test asserts this.
- `save_config` still rejects a non-positive / non-integer timeout with
  `LocalLLMValidationError`.
- The effective timeout round-trips through `GET /settings/local-llm`.
- `docs/llm_providers.md` documents the Ollama-aware default and the override
  rule.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Make local LLM per-call timeout configurable with Ollama-aware default
```

Do not push.
