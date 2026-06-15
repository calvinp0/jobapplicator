---
task_id: "147-add-local-llm-admin-monitor"
verdict: "REQUEST_CHANGES"
reviewed_at: "2026-06-15T11:28:37Z"
reviewer: "codex"
---

# Review: 147-add-local-llm-admin-monitor

## Verdict

REQUEST_CHANGES

## Required fixes

- Implement the required `stalled_generation_timeout` classification. The code declares `TIMEOUT_STALLED = "stalled_generation_timeout"` in `backend/app/local_llm_diagnostics.py`, but no runtime path emits it. `backend/app/local_llm.py:1790` classifies all post-chunk timeouts as `generation_timeout`, and the streaming loop at `backend/app/local_llm.py:1919` has no configurable idle timeout. Add a real idle/stall timeout path and test it.
- Align provider degraded state with the task requirement for repeated timeout failures. `_ProviderHealth.record_timeout()` marks the provider degraded after the first timeout (`backend/app/preflight.py:326`), and `diagnostics_store.mark_provider_degraded(...)` is called immediately with `timeout_failures=1` (`backend/app/preflight.py:803`). The task asks to mark degraded after repeated local LLM timeouts and to show "local provider marked degraded after 2 timeout failures"; gate the degraded state/diagnostic on the threshold or otherwise make the UI/store semantics match the requirement.

## Optional notes

- `git diff --check main...HEAD` reports trailing blank lines at EOF in `backend/app/local_llm_diagnostics.py` and `backend/app/routers/admin_local_llm.py`.

## Evidence checked

- Inspected commit `8248a36 Add local LLM admin monitor`, one commit beyond `main` (`326563a`).
- Inspected changed files under `backend/app/local_llm.py`, `backend/app/local_llm_diagnostics.py`, `backend/app/preflight.py`, `backend/app/provider_trace.py`, `backend/app/routers/admin_local_llm.py`, `backend/tests/test_local_llm.py`, `frontend/src/pages/LocalLlmMonitorPage.tsx`, `frontend/src/components/ProviderTrace.tsx`, `frontend/src/api/*`, `frontend/src/App.tsx`, `frontend/src/layout/Layout.tsx`, and `frontend/src/test/localLlmMonitor.test.tsx`.
- Checked relevant ADRs: `docs/adr/001-local-first-mvp.md` and `docs/adr/009-llm-provider-selection.md`.
- Ran `npm test -- --run src/test/localLlmMonitor.test.tsx` from `frontend`: passed, 3 tests.
- Ran `git diff --check main...HEAD`: failed only on trailing blank line at EOF reports.
- Attempted `python -m pytest backend/tests/test_local_llm.py`; it collected 107 tests but did not complete within the review window and produced no further progress output.

## Scope / allowed-path check

The task file did not include an explicit `allowed_paths` list. The commit changes are within the expected task surface: local LLM backend/client/diagnostics, admin router wiring, preflight/provider trace integration, frontend route/page/API/types/styles, and local LLM monitor tests. I did not see Gmail, browser extension capture, packaging, deployment, or unrelated domain changes. The changes appear consistent with ADR-001 local-first constraints and ADR-009's boundary that hosted/API local LLM work remains separate from the CLI auto-tailoring provider registry.

## Verification status

The task worktree was clean before writing this review artifact, and the branch contains one task commit beyond `main`. Targeted frontend verification passed. Backend targeted verification was attempted but did not complete during this review session. Full task verification (`backend/tests`, frontend build, full frontend tests) was not run here. The implementation is close, but the missing stalled-stream timeout classification and premature degraded-state semantics violate stated acceptance criteria.
