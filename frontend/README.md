# jobapply frontend

Local cockpit for the jobapply backend. Vite + React + TypeScript shell with
placeholder routes that later tasks will fill in.

## Prerequisites

- Node.js 20+
- The backend running locally on `http://127.0.0.1:8000` (see `backend/`).

## Install

```bash
npm install
```

## Develop

```bash
npm run dev
```

Vite serves the app on `http://127.0.0.1:5173`.

Set `VITE_API_BASE` to point the API client at a non-default backend:

```bash
VITE_API_BASE=http://127.0.0.1:9000 npm run dev
```

## Test

```bash
npm test
```

Runs Vitest in a single pass. The smoke suite mounts each route and asserts
the placeholder renders.

## Build

```bash
npm run build
```

Type-checks the project (`tsc -b`) and emits a production bundle to `dist/`.

## Layout

- `src/App.tsx` — top-level router.
- `src/layout/Layout.tsx` — sidebar + content shell.
- `src/pages/` — one placeholder component per route.
- `src/api/` — typed fetch client and stub functions for the backend
  endpoints declared in `agent_tasks/002-backend-models-and-capture-api.md`.

## Out of scope (here)

This task only scaffolds the shell. The job capture confirmation flow,
resume approval UI, run status views, and application tracker live in
later tasks.
