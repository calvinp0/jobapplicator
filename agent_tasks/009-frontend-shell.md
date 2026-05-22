# Task 009: Frontend Shell

## Goal

Scaffold the local frontend cockpit: a Vite + React + TypeScript app with
routing, a layout, an API client targeting the local FastAPI backend, and
empty placeholder routes for the screens that later tasks will fill in.

This task is scaffolding. It must not implement the job capture flow or
resume approval UI (those are task 010 and a later task).

## Background

Read:

- `docs/product_requirements.md` (MMVP workflow)
- `docs/architecture.md` (components)
- `agent_tasks/002-backend-models-and-capture-api.md` (endpoint shape)
- `backend/app/main.py` (existing backend, read-only)

## Scope

Under `frontend/`:

- initialize a Vite React + TypeScript project (`package.json`,
  `vite.config.ts`, `tsconfig.json`, `index.html`)
- add a router (React Router) with these placeholder routes:
  - `/captures` (pending captures awaiting confirmation)
  - `/jobs` (confirmed jobs)
  - `/runs` (Claude runs)
  - `/applications` (application tracker)
  - `/settings` (master resume, evidence bank selection)
- a simple shared layout (sidebar nav + main content area) — minimal CSS;
  no design system dependency required
- an `api/` module with a typed fetch client targeting
  `http://127.0.0.1:8000` (overridable via `VITE_API_BASE`) and stub
  functions for the endpoints the placeholder pages will eventually use
- vitest set up with one smoke test per route confirming it renders
- README under `frontend/README.md` explaining `npm install`,
  `npm run dev`, `npm test`, `npm run build`

## Allowed files

- `frontend/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed)

## Forbidden files

- `backend/**`
- `extension/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/**`
- Other `agent_tasks/*.md`

## Out of scope

- Implementing the job capture confirmation flow (task 010).
- Implementing resume review/approval UI.
- Authentication, multi-user support, or remote deployment.
- Design system, theming beyond minimal CSS.
- State management libraries beyond what React provides built-in (only
  add one if a later task clearly needs it — it doesn't yet).

## Acceptance criteria

- `npm run build` succeeds with no TypeScript errors.
- `npm test` passes (one smoke test per route).
- Each route renders a placeholder component with a clear "not yet
  implemented" message and the route name.
- The API client compiles and points at the local backend by default.
- No backend, extension, or docs files are touched.

## Verification

Run from `frontend/`:

```bash
npm install
npm test
npm run build
```

## Git commit message

```text
Add frontend shell
```

Do not push.
