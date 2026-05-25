# Task 067: Frontend Settings Card for Default LLM Provider

## Goal

Add a Settings card that lets the user pick which CLI-based LLM the
`auto` tailoring path uses by default. The selector reads from the
backend's available-providers list and writes through the default-
provider endpoint added in task 066.

## Background

Read first:

- `agent_tasks/065-backend-llm-provider-registry.md`
- `agent_tasks/066-backend-llm-provider-default-setting.md`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/settingsPage.test.tsx`

The Settings page is already organised as a set of cards (task 038). The
new card slots in alongside Master Resumes and Evidence Banks.

## Scope

1. Add typed API helpers in `frontend/src/api/`:
   - `listLlmProviders()` calling `GET /api/llm-providers`.
   - `getLlmProviderSetting()` calling `GET /api/settings/llm-provider`.
   - `setLlmProviderSetting(id)` calling `PUT /api/settings/llm-provider`.
   - Matching TypeScript types in `frontend/src/api/types.ts`.

2. Add a "Tailoring LLM" card to `SettingsPage.tsx`:
   - Loads the current default and available providers on mount.
   - Renders a `<select>` (or radio group) populated from the
     available providers, showing each provider's display name and id.
   - Save button persists the new value via `setLlmProviderSetting`.
   - Inline success and error messages use `extractApiDetail` to match
     the other cards' error handling.
   - Show a short helper note explaining that this controls the LLM
     used by the existing "Generate Automatically" flow and that the
     Claude for Word handoff is unaffected.

3. Tests (in `frontend/src/test/`):
   - Renders the providers returned by the mocked API.
   - Marks the currently-selected provider as selected on load.
   - Calls the PUT endpoint with the selected id when Save is clicked.
   - Shows an error message when the PUT endpoint returns a non-2xx.
   - Existing Settings tests still pass.

4. No changes to `JobDetailPage` in this task — per-job override lives in
   task 068.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/settingsPage.test.tsx`
- `frontend/src/test/llmProviderSettings.test.tsx` (optional split)
- `agent_tasks/067-frontend-settings-llm-provider-card.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `extension/**`
- `runtime_prompts/**`
- `frontend/src/pages/JobDetailPage.tsx`
- `frontend/src/pages/RunDetailPage.tsx`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`

## Out of scope

- Per-job provider override (task 068).
- Adding new providers to the registry.
- Surfacing provider-specific configuration (binary paths, env vars) in
  the UI.

## Acceptance criteria

- A "Tailoring LLM" card appears in Settings.
- The card lists providers from the backend.
- Saving the form persists the choice and the selection survives a
  page reload.
- The "Claude for Word" flow is not affected by the selection.
- Existing `frontend` tests still pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

After verification passes:

1. Stage the changed frontend files, the new tests, and this task file.
2. Commit locally with the message:

```text
Add Settings card for default LLM provider
```

Do not push.
