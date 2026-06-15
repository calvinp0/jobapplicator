# 150 — Add per-task JSON schema examples to local LLM preflight prompts

## Goal

Improve the JSON-generation accuracy of local models by showing each preflight
task a concrete example of the exact JSON shape it must return. Today the local
calls request a JSON object with required fields but rely on a generic
"reply with JSON only" instruction; small local models frequently emit the right
keys with the wrong nesting, or prose around the object. Adding a compact,
per-task example payload to the prompt (a one-shot schema example) gives the
model a target to copy and reduces schema-validation failures and the wasteful
fallback they trigger. This covers the goal item *add per-task JSON schema
examples*.

## Background

Read these before changing anything:

- `docs/adr/009-llm-provider-selection.md` — local LLM is opt-in for low-risk
  tasks; the preflight pipeline must still fall back deterministically when a
  local call is unusable. Do not change that policy.
- `docs/llm_providers.md` — the **Preflight analysis pipeline** section and the
  per-task list (`job_summary`, `ats_keywords`, `role_requirements`,
  `evidence_gap_plan`, and any others present in code).
- `backend/app/preflight.py` — where each task's system/user messages and
  `required_fields` are assembled before `client.chat_json(...)`. This is the
  only place the per-task example belongs.
- `backend/app/local_llm.py` — `chat_json`, `validate_json_payload`, and the
  existing repair retry (so the example reinforces, not duplicates, the repair
  feedback added earlier).
- `backend/tests/test_preflight.py` — existing per-task prompt/manifest tests.

## Scope

- For each local preflight task, add a compact, valid JSON **example** of the
  expected output to the prompt that task sends, alongside the existing
  required-fields instruction. Keep the example minimal (illustrative values,
  not real candidate data) and consistent with the task's `required_fields`.
- Define the examples in one obvious place (e.g. a per-task mapping keyed by the
  same task identifier the pipeline already uses) so they stay in sync with the
  required-fields definitions and are easy to unit-test. Avoid duplicating the
  example string across call sites.
- Ensure the example is included only for the structured local-LLM prompt path;
  do not alter the deterministic extractor inputs or the Claude `auto` tailoring
  prompts.
- Keep the prompt additive and within the existing context-budget accounting —
  the example must be small enough not to blow the input budget the pipeline
  already estimates; confirm the estimate still includes the added prompt text.
- Update `docs/llm_providers.md` to note that each local preflight task includes
  a one-shot JSON schema example in its prompt.

## Allowed files

- `backend/app/preflight.py`
- `backend/tests/**`
- `docs/llm_providers.md`
- `agent_tasks/150-preflight-per-task-json-schema-examples.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/app/local_llm.py` (schema validation/retry already exist; do not
  change them here)
- `backend/app/routers/**`, `backend/app/schemas.py`, `backend/app/settings.py`
- `frontend/**`, `runtime_prompts/**`, `candidate_context/**`, `runs/**`,
  `extension/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`

## Out of scope

- Changing `required_fields` definitions or the JSON validation rules.
- The diagnostic counters/events (tasks 148/149) or any UI (tasks 151/152).
- Adding examples to the Claude `auto` tailoring prompts.

## Acceptance criteria

- Each local preflight task's prompt includes a compact, valid JSON example that
  matches its `required_fields`.
- The examples live in a single, testable definition kept in sync with the
  required-fields, not duplicated across call sites.
- Only the local-LLM structured path is affected; deterministic extraction and
  the Claude `auto` flow are unchanged.
- The added prompt text is accounted for in the existing input-budget estimate.
- `docs/llm_providers.md` documents the per-task examples.
- Tests in `backend/tests/test_preflight.py` assert each task's prompt carries an
  example whose parsed shape contains the task's required fields.
- `python -m pytest` passes.

## Verification

```bash
python -m pytest backend/tests/test_preflight.py
python -m pytest
```

## Git instructions

Commit message:

```
Add per-task JSON schema examples to local LLM preflight prompts
```

Do not push.
