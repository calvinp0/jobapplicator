# 151 — Add a reasoning-mode control (disabled / hidden / allowed) to LLM Provider settings

## Goal

Give the user a Settings control for the local LLM reasoning behaviour. The
backend already persists a `thinking_mode` field through `GET`/`PUT
/settings/local-llm` (task 131) with values `no_thinking`, `hide_thinking`, and
`strip_thinking`, but there is no UI to read or change it. Add a clearly-labelled
reasoning-mode selector to the LLM Providers settings with three options —
**Disabled**, **Hidden**, and **Allowed** — mapping to `no_thinking`,
`hide_thinking`, and `strip_thinking` respectively, and wire it through the typed
settings payload so it round-trips. This covers the goal item *add a setting:
reasoning mode = disabled / hidden / allowed*.

## Background

Read these before changing anything:

- `agent_tasks/131-add-local-llm-reasoning-controls.md` — defines the
  `thinking_mode` enum and its semantics (`strip_thinking` is the safe default;
  disabling reasoning is best-effort; stripping is the reliable backstop).
- `docs/llm_providers.md` — the **Reasoning control (`thinking_mode`)** section.
- `backend/app/routers/settings.py` — `thinking_mode` on the
  `LocalLLMSettingsView` (line ~116) and `LocalLLMSettingsUpdate` (line ~149);
  this is the GET/PUT contract the UI must match. Do not change the backend.
- `frontend/src/pages/SettingsPage.tsx` — the existing **LLM Providers** section
  and the pattern used for the `max_output_tokens` / `num_ctx` fields (task 146).
- `frontend/src/api/types.ts` — the `LocalLlmSettings` and
  `LocalLlmSettingsUpdate` interfaces (add the `thinking_mode` field).
- `frontend/src/api/index.ts` — how the settings payload is read/sent.
- `frontend/src/test/localLlmSettings.test.tsx` and
  `frontend/src/test/llmProviderSettings.test.tsx` — existing settings tests.

## Scope

- Add `thinking_mode: string` to the `LocalLlmSettings` and
  `LocalLlmSettingsUpdate` types in `frontend/src/api/types.ts`, threading it
  through the settings load/save path in `frontend/src/api/index.ts` as needed.
- Add a reasoning-mode selector (radio group or select) to the LLM Providers
  section of `SettingsPage.tsx`, with three user-facing options:
  - **Allowed** → `strip_thinking` (default) — model may reason; reasoning is
    stripped before parsing and not persisted.
  - **Hidden** → `hide_thinking` — reasoning is kept out of surfaced content/logs.
  - **Disabled** → `no_thinking` — ask the model not to reason (best-effort).
  Include concise help text noting that "Allowed" is the safe default and that
  disabling is best-effort while stripping is the reliable mechanism.
- Load the current value from the GET payload and send the chosen value on save;
  an unknown/missing value from the backend should display as the default
  ("Allowed") without breaking the form.
- Reuse existing settings styles; keep wording user-facing and concise.
- Update `docs/llm_providers.md` to note the Settings control and the
  label→`thinking_mode` mapping.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/api/index.ts`
- `frontend/src/test/localLlmSettings.test.tsx`
- `frontend/src/test/llmProviderSettings.test.tsx`
- `docs/llm_providers.md`
- `agent_tasks/151-frontend-reasoning-mode-setting.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (the `thinking_mode` GET/PUT contract already exists — do not
  change it)
- `frontend/src/pages/LocalLlmMonitorPage.tsx` (the monitor display is task 152)
- Other `frontend/src/pages/**` and `frontend/src/test/**` files not listed above
- `frontend/src/styles.css` is **not** needed; reuse existing classes
- `extension/**`, `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`

## Out of scope

- Any backend change (the field already round-trips).
- Surfacing the model-suitability warning or the diagnostic counters in the
  monitor (task 152).
- Renaming the backend enum values.

## Acceptance criteria

- The LLM Providers settings show a reasoning-mode control with **Disabled**,
  **Hidden**, and **Allowed** options mapping to `no_thinking`, `hide_thinking`,
  and `strip_thinking`.
- The control loads the current `thinking_mode` from GET and saves the selected
  value via PUT; an unknown/missing backend value falls back to "Allowed".
- `frontend/src/api/types.ts` types the `thinking_mode` field on both settings
  interfaces.
- `docs/llm_providers.md` documents the control and the label→value mapping.
- Tests cover rendering the three options, loading a saved value, and saving a
  changed value.
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Add reasoning-mode control (disabled/hidden/allowed) to LLM Provider settings
```

Do not push.
