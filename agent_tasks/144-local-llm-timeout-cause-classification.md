# 144 — Distinguish generation timeout from connection timeout

## Goal

When a local LLM call times out, tell the operator *why*: a **connection
timeout** (the server could not be reached within the timeout — connect/DNS
never completed) is a different problem from a **generation timeout** (the
server was reached and accepted the request, but generation did not finish in
time). Today both collapse to `endpoint_unavailable`, which mislabels a slow
model as an unreachable server. This addresses the goal item *mark timeout cause
as generation timeout vs connection timeout where possible*.

## Background

Read first:

- `docs/llm_providers.md` — the **Classified connection failures (task 136)**
  section and the `error_kind` taxonomy (`endpoint_unavailable`, `bad_url`,
  `model_not_installed`, `unexpected`, `none`).
- `backend/app/local_llm.py` — `classify_endpoint_error`, the
  `ENDPOINT_ERROR_*` constants, the `except urllib.error.URLError` /
  `except TimeoutError` branches in `LocalLLMClient.chat`, and `_probe_failure_message`.
- `backend/app/preflight.py` — `_is_timeout` (matches the documented
  `"timeout after Ns contacting ..."` error string; task 132 degradation logic
  depends on it).
- `backend/tests/test_local_llm.py` — existing error-classification tests.

Context: with `urllib`, a single `timeout=` bounds the whole request, so a
perfectly clean attribution is not always possible. Use the best available
signal — distinguish a timeout whose underlying reason is a connect failure
(`URLError` wrapping a connect-time `TimeoutError`/`ConnectionRefusedError`)
from a read/generation timeout (the request was sent and the server simply did
not finish). Where the layer genuinely cannot tell, prefer the
generation-timeout label only when the connection itself is known to have
succeeded; otherwise keep the existing unavailable classification. Be explicit
in the code comments about the limits of the attribution.

## Scope

- Add a new stable `error_kind` constant for a generation timeout (e.g.
  `ENDPOINT_ERROR_GENERATION_TIMEOUT = "generation_timeout"`). Keep a
  connection-timeout case mapped to the existing `endpoint_unavailable` (or a
  clearly-named connection-timeout constant if cleaner) — document the choice.
- In `LocalLLMClient.chat`, when a timeout is raised, classify it: a
  read/generation timeout (request was dispatched to a reachable server) yields
  the generation-timeout kind with a message like `generation timed out after Ns
  ...`; a connect-time timeout keeps the unavailable/connection-timeout kind.
- Keep the failure path non-raising and the result shape unchanged apart from
  `error` / `error_kind`.
- Preserve preflight's degradation logic: `_is_timeout` must still recognise both
  timeout causes as timeouts. Update `_is_timeout` (and/or the error-string
  contract it matches) so a generation timeout still counts toward the task-132
  degraded/skip thresholds. Update the `backend/tests/test_preflight.py`
  expectations if the error string changes.
- Extend `_probe_failure_message` / `diagnose_connection` so the connection-test
  diagnosis surfaces the generation-timeout case with a clear, distinct message.
- Update `docs/llm_providers.md` to add the generation-timeout kind to the
  taxonomy and explain the connection-vs-generation distinction and its limits.

## Allowed files

- `backend/app/local_llm.py`
- `backend/app/preflight.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/144-local-llm-timeout-cause-classification.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `frontend/**` (any UI treatment of the new kind is out of scope here)
- `backend/app/schemas.py`, `backend/app/routers/settings.py`
- `backend/app/claude_worker.py`, `backend/app/llm_providers.py`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`

## Out of scope

- Splitting the single `urllib` timeout into separate connect/read timeouts via
  a new HTTP stack — keep the stdlib client; classify from the best available
  signal only.
- Frontend display of the new `error_kind` (can be a later follow-up).
- Retrying generation timeouts.

## Acceptance criteria

- A new stable generation-timeout `error_kind` exists and is returned when a
  reachable server fails to finish generating in time.
- A connect-time timeout keeps the existing unavailable classification (not the
  generation-timeout kind).
- The failure path still never raises; only `error`/`error_kind` change.
- Preflight's `_is_timeout` still treats a generation timeout as a timeout, so
  task-132 degradation/skip behaviour is unchanged; `test_preflight.py` passes.
- `diagnose_connection` surfaces a clear, distinct message for the
  generation-timeout case.
- `docs/llm_providers.md` documents the new kind and the attribution limits.
- Tests in `backend/tests/test_local_llm.py` cover both timeout causes and the
  diagnosis message; `backend/tests/test_preflight.py` still passes.

## Verification

- `python -m pytest backend/tests/test_local_llm.py`
- `python -m pytest backend/tests/test_preflight.py`
- `python -m pytest`

## Git instructions

Commit with the message:

```
Classify local LLM generation timeout vs connection timeout
```

Do not push.
