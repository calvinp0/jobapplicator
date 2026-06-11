# Task 135: Detect installed Ollama models via `/api/tags`

## Goal

Give the experimental local LLM subsystem a way to discover which models are
actually installed on an Ollama server, and a single helper that classifies why
a local endpoint call failed. Today the only operational probe is
`test_connection`, which sends a chat prompt and reports raw transport errors
(e.g. `HTTP 404 ...`) with no way to tell "endpoint unavailable" from "wrong
URL" from "model not installed". This task adds a model-listing capability and an
error-classification helper that later tasks (136 diagnostics, 137 pull, 138/139
UI) build on. It is backend-only and changes no existing behavior of
`test_connection`.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — local LLM is an experimental,
  opt-in provider for low-risk tasks; Claude Code remains the default for
  high-risk tailoring. Nothing in this task may touch the `auto` tailoring flow.
- `docs/llm_providers.md` — the user-facing local LLM documentation.
- `agent_tasks/123-add-experimental-local-llm-provider.md` — introduced
  `backend/app/local_llm.py`, the `openai_compatible` vs `ollama` provider modes
  (`PROVIDER_OLLAMA` / `PROVIDER_OPENAI_COMPATIBLE`), `LocalLLMConfig`, and the
  `_post_json` network boundary helper that tests monkeypatch.
- `backend/app/local_llm.py` — `LocalLLMConfig`, `LocalLLMClient` (its
  `_chat_url` derives `{base_url}/chat/completions`), `_post_json` (the
  monkeypatchable network boundary, currently POST-only), and the existing
  `test_connection`.
- `backend/app/routers/local_llm.py` — the operational router
  (`/llm/local/...`), where `test_connection` is exposed and where new
  operational endpoints belong (response models are defined inline as pydantic
  `BaseModel`s, matching `LocalLLMTestResult`).
- `backend/tests/test_local_llm.py` — the existing local LLM test patterns,
  including how `_post_json` is monkeypatched.

## Scope

- Add a module-level `_get_json(url, *, headers=None, timeout=...)` helper to
  `backend/app/local_llm.py` mirroring `_post_json` (a monkeypatchable GET
  boundary). Keep it small; it exists so tests can stub `/api/tags` without a
  live server.
- Add an error-classification helper to `backend/app/local_llm.py`, e.g.
  `classify_endpoint_error(exc, *, base_url) -> tuple[str, str]` returning a
  stable machine `kind` and a human message. The `kind` values must distinguish
  at least:
  - `endpoint_unavailable` — connection refused / DNS / `URLError` (server not
    reachable at all).
  - `bad_url` — reachable host but an HTTP status that indicates the path or
    surface is wrong (e.g. 404 on the base path, 405).
  - `unexpected` — anything else (with the underlying detail preserved).
  ("model not installed" is derived in task 136 from the installed-model list,
  not from transport errors, so it is **not** a `kind` here.)
- Add `list_models()` to `LocalLLMClient` that, for the **Ollama-native**
  provider, calls the server's `/api/tags` endpoint (derive the Ollama API root
  from `base_url` — strip a trailing `/v1` if present, since the native API and
  the OpenAI-compatible `/v1` surface share a host) and returns the installed
  model names. For the `openai_compatible` provider, `list_models()` must return
  a result that clearly indicates model listing is unsupported on that surface
  (do **not** raise). Return a small structured result (names + ok flag +
  classified error) — define a dataclass or reuse `LLMCallResult`-style shape;
  pick the smallest correct option and keep transport errors non-raising.
- Add a `GET /llm/local/models` endpoint to
  `backend/app/routers/local_llm.py` that calls `list_models()` on the persisted
  config and returns `{ provider, ok, models: [...], error, error_kind }`.
  Accept the same optional `base_url` / `provider` query or body overrides the
  test-connection endpoint accepts, so the UI can list models for unsaved edits
  (reuse the override-overlay pattern from `test_local_llm_connection`; you may
  factor that overlay into a small shared helper).
- Update `docs/llm_providers.md` to document the new model-listing capability and
  that installed-model detection is Ollama-native only.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/routers/local_llm.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/135-add-ollama-installed-models-detection.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py`
- `backend/app/schemas.py` (define new response models inline in the router;
  the persisted-settings schema is being changed by in-flight tasks 126/130/131)
- `frontend/**` (model-picker UI is task 138)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Changing `test_connection` behavior or its error reporting (task 136).
- Reporting "model not installed" (task 136 derives it from the model list).
- Pulling / installing models (task 137).
- Any Settings UI (tasks 138/139).
- Wiring model detection into preflight, the `auto` tailoring flow, or app
  startup.

## Acceptance criteria

- `backend/app/local_llm.py` has a monkeypatchable `_get_json` GET helper and a
  `classify_endpoint_error` helper returning the documented `kind` values.
- `LocalLLMClient.list_models()` calls `/api/tags` for the Ollama-native
  provider (deriving the native API root from `base_url`) and returns installed
  model names; for `openai_compatible` it returns a clear "unsupported"
  result without raising. Tests assert both, with `_get_json` monkeypatched.
- A connection failure (URLError) and an HTTP 404 produce distinct `error_kind`
  values (`endpoint_unavailable` vs `bad_url`); a test asserts the distinction.
- `GET /llm/local/models` returns `{ provider, ok, models, error, error_kind }`
  and honors `base_url` / `provider` overrides; a test exercises the endpoint.
- `docs/llm_providers.md` documents Ollama-native model listing.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Detect installed Ollama models via /api/tags
```

Do not push.
