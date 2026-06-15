# 152 — Show thinking vs content lifecycle and the suitability warning in the Local LLM Monitor

## Goal

Surface the sharper backend diagnostics (tasks 148 and 149) in the Local LLM
Monitor (task 147) so the operator can read, at a glance, what a reasoning model
actually did. Display content-started, thinking-started, and final-metrics as
distinct lifecycle states; show thinking characters/tokens separately from
content characters/tokens; and prominently surface the model-suitability warning
("model is emitting thinking; use a non-thinking model or lower reasoning mode")
when a request detected thinking but produced no content. This completes the goal
items *show content started / thinking started / final metrics separately* and
the UI half of the model-suitability warning.

## Background

Read these before changing anything:

- `agent_tasks/147-add-local-llm-admin-monitor.md` — the monitor's sections
  (active request, request options, live generation, server/context, event
  timeline) and the privacy rule: counts and detected-flags yes, raw text no.
- `agent_tasks/148-local-llm-diagnostic-stream-accuracy.md` — adds
  `approx_thinking_chars` / `approx_thinking_tokens` to the diagnostic record,
  makes thinking-started/content-started one-shot events, and adds a
  final-metrics event.
- `agent_tasks/149-local-llm-empty-content-suitability-warning.md` — adds the
  suitability warning to the diagnostic record (`fallback_reason`/`error` and a
  timeline event) when thinking is detected but content is missing.
- `frontend/src/pages/LocalLlmMonitorPage.tsx` — the existing monitor page and
  how it renders the snapshot.
- `frontend/src/api/types.ts` — `LocalLlmDiagnosticRecord`,
  `LocalLlmDiagnosticEvent`, `LocalLlmDiagnosticsSnapshot` (add the new
  thinking-count fields).
- `frontend/src/api/index.ts` — how the diagnostics snapshot is fetched/typed.
- `frontend/src/test/localLlmMonitor.test.tsx` — existing monitor tests
  (including the assertion that raw reasoning text is never rendered).

## Scope

- Extend the diagnostics types in `frontend/src/api/types.ts` to include the new
  record fields from task 148 (`approx_thinking_chars`, `approx_thinking_tokens`)
  alongside the existing content counters; thread through `index.ts` if needed.
- In `LocalLlmMonitorPage.tsx`'s Live generation section, show thinking
  characters/tokens and content characters/tokens as **separate** labelled rows
  (do not merge them), plus the existing thinking-detected / content-detected
  indicators.
- Present the lifecycle as distinct states derived from the record/timeline:
  content started, thinking started, and final metrics recorded — so the
  operator can tell which phase a request reached. The event timeline already
  carries the one-shot events from task 148; render them clearly and de-duped.
- When a request carries the suitability warning (thinking detected, content
  missing — task 149), show it prominently in the active/recent request view
  (e.g. a warning badge with the message), not buried in the timeline.
- Never render raw thinking or content text — only counts, flags, durations, and
  the sanitized warning message. Keep the existing "no raw reasoning" test
  passing and add coverage for the new rows/warning.
- Reuse existing monitor styles; add minimal CSS only if necessary.

## Allowed files

- `frontend/src/pages/LocalLlmMonitorPage.tsx`
- `frontend/src/api/types.ts`
- `frontend/src/api/index.ts`
- `frontend/src/styles.css`
- `frontend/src/test/localLlmMonitor.test.tsx`
- `agent_tasks/152-frontend-monitor-thinking-content-lifecycle.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**` (the diagnostic fields/events come from tasks 148/149)
- `frontend/src/pages/SettingsPage.tsx` (the reasoning-mode control is task 151)
- Other `frontend/src/pages/**` and `frontend/src/test/**` files not listed above
- `extension/**`, `runtime_prompts/**`, `candidate_context/**`, `runs/**`
- `docs/adr/**`, `docs/product_requirements.md`, `docs/architecture.md`
- `docs/contracts/**`

## Out of scope

- Any backend change (tasks 148/149 own the fields and events).
- The reasoning-mode Settings control (task 151).
- Changing the run-trace/RunDetail provider trace display.
- Persisting or rendering raw thinking/content text (still forbidden).

## Acceptance criteria

- The Live generation section shows thinking chars/tokens and content
  chars/tokens as separate labelled rows.
- The monitor distinguishes content-started, thinking-started, and
  final-metrics-recorded states, and the timeline shows those one-shot events
  without duplication.
- A request with thinking detected but no content shows the suitability warning
  prominently (badge/message), using the sanitized backend message.
- No raw thinking or content text is rendered (existing privacy test still
  passes).
- A request with normal content and no warning renders cleanly with the new
  rows.
- Types in `frontend/src/api/types.ts` cover the new thinking-count fields.
- Tests in `frontend/src/test/localLlmMonitor.test.tsx` cover the separate
  thinking/content rows, the lifecycle states, and the suitability warning
  (present and absent).
- `cd frontend && npm test -- --run` and `cd frontend && npm run build` pass.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Show thinking vs content lifecycle and suitability warning in the Local LLM Monitor
```

Do not push.
