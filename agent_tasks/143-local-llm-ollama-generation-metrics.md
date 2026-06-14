# 143 — Capture Ollama generation metrics and tokens/sec on the call result

## Goal

Record the generation telemetry that Ollama's native `/api/chat` response
already returns — `prompt_eval_count`, `eval_count`, `total_duration`, and
`eval_duration` — and derive a tokens-per-second figure from them, attaching all
of it to the local LLM call result so it can be logged and surfaced downstream.
This addresses the goal items *log prompt_eval_count, eval_count, total_duration,
eval_duration from Ollama response* and the data half of *show tokens/sec and
whether thinking was returned*.

## Background

Read first:

- `docs/llm_providers.md` — the **Schema validation and fallback** section (the
  single per-call log line) and the **Preflight analysis pipeline** section (the
  per-task `performance` object: `prompt_token_estimate`, `elapsed_ms`,
  `effective_timeout_seconds` from task 133).
- `backend/app/local_llm.py` — `LLMCallResult`, `LocalLLMClient.chat` (where the
  response `body` is parsed and `latency_ms` is computed), `_extract_content`,
  and `_log_call`.
- `backend/tests/test_local_llm.py` — existing client result tests.

Context: Ollama returns `prompt_eval_count` (input tokens), `eval_count` (output
tokens), `total_duration` and `eval_duration` (nanoseconds). These are
server-reported and authoritative, unlike the estimated `prompt_token_estimate`
already recorded. Tokens/sec is `eval_count / (eval_duration / 1e9)`. The
OpenAI-compatible surface does not return these, so the metrics are best-effort
and Ollama-native only.

## Scope

- Add a structured `generation_metrics` holder to `LLMCallResult` (e.g. an
  optional dict or a small dataclass) with: `prompt_eval_count`, `eval_count`,
  `total_duration_ms`, `eval_duration_ms`, and a derived `tokens_per_second`
  (rounded sensibly; `None` when `eval_duration` is zero/missing to avoid divide
  errors).
- Add a pure, unit-testable helper that extracts these from an Ollama-native
  response body and computes tokens/sec, converting the nanosecond durations to
  milliseconds. Missing or malformed fields degrade to `None`, never raise.
- Populate `generation_metrics` in `LocalLLMClient.chat` from a successful
  Ollama-native response; leave it `None`/empty for the OpenAI-compatible
  provider (no such fields).
- Extend `_log_call` (or its caller) to include tokens/sec and the output token
  count in the per-call log line when available, without breaking the existing
  log format for callers/tests that match on it (append fields rather than
  rewriting the existing ones).
- Update `docs/llm_providers.md` to document the captured Ollama metrics and the
  derived tokens/sec, noting they are Ollama-native only and best-effort.

## Allowed files

- `backend/app/local_llm.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/143-local-llm-ollama-generation-metrics.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/preflight.py` (writing metrics into the manifest is task 145)
- `frontend/**` (the UI display is task 146)
- `backend/app/schemas.py`, `backend/app/routers/settings.py`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`

## Out of scope

- Recording the metrics in the preflight manifest (task 145) or the UI (task 146).
- Any equivalent metrics for the OpenAI-compatible provider (it does not report
  them).
- Persisting metrics to a database table.

## Acceptance criteria

- `LLMCallResult` carries server-reported generation metrics for successful
  Ollama-native calls: `prompt_eval_count`, `eval_count`, `total_duration_ms`,
  `eval_duration_ms`, and a derived `tokens_per_second`.
- The extraction helper is pure and returns `None` fields (never raises) for
  missing/zero/malformed values, including a zero `eval_duration`.
- The OpenAI-compatible provider leaves the metrics unpopulated.
- The per-call log line includes tokens/sec and output tokens when available and
  does not break existing format expectations.
- `docs/llm_providers.md` documents the metrics and their Ollama-native,
  best-effort nature.
- Tests in `backend/tests/test_local_llm.py` cover extraction (full, partial,
  zero-duration, missing), the derived tokens/sec, and that OpenAI-compatible
  calls have no metrics.

## Verification

- `python -m pytest backend/tests/test_local_llm.py`
- `python -m pytest`

## Git instructions

Commit with the message:

```
Capture Ollama generation metrics and tokens/sec on the local call result
```

Do not push.
