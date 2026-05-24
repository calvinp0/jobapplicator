# Task 047: Unblock and refine frontend revision-feedback task (039)

Task ID: `047-unblock-frontend-revision-feedback`

## Goal

Now that the ADR (task 042), contract (043), backend model (044),
backend API (045), and runtime prompt (046) for revision feedback have
landed, refine task 039's task file with the concrete API/UX details
and move its queue status from `blocked` to `planned` so it can be
promoted to `ready` when its dependencies complete.

## Background

Read first:

- `docs/adr/008-revision-feedback-flow.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/039-revision-feedback-flow.md`
- `backend/app/routers/` (the new endpoint from task 045)
- `backend/app/schemas.py` (the new schemas from task 044)

Task 039 was filed as a placeholder before the backend design existed.
Its scope, acceptance criteria, and allowed files were preliminary.
This task tightens 039 against the now-decided design so the next
operator who runs it does not have to re-derive the API shape.

## Scope

- Update `agent_tasks/039-revision-feedback-flow.md`:
  - Replace the "BLOCKED — design first" note with a pointer to
    ADR-008 and the new backend endpoint.
  - Replace the preliminary scope with the concrete frontend behavior
    that calls the task-045 endpoint.
  - Tighten `Allowed files` and `Acceptance criteria` so they reflect
    the final API shape (request body fields, response routing
    target, error surface via `extractApiDetail`).
  - Remove the "Blocker" section.
- Update `agent_tasks/queue.yaml` for task 039:
  - Change `status` from `blocked` to `planned`.
  - Update `depends_on` to include `045-backend-revision-feedback-api`
    (and any other newly-needed predecessor from this pack) so
    `complete` will promote 039 to `ready` only once the backend
    surface has landed.

This task is itself planning work, not product code; it only edits
agent task files.

## Allowed files

```
agent_tasks/039-revision-feedback-flow.md
agent_tasks/047-unblock-frontend-revision-feedback.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/**
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/**
scripts/**
```

## Out of scope

- Implementing the frontend revision-feedback UI (that is task 039
  when it is eventually dispatched).
- Adding new backend or runtime-prompt behavior.
- Re-opening decisions fixed in ADR-008.

## Acceptance criteria

- `agent_tasks/039-revision-feedback-flow.md` no longer contains a
  "Blocker" section and no longer says "do not run yet".
- The file's `Scope` and `Acceptance criteria` reference the
  ADR-008 endpoint and the response routing target.
- `agent_tasks/queue.yaml` shows task 039 with `status: planned` and
  `depends_on` including `045-backend-revision-feedback-api`.
- No file outside `agent_tasks/` is modified.

## Verification

```bash
scripts/agentctl.sh list
scripts/agentctl.sh status
grep -q "ADR-008" agent_tasks/039-revision-feedback-flow.md
```

## Git instructions

Commit locally on the task branch with the message:

```
Unblock frontend revision feedback task
```

Do not push.
