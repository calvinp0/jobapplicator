# 149 — Fail thinking-only schema calls and emit a model-suitability warning

## Goal

Stop a local LLM call from being treated as a usable structured result when the
model produced reasoning but **no answer**. For schema-required preflight tasks,
a reply whose content is empty after thinking is stripped must be classified as a
failure with a clear, specific reason — not the generic "schema validation
failed" that hides *why* it failed. When thinking was detected but content is
missing, the diagnostic store and the call result must carry a model-suitability
warning so the operator knows to switch models or lower the reasoning mode. This
covers the goal items *do not mark a request succeeded if content is empty for
schema-required tasks*, *warn "model is emitting thinking; use a non-thinking
model or lower reasoning mode"*, and *add a model suitability warning when
thinking is detected but content is missing*.

## Background

Read these before changing anything:

- `agent_tasks/148-local-llm-diagnostic-stream-accuracy.md` — the immediately
  preceding task; it adds the separate thinking/content counters and the
  thinking-detected/content-detected signals this task relies on. This task
  builds on those fields.
- `docs/adr/009-llm-provider-selection.md` — local LLM is opt-in for low-risk
  tasks; failures must fall back to the deterministic extractor, never crash a
  run. Preserve that.
- `docs/llm_providers.md` — the **Schema validation and fallback** and
  **Reasoning control (`thinking_mode`)** sections.
- `backend/app/local_llm.py` — `chat_json` (around lines 2056–2139): note it
  already strips thinking before parsing and already performs **one** repair
  retry with the validation `reason` fed back via `_repair_prompt`. Also note
  `strip_thinking`, `validate_json_payload`, `LLMCallResult` (fields `ok`,
  `schema_valid`, `thinking_returned`, `error`), and the diagnostic-store calls.
- `backend/app/local_llm_diagnostics.py` — `LocalLLMDiagnosticRecord`
  (`thinking_detected`, `content_detected`, `fallback_reason`, `error`), and
  `add_event`.
- `backend/tests/test_local_llm.py` — existing schema-validation / repair tests.

Note: the one-retry-with-validation-feedback behaviour the goal asks for already
exists in `chat_json`; do **not** add a second retry. This task only sharpens the
*classification* of an empty/thinking-only reply and adds the suitability
warning.

## Scope

- In `chat_json`, after stripping thinking, detect the case where the cleaned
  content is empty (or whitespace-only) while the raw reply carried thinking
  (`thinking_returned` / structured `message.thinking`). For that case:
  - Set `schema_valid = False` and set a specific `error` such as
    `"model emitted reasoning but no content; use a non-thinking model or lower the reasoning mode"`.
    Do not let this path return a result a caller would treat as a successful
    structured answer.
  - Apply the same classification to the post-repair result when the repaired
    reply is also thinking-only.
- Add a stable, human-readable warning constant for this condition (e.g.
  `THINKING_WITHOUT_CONTENT_WARNING`) and reuse it for both the result `error`
  text and the diagnostic event message so the wording is consistent.
- Record the warning on the diagnostic record when a request ends with
  `thinking_detected` true and `content_detected` false: emit a timeline event
  with the warning text and set the record's `fallback_reason` / `error` to the
  same suitability message (no raw thinking text).
- Keep the failure non-raising: an empty/thinking-only reply yields a non-valid
  `LLMCallResult` that the preflight pipeline already falls back on; verify the
  fallback path still triggers (do not change preflight here — only assert via a
  `local_llm` unit test that `schema_valid` is `False` and the error is the
  suitability message).
- Update `docs/llm_providers.md` to document that a schema-required call with no
  content after stripping thinking is a failure with the suitability warning, and
  that the warning is surfaced on both the call result and the diagnostic record.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/local_llm_diagnostics.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/149-local-llm-empty-content-suitability-warning.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (preflight wiring/manifest is out of scope here)
- `backend/app/routers/**`, `backend/app/schemas.py`, `backend/app/settings.py`
- `frontend/**` (surfacing the warning in the UI is task 152)
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`

## Out of scope

- Adding a second schema retry (one already exists; do not add more).
- Per-task JSON schema examples in the prompt (task 150).
- The Settings reasoning-mode control (task 151) or any monitor UI (task 152).
- Changing the deterministic fallback logic in `preflight.py`.

## Acceptance criteria

- A schema-required `chat_json` reply that is thinking-only (empty content after
  stripping) returns `schema_valid = False` with the specific suitability error,
  not a generic "schema validation failed".
- The same holds when the repair attempt is also thinking-only.
- The diagnostic record for a request that detected thinking but no content
  carries the suitability warning (timeline event + `fallback_reason`/`error`),
  with no raw thinking text.
- A normal reply with real content is unaffected (`schema_valid = True`).
- The failure path never raises.
- `docs/llm_providers.md` documents the empty-content failure and the warning.
- Tests in `backend/tests/test_local_llm.py` cover: thinking-only first reply,
  thinking-only repair reply, the warning on the diagnostic record, and the
  unchanged happy path.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Fail thinking-only schema calls and emit a model-suitability warning
```

Do not push.
