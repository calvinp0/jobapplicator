# 146 — Surface local LLM generation controls in Settings and the run trace

## Goal

Expose the new local LLM generation controls to the user: add a **Max output
tokens** field to the LLM Providers settings (backed by task 140), and surface
the new per-task telemetry in the run-trace UI — tokens/sec and whether the model
returned reasoning ("thinking"), plus the server-reported generation counts —
from the preflight manifest (task 145). This completes the goal item *show
tokens/sec and whether thinking was returned* and gives the output-cap setting a
UI.

## Background

Read first:

- `docs/llm_providers.md` — the Settings field list and the preflight manifest
  `performance` object / `thinking_returned` fields (after tasks 140–145).
- `docs/contracts/claude_run_directory.md` — the per-task preflight manifest
  entry schema (updated by task 145).
- `frontend/src/pages/SettingsPage.tsx` — the existing **LLM Providers** section
  with `num_ctx`, timeout, and context-budget fields (the pattern to follow for a
  new optional numeric field).
- `frontend/src/pages/RunDetailPage.tsx` — how preflight/run-trace details and the
  local-LLM fallback marker (task 134) are rendered.
- `frontend/src/api/types.ts` and `frontend/src/api/index.ts` — the typed local
  LLM settings shape and the run/preflight detail types.
- `frontend/src/test/localLlmSettings.test.tsx`,
  `frontend/src/test/runDetailLog.test.tsx`,
  `frontend/src/test/runDetailProgress.test.tsx` — existing tests to extend.

## Scope

- Settings: add an optional **Max output tokens** input to the LLM Providers
  section, wired to the `max_output_tokens` field on the local LLM settings
  payload (GET/PUT). Empty input means "unset" (sent as null/omitted), matching
  how `num_ctx` is handled. Add help text: optional; maps to Ollama
  `num_predict` / OpenAI-compatible `max_tokens`; bounds generation before
  fallback.
- Run trace: when a preflight task ran on the local provider, display the new
  telemetry from the manifest `performance` object — tokens/sec, output token
  count (`eval_count`), and a clear "reasoning returned" indicator when
  `thinking_returned` is true. Keep it within the existing Advanced/details
  disclosure so it does not clutter the primary flow.
- Update `frontend/src/api/types.ts` to type the new settings field and the new
  manifest/performance fields; thread them through `frontend/src/api/index.ts` as
  needed.
- Keep all wording user-facing and concise; reuse existing styles in
  `styles.css` where possible.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/pages/RunDetailPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/localLlmSettings.test.tsx`
- `frontend/src/test/runDetailLog.test.tsx`
- `frontend/src/test/runDetailProgress.test.tsx`
- `agent_tasks/146-frontend-local-llm-generation-controls.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (the backend fields come from tasks 140–145)
- `extension/**`, `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- Other `frontend/src/pages/**` and `frontend/src/test/**` files not listed above

## Out of scope

- A temperature setting control (temperature is an internal default, task 141).
- Exposing the generation/connection timeout `error_kind` (task 144) in the UI —
  may be a later follow-up.
- Any backend change.

## Acceptance criteria

- The LLM Providers settings include an optional **Max output tokens** field that
  loads from and saves to `max_output_tokens`; an empty field round-trips as
  unset.
- For a local preflight task, the run trace shows tokens/sec, output token count,
  and a clear "reasoning returned" indicator when `thinking_returned` is true,
  inside the existing Advanced/details disclosure.
- A run with no local telemetry (deterministic-only) shows none of the new
  fields and renders as before.
- Types in `frontend/src/api/types.ts` cover the new settings and manifest
  fields.
- Tests in the listed test files cover the new settings field and the run-trace
  telemetry display (present and absent cases).
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

- `cd frontend && npm test -- --run`
- `cd frontend && npm run build`

## Git instructions

Commit with the message:

```
Surface local LLM max output tokens setting and generation telemetry in the UI
```

Do not push.
