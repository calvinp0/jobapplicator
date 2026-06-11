# Task 131: Add local LLM reasoning controls and strip thinking text before JSON parsing

## Goal

Stop "thinking" / reasoning output from corrupting the local LLM's structured
JSON replies. Reasoning-capable local models (DeepSeek-R1, Qwen3, and other
Ollama models) emit chain-of-thought — often wrapped in `<think>...</think>` or
similar markers — *before* the JSON object the preflight pipeline expects. That
prose makes `validate_json_payload` fail, which wastes the (slow) local call and
forces a deterministic fallback even when the model produced a usable answer.
This task adds an opt-in reasoning control (no-thinking / hide-thinking /
strip-thinking) to the local LLM config and strips any thinking text from the
model's content **before** JSON parsing, so a reasoning model's structured
answer is recovered instead of discarded. It builds on the timeout work in task
130.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — local LLM is experimental and
  opt-in for low-risk tasks; do not change that policy.
- `docs/llm_providers.md` — Configuration section and the
  Ollama / OpenAI-compatible setup notes.
- `agent_tasks/123-add-experimental-local-llm-provider.md` — introduced
  `backend/app/local_llm.py` and `LocalLLMConfig`.
- `agent_tasks/130-add-local-llm-task-timeout-and-ollama-default.md` — the
  immediately preceding task in this pack (timeout defaults).
- `backend/app/local_llm.py` — `LocalLLMConfig`, `get_config`, `save_config`,
  `get_settings_view`, `validate_json_payload` (around lines 485–503),
  `_extract_content` (around lines 578–586), `LocalLLMClient.chat` /
  `chat_json` (around lines 608–764), and how the outbound `payload` is
  assembled before `_post_json`.
- `backend/app/schemas.py` and `backend/app/routers/settings.py` — the
  `GET`/`PUT /settings/local-llm` read/update shapes.

## Scope

- Add a reasoning-control setting to `LocalLLMConfig` in
  `backend/app/local_llm.py`. Use a single, well-documented field — a
  `thinking_mode` enum is preferred — covering at least these behaviors:
  - **no-thinking**: ask the model not to produce reasoning at all (best effort).
    For the Ollama-native provider, send the documented native option that
    disables reasoning (e.g. `think: false`); for OpenAI-compatible servers,
    reinforce "reply with ONLY the JSON object, no reasoning" in the system
    prompt. Document in a code comment that disabling is best-effort and the
    strip step below is the reliable backstop.
  - **strip-thinking** (the safe default): allow the model to think but remove
    the thinking text from the content before parsing.
  - **hide-thinking**: keep the model's reasoning out of the persisted artifacts
    and logs (treated like strip for parsing purposes, but the intent is that
    thinking is never surfaced downstream).
  - Default the field to the strip/hide-safe behavior so existing users benefit
    without reconfiguring. Parse it in `get_config` (tolerate missing/unknown →
    default) and validate it in `save_config` (reject an unrecognized value with
    `LocalLLMValidationError`).
- Add a thinking-stripping helper and call it on the model content **before**
  `validate_json_payload` runs (and before the repair-retry parse), in
  `LocalLLMClient`'s JSON path:
  - Remove `<think>...</think>` blocks (and the common `<thinking>...</thinking>`
    variant), case-insensitively, including multi-line spans.
  - After stripping, if the remaining text still contains a JSON object, parse
    that; tolerate leading/trailing whitespace. Keep the existing repair-retry
    behavior for genuinely malformed replies.
  - The helper must be pure and unit-testable in isolation.
- Wire the no-thinking request option only where it applies: for
  `provider == "ollama"` send the native disable-reasoning option; never send a
  provider-specific reasoning flag to an OpenAI-compatible endpoint.
- Surface the reasoning-control field through the persisted-settings read/update
  path (`backend/app/schemas.py`, `backend/app/routers/settings.py`) so it
  round-trips through `GET`/`PUT /settings/local-llm`.
- Update `docs/llm_providers.md` Configuration section to document the reasoning
  control, its modes, the default, and that stripping is the reliable mechanism
  while disabling reasoning is best-effort.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/schemas.py`
- `backend/app/routers/settings.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/131-add-local-llm-reasoning-controls.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (preflight wiring is tasks 132/133)
- `frontend/**` (UI is task 134)
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Adding a Settings UI control for the reasoning mode (task 134).
- Introducing any reasoning / sequential-thinking *step* into the preflight
  pipeline — the goal is to remove thinking from replies, never to add it
  (the explicit "do not add sequential thinking for preflight" guardrail lives
  in task 132).
- Manifest / run-trace logging changes (task 133).
- Changing the over-budget handling or the task-risk policy.

## Acceptance criteria

- `LocalLLMConfig` has a reasoning-control field with a safe default, parsed by
  `get_config` and validated by `save_config` (unrecognized value rejected).
- A pure thinking-stripping helper removes `<think>`/`<thinking>` blocks
  (case-insensitive, multi-line); unit tests cover content with reasoning before
  a JSON object, nested/whitespace cases, and content with no thinking markers
  (unchanged).
- A local reply that wraps valid JSON in a `<think>` block now parses
  successfully instead of falling back; a test asserts the JSON is recovered.
- For `provider == "ollama"` with no-thinking selected, the outbound request
  carries the native disable-reasoning option; for `openai_compatible` it never
  carries a provider-specific reasoning flag; tests assert both.
- The reasoning-control field round-trips through `GET`/`PUT /settings/local-llm`.
- `docs/llm_providers.md` documents the reasoning control and its modes.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_local_llm.py
python -m pytest
```

## Git instructions

Commit message:

```
Add local LLM reasoning controls and strip thinking before JSON parsing
```

Do not push.
