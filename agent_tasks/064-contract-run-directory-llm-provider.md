# Task 064: Add llm_provider to Run Directory Contract

## Goal

Update the run-directory contract so `runs/<run_id>/metadata.json` documents
an `llm_provider` field. This is the documentation half of the LLM-selection
work; the backend persistence and dispatch follow in task 065.

## Background

Read first:

- `docs/adr/009-llm-provider-selection.md` (added by task 063)
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/058-add-tailoring-method-model.md`
- `agent_tasks/063-adr-llm-provider-selection.md`

The existing contract already documents `tailoring_method`. The new
`llm_provider` field is orthogonal: it identifies which CLI tool ran the
`auto` flow. For `tailoring_method == word_handoff` the field is still
present but its value is descriptive (`claude_for_word`) — that detail
lives in task 065's backend implementation, but the contract must be
written in a way that does not contradict it.

## Scope

Edit `docs/contracts/claude_run_directory.md` so that:

- The Metadata section names `llm_provider` as a field on
  `metadata.json` alongside `tailoring_method` and `status`.
- An example metadata block shows `"llm_provider": "claude_code"` next
  to `"tailoring_method": "auto"`.
- A short list of currently recognized values is included:
  `claude_code`, `codex`, `gemini`. Note that `word_handoff` runs may
  use the sentinel `claude_for_word` so the field is never absent.
- The contract states that the provider id must be stable, lowercase,
  and snake_case, and that adding a new provider does not change the
  required output filenames under `output/`.
- A pointer to ADR-009 is added in the same place ADR-002 and ADR-008
  are referenced.

Do not change any other section of the contract.

## Allowed files

- `docs/contracts/claude_run_directory.md`
- `agent_tasks/064-contract-run-directory-llm-provider.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `frontend/**`
- `docs/adr/**`
- `runtime_prompts/**`
- `docs/product_requirements.md`
- `docs/architecture.md`

## Out of scope

- Renaming any existing field.
- Implementing the backend persistence.
- Defining provider-specific output files (the contract stays uniform).

## Acceptance criteria

- `docs/contracts/claude_run_directory.md` mentions `llm_provider` and
  shows it in the metadata example.
- It lists `claude_code`, `codex`, and `gemini` as recognized values.
- It cross-references ADR-009.
- No other files are changed.

## Verification

```bash
grep -q "llm_provider" docs/contracts/claude_run_directory.md
grep -q "claude_code" docs/contracts/claude_run_directory.md
grep -q "codex" docs/contracts/claude_run_directory.md
grep -q "gemini" docs/contracts/claude_run_directory.md
grep -q "ADR-009" docs/contracts/claude_run_directory.md
```

## Git instructions

After verification passes:

1. Stage `docs/contracts/claude_run_directory.md` and
   `agent_tasks/064-contract-run-directory-llm-provider.md`.
2. Commit locally with the message:

```text
Document llm_provider in run directory contract
```

Do not push.
