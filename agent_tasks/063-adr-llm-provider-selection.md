# Task 063: ADR for LLM Provider Selection

## Goal

Record the architectural decision to let the user choose which CLI-based LLM
worker runs the existing `auto` tailoring flow (Claude Code today; Codex CLI,
Gemini CLI, or future tools tomorrow). The decision is captured as a new ADR
so the backend and frontend tasks that follow have a single design document
to point at.

This task only writes the ADR. It does not implement provider abstraction,
add a database field, or change UI.

## Background

Read first:

- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/058-add-tailoring-method-model.md`
- `agent_tasks/062-add-frontend-tailoring-method-controls.md`

Context the ADR must reflect:

- `tailoring_method` already distinguishes `auto` from `word_handoff`. The
  new dimension is *which LLM CLI executes the `auto` flow*; it is
  orthogonal to `tailoring_method`.
- The worker-boundary rule from ADR-002 must continue to hold for every
  provider: the LLM may only read and write inside its run directory; the
  backend remains the source of truth.
- The run-directory contract in `docs/contracts/claude_run_directory.md`
  describes one set of expected outputs (`output/tailored_resume.docx`,
  `output/tailored_resume.md`, `output/change_log.md`, `output/claim_audit.md`).
  Each provider must satisfy that contract or its run fails validation.

## Scope

Add `docs/adr/009-llm-provider-selection.md` with the standard ADR
sections (Status, Context, Decision, Rationale, Consequences, Alternatives
Considered, Notes). The decision section should include, at minimum:

- The backend supports a configurable LLM provider for the `auto`
  tailoring flow. Initial providers: `claude_code` (default), `codex`,
  `gemini`. New providers may be added without changing the run-directory
  contract.
- A provider is identified by a stable string id, has a CLI binary
  (env-var overridable), and a non-interactive invocation that takes the
  prompt on stdin and writes outputs under `output/`.
- Each `ClaudeRun` persists the provider id used so the run record is
  self-describing.
- The user-facing default lives in app settings and is editable through
  the Settings page.
- The worker-boundary rule (ADR-002) and the evidence-constraint rule
  (ADR-004) apply identically to every provider — no provider may mutate
  the database, and no provider may invent unsupported claims.

The ADR should also note explicit non-goals:

- No hosted-API providers in this iteration (CLI-only).
- No provider-specific runtime prompts in this iteration; the existing
  `runtime_prompts/resume_tailoring.md` is shared.
- No fallback/cascade between providers if one fails — the run fails and
  the user retries with the chosen provider.

## Allowed files

- `docs/adr/009-llm-provider-selection.md`
- `agent_tasks/063-adr-llm-provider-selection.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `frontend/**`
- `extension/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `runs/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/adr/000-template.md` and any other existing ADR (do not edit them)

## Out of scope

- Implementing the provider registry, the API, or the UI.
- Renaming `ClaudeRun` or the `claude_worker` module.
- Adding hosted-API (non-CLI) providers.
- Adding provider-specific prompts.

## Acceptance criteria

- `docs/adr/009-llm-provider-selection.md` exists and follows the
  template structure used by ADR-002 and ADR-008.
- The ADR explicitly references ADR-002 (worker boundary) and ADR-004
  (evidence constraint) and states they apply to every provider.
- The ADR lists `claude_code`, `codex`, and `gemini` as the initial
  provider ids.
- The ADR lists the non-goals above.
- No other files are modified.

## Verification

```bash
test -f docs/adr/009-llm-provider-selection.md
grep -q "ADR-002" docs/adr/009-llm-provider-selection.md
grep -q "ADR-004" docs/adr/009-llm-provider-selection.md
grep -q "claude_code" docs/adr/009-llm-provider-selection.md
grep -q "codex" docs/adr/009-llm-provider-selection.md
grep -q "gemini" docs/adr/009-llm-provider-selection.md
```

## Git instructions

After verification passes:

1. Stage `docs/adr/009-llm-provider-selection.md` and
   `agent_tasks/063-adr-llm-provider-selection.md`.
2. Commit locally with the message:

```text
Add ADR-009 for LLM provider selection
```

Do not push.
