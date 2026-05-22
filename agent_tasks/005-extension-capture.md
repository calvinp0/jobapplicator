# Task 005: Browser Extension Current-Page Capture

## Goal

Implement the browser extension capture provider that lets the user trigger
a current-page job capture from a LinkedIn job posting and send the
normalized payload to the local backend's `POST /captures` endpoint.

This task implements one capture provider only. It must not change backend
models, schemas, or the capture endpoint contract.

## Background

Read:

- `docs/product_requirements.md`
- `docs/architecture.md` (capture provider architecture, browser assistance boundary)
- `docs/adr/005-browser-assisted-current-page-capture.md`
- `docs/adr/007-capture-provider-architecture.md`
- `agent_tasks/002-backend-models-and-capture-api.md` (capture payload shape)
- `backend/app/routers/captures.py` (endpoint contract, read-only)
- `backend/app/schemas.py` (normalized payload fields, read-only)

## Scope

Create a Manifest V3 browser extension under `extension/` with:

- `manifest.json` declaring required permissions (activeTab, host permission
  for LinkedIn job pages only) and the action button
- a background service worker that handles the action click
- a content script that parses the current LinkedIn job page and extracts:
  `company`, `title`, `location`, `description_text`, `application_method`,
  `external_url`, `external_job_id`, `raw_text`
- a small popup or action handler that POSTs the normalized payload to the
  local backend (default `http://127.0.0.1:8000/captures`)
- a parser module separated from the extension shim so it can be unit-tested
  in Node against a saved HTML fixture
- a build setup (`package.json`, bundler config of your choice — esbuild or
  vite preferred for simplicity) and unit tests (vitest or jest)
- a fixtures directory with one captured LinkedIn job page HTML snippet
  used by the parser tests

Also create:

- `docs/contracts/browser_extension_capture.md` describing the extension's
  permissions, allowed/forbidden behaviors, payload shape, and how to load
  it as an unpacked extension for local development.

## Allowed files

- `extension/**`
- `docs/contracts/browser_extension_capture.md`
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed; do
  not edit by default)

## Forbidden files

- `backend/**`
- `frontend/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- Any other `agent_tasks/*.md`

## Out of scope

- Modifying the backend capture endpoint or payload schema.
- Adding capture providers other than LinkedIn current-page capture.
- Auto-clicking Easy Apply, auto-attaching files, auto-submitting, or any
  background crawling.
- Publishing or packaging the extension for distribution.
- Frontend UI for reviewing captures (that is task 010).

## Acceptance criteria

- `manifest.json` requests the minimum permissions needed and is scoped to
  LinkedIn job URLs.
- The parser module is pure (no DOM globals at import time) so it can be
  tested in Node by passing in a parsed document or HTML string.
- Parser unit tests cover: a full job-page fixture, a missing-field case
  (e.g. no location), and a non-LinkedIn page rejection.
- The action handler POSTs a payload that matches the normalized capture
  fields defined by `backend/app/schemas.py`.
- The extension does no work without an explicit user click on the action.
- `npm test` and `npm run build` both pass.

## Verification

Run from `extension/`:

```bash
npm install
npm test
npm run build
```

## Git commit message

```text
Add browser extension current-page capture
```

Do not push.
