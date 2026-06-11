# Task 134: Surface "local LLM attempted but fell back" clearly in the run-trace UI

## Goal

Make it obvious in the run-trace UI when a run *tried* the experimental local LLM
and then fell back to the deterministic extractor (or to Claude Code). Task 133
emits a stable "Local LLM attempted but fell back: <reason>" marker into the
run's progress/log stream and records the attempted/degraded/skipped state in the
preflight manifest, but the frontend currently renders those lines as plain log
text — the operator has to read carefully to notice the fallback. This
frontend-only task detects that signal in the run trace and renders it as a
clear, styled notice (not just a raw log line), so a degraded local run is
visible at a glance. It consumes the backend signal added in task 133 and does
not change any backend behavior.

## Background

Read these before changing anything:

- `docs/llm_providers.md` — Preflight section; the UI wording should match the
  "Local LLM attempted but fell back" phrasing the backend emits.
- `docs/adr/009-llm-provider-selection.md` — local LLM is experimental and
  opt-in; keep the framing consistent (a fallback is expected, not an error).
- `agent_tasks/133-log-preflight-local-llm-performance-and-fallback.md` — defines
  the stable marker wording emitted to the run trace and the manifest
  attempted/degraded/skipped fields this task surfaces.
- `frontend/src/pages/RunDetailPage.tsx` — the run-trace rendering (progress
  events + raw `run.log` lines; see the progress/log handling around lines
  330–530).
- `frontend/src/api/types.ts` and `frontend/src/api/index.ts` — the run, run
  log, and progress types/calls the page consumes.
- `frontend/src/test/runDetailLog.test.tsx`,
  `frontend/src/test/runDetailProgress.test.tsx`, and
  `frontend/src/test/runDetailPage.test.tsx` — existing run-trace coverage to
  extend.

## Scope

- Detect the task-132 marker in the run trace the page already loads (the
  progress/log lines). Match the stable wording the backend emits ("Local LLM
  attempted but fell back: <reason>"). Prefer matching a stable prefix over an
  exact string so the trailing reason can vary.
- Render a clear, styled notice in `RunDetailPage.tsx` when the marker is present
  — e.g. an informational banner/badge near the run status that reads "Local LLM
  attempted but fell back" and shows the reason. It must read as an expected,
  non-fatal outcome (info/neutral styling), not an error, consistent with the
  advisory nature of preflight.
- Keep the raw run-trace log/progress rendering unchanged; the notice is an
  additional, more prominent surface, not a replacement.
- Do not invent new backend fields or call new endpoints: rely only on the
  run-trace data the page already fetches. If a small additive type is needed to
  read an existing field, add it to `frontend/src/api/types.ts` without changing
  request behavior.
- Add minimal styling in `frontend/src/styles.css` for the notice (reuse existing
  banner/badge classes where they exist).
- Extend the run-detail tests to cover: the notice appears when the marker line
  is in the trace, the reason text is shown, and the notice is absent on a clean
  run (no marker).

## Allowed files

- `frontend/src/pages/RunDetailPage.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/api/index.ts`
- `frontend/src/styles.css`
- `frontend/src/test/runDetailLog.test.tsx`
- `frontend/src/test/runDetailProgress.test.tsx`
- `frontend/src/test/runDetailPage.test.tsx`
- `agent_tasks/134-surface-local-llm-fallback-in-run-trace.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (the run-trace signal and manifest are tasks 132/133)
- `docs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `runtime_prompts/**`, `candidate_context/**`, `runs/**`, `extension/**`

## Out of scope

- Any backend change (signal emission, manifest fields, degraded/skip behavior)
  — those are tasks 132 and 133; this task assumes the marker exists.
- A Settings UI control for timeout or reasoning mode (those settings are owned
  by tasks 130/131; their UI is not part of this task).
- Rendering the full preflight manifest or a performance table in the UI;
  surfacing the single "attempted but fell back" notice is the scope.
- Restyling the rest of the run-trace page beyond the new notice.

## Acceptance criteria

- When the run trace contains the task-132 marker, `RunDetailPage` shows a clear,
  styled, non-error notice reading "Local LLM attempted but fell back" with the
  reason; a test asserts this.
- When the run trace has no marker (clean run), the notice is absent; a test
  asserts this.
- The raw log/progress rendering is unchanged.
- No new backend endpoints or request behavior are introduced.
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Surface local LLM attempted-but-fell-back in the run-trace UI
```

Do not push.
