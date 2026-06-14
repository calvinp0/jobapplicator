# 141 — Default temperature 0 and JSON-only instruction for structured local calls

## Goal

Make the local LLM subsystem more deterministic and parse-friendly for the
structured (JSON) calls the preflight pipeline relies on. Structured calls
(`chat_json`, i.e. any call with a JSON `response_format`) should request
temperature `0` by default and reinforce a "return JSON only, no reasoning"
instruction, regardless of the configured `thinking_mode`. This addresses two
goal items: *default temperature 0 for JSON preflight* and *add prompt
instruction: return JSON only, no reasoning*.

## Background

Read first:

- `docs/llm_providers.md` — the **Reasoning control (`thinking_mode`)** section
  and the **Schema validation and fallback** section; note that today the
  JSON-only system prompt is injected *only* under `no_thinking` for the
  OpenAI-compatible provider.
- `backend/app/local_llm.py` — `LocalLLMClient.chat` (both provider branches),
  `chat_json`, `_NO_THINKING_SYSTEM_PROMPT`, and the `response_format` handling.
- `backend/tests/test_local_llm.py` — existing client payload tests.

Context: a low temperature makes strict-JSON output and instruction-following
more reliable for small local models, and an explicit JSON-only instruction
reduces the prose-before-JSON failures that the task-131 strip step currently
has to clean up after the fact.

## Scope

- Add a module-level constant for the default structured-call temperature
  (`DEFAULT_JSON_TEMPERATURE = 0`).
- In `LocalLLMClient.chat`, when a JSON `response_format` is requested, send the
  temperature to the server using each provider's native field:
  - Ollama-native branch: `options.temperature` (added to the same `options`
    block as `num_ctx` / `num_predict`).
  - OpenAI-compatible branch: top-level `temperature`.
  - For non-structured calls (e.g. `test_connection`), preserve current
    behaviour — do **not** force a temperature.
- Reinforce the JSON-only instruction for **every** structured call, not just
  `no_thinking`: ensure a concise "reply with ONLY the requested JSON object, no
  reasoning/prose/markdown" instruction is present for both providers when a JSON
  `response_format` is set. Keep the existing `no_thinking` behaviour intact and
  avoid duplicating the instruction when it is already injected.
- Keep the temperature value internal to the client for this pass (a hardcoded
  default for structured calls); do not add a new persisted setting.
- Update `docs/llm_providers.md` to document that structured local calls request
  temperature `0` and always include a JSON-only instruction.

## Allowed files

- `backend/app/local_llm.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/141-local-llm-json-temperature-and-prompt.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/schemas.py`, `backend/app/routers/settings.py` (no new setting in
  this task)
- `backend/app/preflight.py` (preflight prompt wiring is task 145)
- `frontend/**`, `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`

## Out of scope

- A user-configurable temperature setting (note as a possible follow-up).
- Changing non-structured / free-text call behaviour.
- Preflight prompt assembly (task 145).

## Acceptance criteria

- Structured calls (`response_format` set) send temperature `0` via
  `options.temperature` (Ollama-native) or top-level `temperature`
  (OpenAI-compatible).
- Non-structured calls (e.g. `test_connection`) send no temperature.
- A JSON-only instruction is present for structured calls under all
  `thinking_mode` values for both providers, without being duplicated when the
  `no_thinking` injection already adds it.
- The temperature is added to the same `options` block as any `num_ctx`/
  `num_predict` for the Ollama-native provider (one block, not several).
- `docs/llm_providers.md` reflects the new defaults.
- Tests in `backend/tests/test_local_llm.py` assert the temperature and
  JSON-only instruction for both providers, and assert non-structured calls are
  unaffected.

## Verification

- `python -m pytest backend/tests/test_local_llm.py`
- `python -m pytest`

## Git instructions

Commit with the message:

```
Default temperature 0 and JSON-only instruction for structured local calls
```

Do not push.
