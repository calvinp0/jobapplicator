# Task 126: Add optional Ollama `num_ctx` setting and send it on native requests

## Goal

Give the experimental local LLM subsystem an optional `num_ctx` setting that
controls the **running model server's** context length for Ollama, and send it
on outbound Ollama requests. Today the only context knob is
`context_window_tokens`, which drives JobApplicator's own budgeting math but
never reaches the model server — so a user who sets a large budget can still hit
silent server-side truncation because the Ollama model is running at its default
`num_ctx` (often 2048/4096). This task adds the persisted, validated `num_ctx`
field and the request-time plumbing so that, for the Ollama-native provider, the
configured server context is actually requested. The companion detection,
manifest logging, and UI changes are split into tasks 127 and 128.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — the provider-selection decision
  record. Local LLM is an experimental, opt-in provider for low-risk tasks;
  Claude Code remains the default for high-risk tailoring.
- `docs/llm_providers.md` — the user-facing local LLM documentation, including
  the Configuration and "Setting up Ollama / an OpenAI-compatible endpoint"
  sections.
- `agent_tasks/123-add-experimental-local-llm-provider.md` — introduced
  `backend/app/local_llm.py`, the `openai_compatible` vs `ollama` provider modes,
  and the persisted `LocalLLMConfig`.
- `agent_tasks/125-add-local-llm-context-budget-safeguards.md` — introduced the
  context-budget fields (`context_window_tokens`, `reserved_output_tokens`,
  `max_input_tokens`) and the over-budget handling.
- `backend/app/local_llm.py` — `LocalLLMConfig`, `get_config`, `save_config`,
  `PROVIDER_OLLAMA` / `PROVIDER_OPENAI_COMPATIBLE`, and `LocalLLMClient.chat`
  (the `payload` dict around lines 636–641 is where outbound request fields are
  assembled).
- `backend/app/schemas.py` and `backend/app/routers/settings.py` — the
  `GET`/`PUT /settings/local-llm` read/update shapes the config is exposed
  through.

## Scope

- Add an optional `num_ctx` field to `LocalLLMConfig` in
  `backend/app/local_llm.py`:
  - Type `Optional[int]`, default `None` (meaning "do not request a specific
    server context; leave the server at its own default").
  - Parse it in `get_config` (treat missing / null / non-int as `None`).
  - Validate it in `save_config`: when present it must be a positive integer;
    raise `LocalLLMValidationError` otherwise. It is independent of
    `context_window_tokens` (it configures the server, not JobApplicator's
    budget), so do **not** couple their validation.
- Send `num_ctx` on outbound requests for the **Ollama-native** provider only:
  - In `LocalLLMClient.chat`, when `config.provider == PROVIDER_OLLAMA` and
    `config.num_ctx` is set, include the Ollama context option in the request so
    the server actually runs at that context length. Ollama honours
    `options.num_ctx` on its native `/api/chat` surface; the OpenAI-compatible
    `/v1/chat/completions` surface does not. Choose the smallest correct
    mechanism (route the Ollama-native request through `/api/chat` with
    `{"options": {"num_ctx": N}}`, or include the `options` block the local
    server honours) and document the choice in a short code comment.
  - The `openai_compatible` provider must **never** send `num_ctx` — context
    cannot be set per-request there, and that limitation is surfaced to the user
    in task 127/128.
  - Keep the existing pre-send context-budget check unchanged; `num_ctx` does
    not replace JobApplicator's budgeting, it complements it.
- Surface `num_ctx` through the persisted-settings read/update path
  (`backend/app/schemas.py`, `backend/app/routers/settings.py`) so the value
  round-trips through `GET`/`PUT /settings/local-llm`.
- Update `docs/llm_providers.md` Configuration section to document the new
  optional `num_ctx` setting: what it does (sets the Ollama server's running
  context length), that it only applies to the Ollama-native provider, and that
  it is distinct from JobApplicator's context budget.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/schemas.py`
- `backend/app/routers/settings.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/126-add-ollama-num-ctx-setting.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (manifest logging is task 127)
- `backend/app/routers/local_llm.py` (test-connection / detection is task 127)
- `frontend/**` (UI is task 128)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Detecting or reporting the server's actual context length (task 127).
- Recording assumed/effective context in the preflight manifest (task 127).
- Any Settings UI control or label change (task 128).
- Changing the over-budget handling, the deterministic fallback chain, or the
  task-risk policy.
- Wiring `num_ctx` for non-Ollama servers.

## Acceptance criteria

- `LocalLLMConfig` has an optional `num_ctx` field defaulting to `None`, parsed
  by `get_config` and validated by `save_config` (positive int or absent).
- For `provider == "ollama"` with `num_ctx` set, the outbound request payload
  carries the Ollama context option; a test asserts the value reaches the
  request body.
- For `provider == "openai_compatible"`, the outbound request never carries
  `num_ctx`, regardless of the stored value; a test asserts its absence.
- `num_ctx` round-trips through `GET`/`PUT /settings/local-llm` and an invalid
  (non-positive / non-int) value is rejected with `LocalLLMValidationError`.
- `docs/llm_providers.md` documents the optional `num_ctx` setting and that it is
  Ollama-only and distinct from the context budget.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Add optional Ollama num_ctx and send it on native requests
```

Do not push.
