# 142 — Ignore Ollama structured `message.thinking` and don't persist it by default

## Goal

Handle the Ollama-native **structured** reasoning field, `message.thinking`,
which is distinct from the inline `<think>...</think>` text that task 131
already strips. When an Ollama model returns reasoning in `message.thinking`,
the subsystem must (a) never fold it into the parsed/surfaced content, (b) record
that thinking *was* returned so it can be surfaced later, and (c) not persist the
reasoning text by default. This addresses the goal items *strip/ignore Ollama
message.thinking* and *do not persist thinking by default*.

## Background

Read first:

- `docs/llm_providers.md` — the **Reasoning control (`thinking_mode`)** section
  (task 131): `strip_thinking` (default), `hide_thinking`, `no_thinking`, and the
  rule that stripping is the reliable mechanism.
- `backend/app/local_llm.py` — `_extract_content` (currently reads only
  `choices[0].message.content` and Ollama `message.content`), `strip_thinking`,
  `LLMCallResult`, and `chat` / `chat_json`.
- `backend/tests/test_local_llm.py` — existing thinking/strip tests.

Context: Ollama's native `/api/chat` returns a separate `message.thinking`
string for reasoning models (when reasoning is on). The current `_extract_content`
ignores it for *content*, but the result object has no signal that thinking was
returned, and nothing guarantees the reasoning text stays out of persisted
artifacts. The goal wants an explicit, observable contract.

## Scope

- Add a `thinking_returned: bool` field (default `False`) to `LLMCallResult`.
- When parsing an Ollama-native response, detect a non-empty
  `message.thinking` and set `thinking_returned = True`. Also treat a stripped
  inline `<think>` block (content that changed after `strip_thinking`) as
  thinking-returned, so the flag is meaningful for both reasoning shapes.
- Ensure `message.thinking` is **never** concatenated into the surfaced
  `content` or the parsed JSON.
- Do not persist the reasoning text by default: the surfaced `content` carried
  forward to artifacts/logs must not contain the structured thinking, for every
  `thinking_mode`. (The existing `hide_thinking` behaviour for inline `<think>`
  is preserved; this task extends the "don't persist reasoning" guarantee to the
  structured field by simply never copying it into `content`.)
- Update `docs/llm_providers.md` to document that the Ollama-native
  `message.thinking` field is ignored for parsing, never persisted, and that a
  `thinking_returned` signal is exposed on the call result.

## Allowed files

- `backend/app/local_llm.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/142-local-llm-ollama-thinking-field.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (manifest surfacing of `thinking_returned` is task 145)
- `frontend/**` (the UI badge is task 146)
- `backend/app/schemas.py`, `backend/app/routers/settings.py`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`

## Out of scope

- Surfacing `thinking_returned` in the preflight manifest (task 145) or the UI
  (task 146).
- Adding an option to *keep* reasoning text (persisting thinking is explicitly
  not wanted by default).
- Changing the `thinking_mode` settings surface.

## Acceptance criteria

- `LLMCallResult` exposes `thinking_returned` (default `False`).
- An Ollama-native response with a non-empty `message.thinking` sets
  `thinking_returned = True` and leaves `content` free of the reasoning text.
- A response whose content carried an inline `<think>` block also reports
  `thinking_returned = True` after stripping.
- A response with no reasoning reports `thinking_returned = False` and is parsed
  exactly as before.
- The structured thinking text never appears in surfaced `content` or parsed
  JSON under any `thinking_mode`.
- `docs/llm_providers.md` documents the behaviour.
- Tests in `backend/tests/test_local_llm.py` cover the structured-thinking case,
  the inline-`<think>` case, and the no-thinking case.

## Verification

- `python -m pytest backend/tests/test_local_llm.py`
- `python -m pytest`

## Git instructions

Commit with the message:

```
Ignore Ollama structured message.thinking and expose thinking_returned signal
```

Do not push.
