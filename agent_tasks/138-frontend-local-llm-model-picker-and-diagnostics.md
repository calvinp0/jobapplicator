# Task 138: Surface installed models and clear connection diagnostics in Settings

## Goal

Make the Settings → local LLM panel usable for diagnosing Ollama setups: show the
list of installed models, offer a model picker populated from that list instead
of (or alongside) free-text entry, and present the three classified connection
failures from the backend — wrong provider URL, endpoint unavailable, and model
not installed — as distinct, clear messages rather than a raw error string. This
is the frontend counterpart to backend tasks 135 and 136.

## Background

Read these before changing anything:

- `docs/llm_providers.md` — user-facing local LLM docs (updated by tasks
  135/136 with the model-listing capability and the three failure classes).
- `agent_tasks/135-add-ollama-installed-models-detection.md` — added
  `GET /llm/local/models` returning `{ provider, ok, models, error, error_kind }`.
- `agent_tasks/136-classify-local-llm-connection-errors.md` — added `error_kind`
  and `installed_models` to the test-connection result (`LocalLlmTestResult`).
- `agent_tasks/128-clarify-context-budget-settings-ui.md` — the in-flight task
  that also edits `SettingsPage.tsx` / the local LLM settings types and tests.
  This task depends on it to avoid conflicting edits; read it so the panel
  structure and test patterns line up.
- `frontend/src/pages/SettingsPage.tsx` — the Settings page hosting the local
  LLM panel.
- `frontend/src/api/index.ts`, `frontend/src/api/types.ts` — the API client and
  the `LocalLlmSettings` / `LocalLlmTestResult` / `LocalLlmTestRequest` types.
- `frontend/src/test/localLlmSettings.test.tsx` — existing local LLM Settings
  tests and their mocking conventions.

## Scope

- Add a typed client method for `GET /llm/local/models` in
  `frontend/src/api/index.ts` and the matching response interface in
  `frontend/src/api/types.ts`. Add `error_kind` and `installed_models` to the
  `LocalLlmTestResult` interface to match the backend (task 136).
- In the local LLM Settings panel:
  - Add a "List models" / refresh affordance that calls the models endpoint and
    displays the installed models (using the current unsaved `base_url` /
    `provider` so it works before saving). Show a clear empty/unsupported state
    for the `openai_compatible` provider (model listing is Ollama-only).
  - Offer a model picker populated from the installed-model list (a select
    populated from the list; keep a free-text fallback so non-Ollama setups can
    still type a model name). Selecting a model updates the model field.
  - When a connection test fails, render a distinct message per `error_kind`:
    wrong provider URL (`bad_url`), endpoint unavailable
    (`endpoint_unavailable`), and model not installed (`model_not_installed`,
    listing the installed models). Fall back to the generic message for
    `unexpected`.
- Keep all new UI behind the existing experimental local LLM panel; do not change
  unrelated Settings sections.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/localLlmSettings.test.tsx`
- `agent_tasks/138-frontend-local-llm-model-picker-and-diagnostics.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (backend endpoints are tasks 135/136/137)
- The "Pull model" button, confirmation, and progress UI (task 139)
- `frontend/src/test/settingsPage.test.tsx` and other unrelated test files
  (scope to the local LLM settings test)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- The explicit "Pull model" action and its progress/confirmation UI (task 139).
- Any change to the context-budget labels (task 128 owns those).
- Backend behavior changes.

## Acceptance criteria

- `frontend/src/api/index.ts` has a typed method for `GET /llm/local/models`, and
  `frontend/src/api/types.ts` carries the models-response interface plus
  `error_kind` and `installed_models` on `LocalLlmTestResult`.
- The local LLM panel can list installed models and shows a clear
  unsupported/empty state for the `openai_compatible` provider; a test asserts
  the listing renders and the picker updates the model field.
- A failed test-connection renders a distinct message for each of `bad_url`,
  `endpoint_unavailable`, and `model_not_installed`; tests assert at least the
  `model_not_installed` and one transport case.
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Surface installed Ollama models and connection diagnostics in Settings
```

Do not push.
