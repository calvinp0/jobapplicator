# Task 137: Add an explicit, confirmation-gated Ollama model-pull action

## Goal

Add an opt-in, explicit "pull model" capability for the Ollama-native provider
using the server's `/api/pull` endpoint, so a user who discovers (via task 136)
that their selected model is not installed can install it on demand. The pull is
strictly an explicit, operator-initiated action: it is never invoked
automatically during resume tailoring, preflight, or app startup, and the API
contract requires an explicit request. Pull progress is reported back so the UI
(task 139) can stream/poll it, and the response warns that the backend cannot
verify whether the model will fit the host's disk/VRAM. This task is
backend-only.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — local LLM is experimental and
  opt-in; Claude Code remains the default for high-risk tailoring. A model pull
  must never become part of the `auto` flow or block startup.
- `docs/llm_providers.md` — user-facing local LLM docs.
- `agent_tasks/135-add-ollama-installed-models-detection.md` — `_get_json`,
  `_post_json`, `classify_endpoint_error`, deriving the Ollama-native API root
  from `base_url`, and `LocalLLMClient.list_models()`.
- `agent_tasks/136-classify-local-llm-connection-errors.md` — the
  `model_not_installed` diagnosis the pull action complements.
- `backend/app/local_llm.py` — `LocalLLMClient`, the `_post_json` network
  boundary, and `PROVIDER_OLLAMA`.
- `backend/app/routers/local_llm.py` — operational `/llm/local/...` router and
  inline response-model conventions.

## Scope

- Add a `pull_model(name, *, on_progress=None)` capability to `LocalLLMClient`
  (Ollama-native only) that calls the server's `/api/pull`. Ollama streams
  newline-delimited JSON progress objects; consume them and surface progress as
  structured updates (status string, and completed/total bytes when present).
  For the `openai_compatible` provider, refuse with a clear "pulling is only
  supported for the Ollama-native provider" error (do not raise an unhandled
  exception). Keep the network call routed through the monkeypatchable boundary
  so tests can simulate a streamed pull without a live server.
- Add a `POST /llm/local/pull` endpoint to `backend/app/routers/local_llm.py`
  that:
  - requires the model name explicitly in the request body (no defaulting to a
    "pull whatever" behavior), and refuses unless the persisted provider is
    Ollama-native (or an explicit `provider=ollama` override is supplied).
  - returns a structured result the UI can render as progress. Choose the
    smallest correct transport for progress (either a streaming response, or a
    start + poll-status pair). If you use a poll model, add the matching status
    endpoint; if you stream, document the shape. Keep it bounded and
    non-blocking on the event loop.
  - includes an explicit advisory in the response/contract that the backend
    cannot verify disk/VRAM fit for the requested model.
- Confirmation is the caller's responsibility (the UI in task 139 gates it
  behind a dialog); the backend's contract requirement is that the action is
  only ever reachable through this explicit endpoint, never as a side effect of
  any other call.
- Update `docs/llm_providers.md` to document the explicit pull action, that it is
  Ollama-only, that it requires confirmation in the UI, that the disk/VRAM fit is
  unknown, and that pulling never happens automatically during tailoring or
  startup.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/routers/local_llm.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/137-add-ollama-model-pull-endpoint.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/schemas.py` (define pull request/response models inline in the
  router)
- `backend/app/preflight.py`, `backend/app/claude_worker.py`,
  `backend/app/run_directory.py` (pull must not touch the tailoring/preflight
  paths)
- `backend/app/main.py` (pull must not run at startup)
- `frontend/**` (pull UI is task 139)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- The Settings "Pull model" button, confirmation dialog, and progress display
  (task 139).
- Auto-pulling a missing model from the test-connection or preflight paths.
- Deleting / managing already-installed models.

## Acceptance criteria

- `LocalLLMClient.pull_model` calls `/api/pull` for the Ollama-native provider
  and surfaces streamed progress updates; for `openai_compatible` it returns a
  clear unsupported result without raising. Tests assert both with the network
  boundary monkeypatched to emit simulated progress lines.
- `POST /llm/local/pull` requires an explicit model name, refuses non-Ollama
  providers, returns structured progress (stream or start+poll), and its
  response/contract carries the disk/VRAM-unknown advisory. A test exercises the
  endpoint, including the missing-name and wrong-provider refusals.
- No tailoring/preflight/startup code path invokes `pull_model`; grep evidence
  (the only caller is the new endpoint) is reflected in the test or noted in the
  commit.
- `docs/llm_providers.md` documents the explicit, confirmation-gated,
  Ollama-only pull action and the never-automatic guarantee.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Add explicit confirmation-gated Ollama model-pull endpoint
```

Do not push.
