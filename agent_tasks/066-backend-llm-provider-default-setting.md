# Task 066: Backend Default LLM Provider Setting

## Goal

Persist a user-editable default LLM provider so the run-creation flow can
fall back to it when the caller does not specify one. Expose `GET` and
`PUT` endpoints so the Settings page (task 067) can read and update it.

## Background

Read first:

- `docs/adr/009-llm-provider-selection.md`
- `agent_tasks/065-backend-llm-provider-registry.md`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/main.py`
- `backend/app/routers/**`
- `backend/tests/test_api.py`

The provider registry already exists (task 065). What is missing is a
single piece of app-wide state — "which provider id is the default?" —
and the endpoints to surface it.

## Scope

1. Add a minimal app-settings store. Two acceptable shapes:
   - a key/value `app_settings` table with `(key TEXT PK, value TEXT,
     updated_at TIMESTAMP)`, or
   - a dedicated `app_settings` row in an existing settings module if
     one already exists in the codebase.

   Pick the one that matches the project's existing pattern. The store
   must round-trip through SQLite without alembic.

2. Add a helper API in a module under `backend/app/` (for example,
   `backend/app/settings.py` if no such module exists) with two
   functions: `get_default_llm_provider() -> str` and
   `set_default_llm_provider(provider_id: str) -> str`. The setter
   validates against the provider registry from task 065 and raises a
   clear error for unknown ids. The getter returns `"claude_code"`
   when no setting row is present.

3. Wire the run-creation route to call `get_default_llm_provider()`
   when the request omits `llm_provider`.

4. Add two endpoints:
   - `GET /api/settings/llm-provider` — returns
     `{"default_provider": "<id>", "available": [...]}` where
     `available` is the same shape returned by `GET /api/llm-providers`.
   - `PUT /api/settings/llm-provider` — takes `{"default_provider":
     "<id>"}`, validates against the registry, persists, and returns
     the new setting. Returns 400 with a clear message for unknown ids.

5. Tests:
   - The getter returns `claude_code` on a fresh DB.
   - The setter persists a new value and the getter reads it back.
   - Setting an unknown provider raises and the row is unchanged.
   - `GET /api/settings/llm-provider` returns the current value and the
     list of available providers.
   - `PUT /api/settings/llm-provider` accepts a valid id and rejects an
     unknown one with 400.
   - A run created without `llm_provider` uses the persisted default,
     not the hardcoded fallback.

## Allowed files

- `backend/app/settings.py` (new; or extend the existing equivalent)
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/db.py`
- `backend/app/main.py`
- `backend/app/routers/**`
- `backend/tests/**`
- `agent_tasks/066-backend-llm-provider-default-setting.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `frontend/**`
- `extension/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `runs/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`

## Out of scope

- Frontend Settings page changes (task 067).
- Per-job provider override UI (task 068).
- General-purpose feature-flag system or arbitrary key/value config UI.
  Only the LLM-provider setting is exposed.

## Acceptance criteria

- An app-settings store persists `default_llm_provider`.
- `GET /api/settings/llm-provider` returns the current default and the
  list of available providers.
- `PUT /api/settings/llm-provider` validates against the registry and
  persists.
- The run-creation route falls back to the persisted default when
  `llm_provider` is omitted.
- All `pytest` tests pass.

## Verification

```bash
pytest backend/tests/test_api.py
pytest
```

## Git instructions

After verification passes:

1. Stage the changed backend files, the new settings module, the new
   tests, and this task file.
2. Commit locally with the message:

```text
Add backend default LLM provider setting
```

Do not push.
