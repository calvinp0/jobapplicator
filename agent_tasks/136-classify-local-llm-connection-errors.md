# Task 136: Classify local LLM connection errors and report missing models

## Goal

Make the local LLM connection test diagnose *why* it failed instead of echoing a
raw transport error. After this task, testing the connection for the
Ollama-native provider first checks the installed-model list, reports the
installed models back to the caller, and — when the configured model is not
installed — says "model not installed" rather than surfacing a raw `HTTP 404`.
More generally, the test result distinguishes three failure classes: **endpoint
unavailable** (server not reachable), **wrong provider URL** (reachable but the
surface/path is wrong), and **missing model** (server reachable, model not
installed). This turns an opaque failure into an actionable one.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — experimental, opt-in local
  provider; never the high-risk tailoring default.
- `docs/llm_providers.md` — user-facing local LLM docs.
- `agent_tasks/135-add-ollama-installed-models-detection.md` — added
  `LocalLLMClient.list_models()` (Ollama `/api/tags`), the `_get_json` helper,
  the `classify_endpoint_error` helper, and `GET /llm/local/models`. This task
  builds directly on those.
- `backend/app/routers/local_llm.py` — `test_local_llm_connection`,
  `LocalLLMTestRequest`, and `LocalLLMTestResult` (the response model where new
  diagnostic fields belong).
- `backend/app/local_llm.py` — `LocalLLMClient.test_connection`, `chat` (where
  `urllib.error.HTTPError` / `URLError` are currently turned into flat error
  strings), and the helpers added in task 135.

## Scope

- Extend the connection-test path so that, for the **Ollama-native** provider,
  it calls `list_models()` *before* (or as part of) the chat probe and:
  - includes the installed model names in the result,
  - when the configured model is absent from the installed list, reports a
    `model_not_installed` failure with a clear message (e.g.
    `Model "<name>" is not installed on this Ollama server. Installed: ...`),
    instead of letting the chat probe fail with a raw 404.
  - For the `openai_compatible` provider, keep the existing probe behavior but
    still classify transport failures (below). Model listing is unsupported
    there, so a missing model cannot be detected pre-probe — that is expected.
- Classify connection-test failures using `classify_endpoint_error` (task 135)
  plus the model-not-installed check, and surface a stable `error_kind` on
  `LocalLLMTestResult`. The required kinds: `endpoint_unavailable`, `bad_url`,
  `model_not_installed`, `unexpected`, and `none`/`ok` on success.
- Make the human `message` on `LocalLLMTestResult` reflect the classified kind so
  the UI (task 138) can show a clear, distinct error for each of: wrong provider
  URL, endpoint unavailable, and model not installed.
- Add the new fields (`error_kind`, `installed_models`) to `LocalLLMTestResult`
  and populate them in `test_local_llm_connection`. Keep existing fields stable.
- Update `docs/llm_providers.md` Troubleshooting/Configuration to describe the
  three failure classes and what each means.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/routers/local_llm.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/136-classify-local-llm-connection-errors.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/schemas.py` (test result models live in the router; persisted
  settings schema is owned by in-flight tasks 126/130/131)
- `backend/app/preflight.py`
- `frontend/**` (diagnostic UI is task 138)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Pulling / installing a missing model (task 137 adds the explicit pull action).
- The Settings model picker and error display (task 138).
- Changing the chat / tailoring / preflight paths beyond error classification on
  the operational test endpoint.

## Acceptance criteria

- For the Ollama-native provider with a model that is not in the `/api/tags`
  list, `POST /llm/local/test-connection` returns `ok=false`,
  `error_kind="model_not_installed"`, a message naming the missing model, and
  the installed-model list — with no raw `HTTP 404` leaking into `message`. A
  test asserts this with `_get_json`/`_post_json` monkeypatched.
- A connection refused / unreachable host yields
  `error_kind="endpoint_unavailable"`; an HTTP 404 on a reachable host yields
  `error_kind="bad_url"`. Tests assert both.
- A successful test yields `error_kind` of `none` (or `ok`) and `installed_models`
  populated for the Ollama provider.
- `LocalLLMTestResult` exposes `error_kind` and `installed_models`; existing
  fields are unchanged.
- `docs/llm_providers.md` documents the three failure classes.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Classify local LLM connection errors and report missing models
```

Do not push.
