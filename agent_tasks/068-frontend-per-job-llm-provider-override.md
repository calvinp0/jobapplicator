# Task 068: Per-Job LLM Provider Override on Generate

## Goal

Let the user override the default LLM provider for a single generation
without changing the Settings default. The override surfaces next to the
existing "Generate Automatically" button on the job workspace.

## Background

Read first:

- `agent_tasks/065-backend-llm-provider-registry.md`
- `agent_tasks/066-backend-llm-provider-default-setting.md`
- `agent_tasks/067-frontend-settings-llm-provider-card.md`
- `frontend/src/pages/JobDetailPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/jobDetailWorkspace.test.tsx`

The auto-generation button already exists in the JobDetailPage workspace
stepper (task 034 / 062). The backend already accepts an optional
`llm_provider` on the run-creation endpoint (task 065).

## Scope

1. In `JobDetailPage.tsx`, fetch the providers list (via
   `listLlmProviders` from task 067) when the workspace mounts and
   render a compact selector next to the "Generate Automatically"
   button. The selector defaults to the persisted default returned by
   `getLlmProviderSetting`; the user may change it for the current run
   only.

2. Pass the chosen provider id to the existing run-creation API call
   when "Generate Automatically" is clicked. If the selector is left at
   the default, omit the field so the backend's fallback is used.

3. Do not surface the selector on the "Prepare for Claude for Word"
   button — Word handoff is not an LLM-provider choice.

4. After a run starts, display the chosen provider name in the run's
   progress area so the user can see which tool is running.

5. Tests:
   - The selector lists providers from the mocked API.
   - The default selection matches the mocked default-provider setting.
   - Clicking Generate with a non-default selection sends the chosen
     provider id to the run-creation endpoint.
   - Clicking Generate with the default selection does not include
     `llm_provider` in the request body (or sends the default id —
     either is acceptable as long as it is consistent and tested).
   - The Claude for Word button does not include the provider field.
   - Existing JobDetailPage tests still pass.

## Allowed files

- `frontend/src/pages/JobDetailPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/jobDetailWorkspace.test.tsx`
- `frontend/src/test/jobDetailLlmProvider.test.tsx` (optional new test file)
- `agent_tasks/068-frontend-per-job-llm-provider-override.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `extension/**`
- `runtime_prompts/**`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/pages/RunDetailPage.tsx`
- `frontend/src/pages/ResumeVersionDetailPage.tsx`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`

## Out of scope

- Persisting per-job overrides between sessions (the override is for
  one run only).
- Adding providers to the registry.
- Showing the override on any page other than the job workspace.

## Acceptance criteria

- The job workspace shows a provider selector next to "Generate
  Automatically".
- The selector defaults to the Settings default.
- A non-default selection is sent to the run-creation endpoint.
- The Claude for Word button is unaffected.
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
Add per-job LLM provider override on generate
```

Do not push.
