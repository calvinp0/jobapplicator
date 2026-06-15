# 148 — Make local LLM streaming diagnostics accurate: once-only events and separate thinking/content counts

## Goal

Fix two diagnostic-accuracy defects in the local LLM streaming path so the admin
monitor (task 147) tells the truth about what a reasoning model did. First, the
`"thinking stream started"` event is currently emitted on *every* streamed chunk
that carries a `message.thinking` value, so a reasoning run floods the timeline
with duplicate lines. It must fire at most once per request. Second, the
diagnostic record only counts *content* characters (`approx_generated_chars`);
thinking output is detected but never counted, so the operator cannot tell how
much of a stalled/timed-out run was thinking versus answer. Track thinking
chars/tokens separately from content chars/tokens, and emit a distinct
`"content stream started"` lifecycle event (the mirror of the thinking one) plus
a clear final-metrics event, so content-started, thinking-started, and the final
generation metrics are observable as separate timeline entries.

## Background

Read these before changing anything:

- `agent_tasks/147-add-local-llm-admin-monitor.md` — the diagnostic store,
  streaming model, event timeline, and the privacy rule (counts yes, raw text
  no). This task tightens that monitor; do not change its product shape.
- `docs/adr/009-llm-provider-selection.md` — local LLM is experimental and
  opt-in for low-risk tasks; do not change that policy.
- `docs/llm_providers.md` — the local LLM diagnostics / monitor section.
- `backend/app/local_llm.py` — the Ollama streaming loop (around lines
  2007–2054): the per-chunk handler that splits `message.thinking` /
  `message.content`, calls `diagnostics_store.add_event(...)` for
  `"first chunk received"` and `"thinking stream started"`, and calls
  `diagnostics_store.update_chunk(thinking_chars=..., content_chars=...)`.
- `backend/app/local_llm_diagnostics.py` — `LocalLLMDiagnosticRecord`
  (fields `approx_generated_chars`, `approx_generated_tokens`,
  `thinking_detected`, `content_detected`, `time_to_first_content_ms`),
  `update_chunk`, `update_final_metrics`, and `add_event`.
- `backend/tests/test_local_llm.py` — existing streaming/diagnostic tests.

## Scope

- In `backend/app/local_llm.py`'s Ollama streaming loop, guard the
  `"thinking stream started"` event with a local boolean so it fires at most
  once per request (the first chunk whose `message.thinking` is non-empty).
  Add a symmetric `"content stream started"` event that fires at most once, on
  the first chunk whose `message.content` is non-empty.
- Keep emitting `"first chunk received"` exactly as today (do not regress it).
- Add separate thinking counters to `LocalLLMDiagnosticRecord` in
  `backend/app/local_llm_diagnostics.py`:
  - `approx_thinking_chars: int = 0`
  - `approx_thinking_tokens: int = 0`
  Keep the existing `approx_generated_chars` / `approx_generated_tokens` as the
  **content** counters (do not fold thinking into them). Update `update_chunk`
  to accumulate `thinking_chars` into the new thinking counters using the same
  ~chars/4 token estimate the content path uses, while leaving the content
  accumulation unchanged.
- Emit a distinct final-metrics timeline event (e.g. `"final metrics recorded"`)
  when `update_final_metrics` records server-reported counts on a `done` chunk,
  so the timeline shows content-started, thinking-started, and final metrics as
  three separate entries. Keep the message free of raw thinking/content text.
- Update `docs/llm_providers.md` to document that thinking and content
  characters/tokens are tracked separately and that thinking-started,
  content-started, and final-metrics are distinct one-shot timeline events.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/local_llm_diagnostics.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/148-local-llm-diagnostic-stream-accuracy.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (per-task prompts/schema examples are task 150)
- `backend/app/routers/**`, `backend/app/schemas.py`, `backend/app/settings.py`
- `frontend/**` (the monitor UI display is task 152)
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`

## Out of scope

- Treating empty/thinking-only content as a failure or emitting the
  model-suitability warning (task 149).
- Any frontend rendering of the new counters/events (task 152).
- Adding per-task JSON schema examples (task 150).
- Persisting raw thinking or content text (still forbidden by default — task
  147 already established this; do not change it).

## Acceptance criteria

- `"thinking stream started"` is emitted at most once per request even when many
  chunks carry `message.thinking`.
- `"content stream started"` is emitted at most once per request, on the first
  non-empty `message.content` chunk.
- `LocalLLMDiagnosticRecord` carries `approx_thinking_chars` and
  `approx_thinking_tokens`, accumulated only from thinking chunks and kept
  separate from the content counters.
- A distinct final-metrics timeline event is emitted when final server metrics
  are recorded.
- No raw thinking or content text is added to any event message.
- `docs/llm_providers.md` documents the separate counters and the three distinct
  one-shot events.
- Tests in `backend/tests/test_local_llm.py` cover: multiple thinking chunks →
  one thinking-started event; first content chunk → one content-started event;
  separate thinking vs content char/token accumulation; final-metrics event.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Make local LLM streaming diagnostics accurate: once-only events and separate thinking/content counts
```

Do not push.
