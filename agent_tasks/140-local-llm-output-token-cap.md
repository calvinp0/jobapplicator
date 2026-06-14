# 140 — Cap local LLM output tokens (num_predict / max_tokens)

## Goal

Give the experimental local LLM subsystem a configurable per-call output-token
cap so a local model cannot run away generating unbounded text before the
deterministic fallback kicks in. The cap is sent to the server as the
provider-native field — `options.num_predict` for the Ollama-native provider and
`max_tokens` for the OpenAI-compatible provider — so generation is bounded at
the source, not just trimmed after the fact. This directly addresses two goal
items: *add per-task max output tokens / Ollama num_predict* and *cap local LLM
output before fallback*.

## Background

Read first:

- `docs/llm_providers.md` — the local LLM subsystem, config fields, and the
  Ollama-native vs OpenAI-compatible endpoint split.
- `docs/contracts/agent_orchestration.md` — the section "Runtime LLM providers
  are a separate concern" (this is the experimental local subsystem, never the
  `auto` tailoring flow).
- `docs/adr/009-llm-provider-selection.md` — why local/HTTP providers are scoped
  out of the high-risk CLI registry.
- `backend/app/local_llm.py` — `LocalLLMConfig`, `get_config`, `save_config`,
  `get_settings_view`, and `LocalLLMClient.chat` (the payload-building branches
  for Ollama-native `/api/chat` and OpenAI-compatible `/chat/completions`).
- `backend/app/schemas.py` and `backend/app/routers/settings.py` — how
  `reserved_output_tokens` and `num_ctx` are validated and persisted (mirror that
  pattern).
- `backend/tests/test_local_llm.py` — existing config/persistence/client tests.

Note: `reserved_output_tokens` is JobApplicator's *prompt-budget* headroom; it is
**not** an instruction to the server. This task adds a separate, optional output
cap that is actually sent to the model server.

## Scope

- Add an optional `max_output_tokens` field to `LocalLLMConfig` (default `None`
  meaning "do not send an output cap; leave the server at its own default"),
  following the exact optional-integer pattern already used for `num_ctx`
  (load coercion in `get_config`, validation in `save_config`, echo in
  `get_settings_view`, round-trip in the returned config object).
- Validate it as a positive integer when present; reject `<= 0` with a clear
  `LocalLLMValidationError`, mirroring `num_ctx` validation.
- In `LocalLLMClient.chat`, when `max_output_tokens` is set:
  - Ollama-native branch: add `num_predict` to the `options` block (creating the
    block if needed, alongside any `num_ctx`).
  - OpenAI-compatible branch: add `max_tokens` to the request payload.
  - When `max_output_tokens` is `None`, send nothing (unchanged behaviour).
- Thread the field through `save_config`'s signature and the settings request
  schema / router so it persists and round-trips.
- Update `docs/llm_providers.md`: document the new **Max output tokens** field,
  that it maps to `num_predict` (Ollama-native) / `max_tokens`
  (OpenAI-compatible), that it is optional and defaults to the server's own
  limit, and that it bounds generation before the deterministic fallback.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/schemas.py`
- `backend/app/routers/settings.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/140-local-llm-output-token-cap.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (wiring the cap into preflight is task 145)
- `frontend/**` (the Settings field is task 146)
- `backend/app/llm_providers.py`, `backend/app/claude_worker.py`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`

## Out of scope

- Per-task-type (job_summary vs ats_keywords) distinct output caps — a single
  config-level cap is sufficient for this pass; defer differentiation.
- Wiring the cap into the preflight pipeline or the manifest (task 145).
- Any frontend Settings control (task 146).
- A temperature setting (task 141).

## Acceptance criteria

- `LocalLLMConfig` has an optional `max_output_tokens` (default `None`) that
  persists and round-trips through `save_config` / `get_config` /
  `get_settings_view`.
- A non-positive `max_output_tokens` is rejected with `LocalLLMValidationError`;
  `None` is accepted and means "send no cap".
- With a cap set, the Ollama-native request carries `options.num_predict` and the
  OpenAI-compatible request carries `max_tokens`; with no cap, neither is sent.
- Setting a cap alongside `num_ctx` produces a single `options` block containing
  both keys for the Ollama-native provider.
- `docs/llm_providers.md` documents the field and its provider-native mapping.
- New/updated tests in `backend/tests/test_local_llm.py` cover persistence,
  validation, and both provider payload shapes (cap set and unset).

## Verification

- `python -m pytest backend/tests/test_local_llm.py`
- `python -m pytest`

## Git instructions

Commit with the message:

```
Add configurable local LLM output-token cap (num_predict/max_tokens)
```

Do not push.
