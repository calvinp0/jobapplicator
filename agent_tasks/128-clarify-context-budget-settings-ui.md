# Task 128: Clarify context-budget label and surface server context in Settings

## Goal

Make the Settings → Local LLM card honest about what its context controls
actually do. Today the field is labelled "Context window tokens", which reads as
if it sets the model server's context — but it only drives JobApplicator's own
budgeting math (it never reaches the server). This task renames that label to
"JobApplicator context budget", adds helper text explaining the distinction,
exposes the optional Ollama `num_ctx` control (from task 126), shows the
server-reported context when JobApplicator can detect it, and warns when the
endpoint is OpenAI-compatible and the real context cannot be verified (from task
127). It is a frontend-only task that consumes the backend fields added in tasks
126 and 127.

## Background

Read these before changing anything:

- `docs/llm_providers.md` — Configuration and "Testing the connection" sections;
  the wording there should match the UI copy you write.
- `docs/adr/009-llm-provider-selection.md` — local LLM is experimental and
  opt-in; keep the UI framing consistent with that.
- `agent_tasks/126-add-ollama-num-ctx-setting.md` — added the `num_ctx` config
  field exposed via `GET`/`PUT /settings/local-llm`.
- `agent_tasks/127-detect-and-log-local-server-context.md` — added
  `server_reported_context_tokens`, `context_verified`, and `context_warning`
  (plus a `num_ctx` override) to `POST /llm/local/test-connection`.
- `frontend/src/pages/SettingsPage.tsx` — the `local-llm-card` section (the
  "Context window tokens" field around lines 765–812, the provider `<select>`
  around lines 712–724, the "Configured context" / "Usable input budget"
  summary, and the test-connection handler).
- `frontend/src/api/types.ts` — `LocalLlmSettings`, `LocalLlmSettingsUpdate`,
  `LocalLlmTestResult`, `LocalLlmTestRequest`.
- `frontend/src/api/index.ts` — the local-LLM settings and test-connection API
  calls.
- `frontend/src/test/localLlmSettings.test.tsx` and
  `frontend/src/test/settingsPage.test.tsx` — existing coverage to extend.

## Scope

- Rename the context-budget control label in the local-LLM card from
  "Context window tokens" to **"JobApplicator context budget"**, and update the
  summary label "Configured context" to read consistently (e.g.
  "JobApplicator context budget"). Keep the underlying field
  (`context_window_tokens`) and its computed `max_input_tokens` behavior
  unchanged.
- Add helper text near the renamed control explaining that this value changes
  **how JobApplicator budgets prompt size**, and does **not** necessarily change
  the running model server's context window — the server keeps its own context
  unless configured separately (e.g. Ollama `num_ctx`).
- Add an optional Ollama `num_ctx` control:
  - Bind it to the `num_ctx` settings field added in task 126 (load from
    `LocalLlmSettings`, send via `LocalLlmSettingsUpdate`).
  - Show it only when the selected provider is `ollama` (it has no effect for
    OpenAI-compatible endpoints), with helper text that it sets the Ollama
    server's running context length.
  - Treat an empty value as "unset" (`null`).
- Surface server-context verification from the connection test:
  - Extend the test-connection types/call to read
    `server_reported_context_tokens`, `context_verified`, and `context_warning`,
    and pass the current `num_ctx` edit as the override.
  - After a successful test, when `context_verified` is true and a
    server-reported context is present, show it (e.g. "Server-reported context:
    N tokens"). When `context_verified` is false, show the `context_warning`.
- Warn for OpenAI-compatible endpoints: when the selected provider is
  `openai_compatible`, show a static note that JobApplicator cannot verify the
  server's real context window, so the configured budget is an assumption. (The
  connection-test warning from task 127 is the dynamic counterpart; this static
  note covers the pre-test state.)
- Add/extend tests in `frontend/src/test/localLlmSettings.test.tsx` for: the
  renamed label, the `num_ctx` control appearing only for Ollama, the
  server-reported-context display on a verified test, and the
  OpenAI-compatible "cannot verify" warning.

## Allowed files

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/api/index.ts`
- `frontend/src/api/types.ts`
- `frontend/src/styles.css`
- `frontend/src/test/localLlmSettings.test.tsx`
- `frontend/src/test/settingsPage.test.tsx`
- `agent_tasks/128-clarify-context-budget-settings-ui.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (backend behavior is tasks 126 and 127)
- `docs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Any backend change (config persistence, request plumbing, detection, manifest)
  — those are tasks 126 and 127, and this task assumes their fields exist.
- Auto-applying a detected server context to the budget; detection is display
  only and the user keeps control of the budget value.
- Restyling the rest of the Settings page beyond what these controls need.

## Acceptance criteria

- The local-LLM card labels the context-budget control "JobApplicator context
  budget" (not "Context window tokens") with helper text clarifying it changes
  JobApplicator budgeting, not the server's running context.
- An optional Ollama `num_ctx` control appears only for the Ollama provider,
  binds to the `num_ctx` setting, and treats empty as unset.
- A successful connection test shows the server-reported context when verified,
  and shows the warning when it cannot be verified.
- An OpenAI-compatible selection shows a "cannot verify server context" note.
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Clarify context budget label and surface server context in Settings
```

Do not push.
