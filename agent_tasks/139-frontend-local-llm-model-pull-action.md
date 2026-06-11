# Task 139: Add a confirmation-gated "Pull model" action with progress in Settings

## Goal

Add an explicit "Pull model" control to the Settings → local LLM panel that lets
a user install a missing Ollama model on demand, gated behind a confirmation
dialog, with visible progress while the pull runs and a clear warning that the
app cannot verify whether the model fits the host's disk/VRAM. This is the
frontend counterpart to backend task 137. The pull never starts without an
explicit click + confirmation, and is only offered for the Ollama-native
provider.

## Background

Read these before changing anything:

- `docs/llm_providers.md` — user-facing local LLM docs (updated by task 137 with
  the explicit, confirmation-gated, Ollama-only pull action and the
  never-automatic guarantee).
- `agent_tasks/137-add-ollama-model-pull-endpoint.md` — added `POST
  /llm/local/pull` (explicit model name required, Ollama-only, structured
  progress via stream or start+poll, disk/VRAM-unknown advisory). Match whichever
  progress transport that task implemented.
- `agent_tasks/138-frontend-local-llm-model-picker-and-diagnostics.md` — added
  the installed-model list, picker, and `error_kind` diagnostics this task
  builds on (it surfaces `model_not_installed`, which is the natural trigger for
  offering a pull). This task depends on 138 to avoid conflicting edits to the
  same panel.
- `frontend/src/pages/SettingsPage.tsx` — the Settings page / local LLM panel.
- `frontend/src/api/index.ts`, `frontend/src/api/types.ts` — API client + types.
- `frontend/src/test/localLlmSettings.test.tsx` — local LLM Settings tests.

## Scope

- Add a typed client method for `POST /llm/local/pull` (and the poll-status
  method if task 137 used a poll model) in `frontend/src/api/index.ts`, plus the
  request/response/progress interfaces in `frontend/src/api/types.ts`.
- In the local LLM Settings panel, add a "Pull model" affordance shown only for
  the Ollama-native provider. Clicking it must require an explicit confirmation
  step (a confirm dialog / inline confirm) before any request is sent — no pull
  fires on the first click alone.
- While the pull runs, show progress (status text and a progress indicator driven
  by the backend's progress updates — streamed or polled to match task 137).
  Surface success (model now installed; refresh the installed-model list from
  task 138) and failure clearly.
- Display the disk/VRAM-unknown warning next to the pull control and/or in the
  confirmation step, matching the backend advisory.
- When the connection diagnostics report `model_not_installed` (task 138), make
  the pull action the obvious next step (e.g. offer to pull the named model).
- Do not auto-trigger a pull from any other flow; the only entry point is this
  explicit, confirmed control.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/localLlmSettings.test.tsx`
- `agent_tasks/139-frontend-local-llm-model-pull-action.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (the pull endpoint is task 137)
- `frontend/src/test/settingsPage.test.tsx` and other unrelated test files
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Any backend behavior change (task 137 owns the endpoint and its guarantees).
- Model deletion / management beyond pulling.
- Auto-pull on missing model, on startup, or during tailoring.

## Acceptance criteria

- `frontend/src/api/index.ts` / `types.ts` carry the pull request/response (and
  poll-status, if used) types matching task 137.
- The "Pull model" control appears only for the Ollama-native provider and
  requires an explicit confirmation before sending the request; a test asserts no
  request fires without confirmation and one fires after confirming.
- Pull progress and success/failure are rendered; the disk/VRAM-unknown warning
  is shown; a test asserts the warning and a progress/terminal state.
- A `model_not_installed` diagnostic offers the pull as the next step.
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Add confirmation-gated Ollama model-pull action with progress in Settings
```

Do not push.
