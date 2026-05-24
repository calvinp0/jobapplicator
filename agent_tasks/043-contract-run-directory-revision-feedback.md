# Task 043: Run-directory contract update for revision feedback

Task ID: `043-contract-run-directory-revision-feedback`

## Goal

Update `docs/contracts/claude_run_directory.md` to add the revision-
feedback input file decided in ADR-008, so the backend (task 044/045)
and the runtime prompt (task 046) have one authoritative description of
where feedback lives inside `runs/<run_id>/input/`.

## Background

Read first:

- `docs/adr/008-revision-feedback-flow.md` (lands in task 042)
- `docs/contracts/claude_run_directory.md`
- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`

The ADR fixes the input filename and the high-level structure the file
must carry. This task is the contract change that makes that visible to
every downstream task.

## Scope

- Add an "Input Files" subsection for the revision-feedback input file
  (filename per ADR-008, typically `revision_feedback.md`). Describe:
  - when the file is present (only for follow-up tailoring runs;
    absent for first-draft runs)
  - what fields/sections it carries
  - the explicit statement that the worker must still respect ADR-004
    (evidence constraints) and ADR-002 (no DB writes)
- Add the new filename to both the "Claude Code Read Boundary" list
  and the description of `runs/<run_id>/input/` at the top of the
  document.
- Cross-reference ADR-008 by id from the new subsection.

## Allowed files

```
docs/contracts/claude_run_directory.md
agent_tasks/043-contract-run-directory-revision-feedback.md
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
docs/adr/**
docs/contracts/agent_orchestration.md
docs/contracts/browser_extension_capture.md
docs/product_requirements.md
docs/architecture.md
```

## Out of scope

- Changing other input files described in the contract.
- Modifying the write boundary (no output file changes here).
- Backend or frontend implementation.

## Acceptance criteria

- `docs/contracts/claude_run_directory.md` has a new input-file
  subsection for revision feedback that matches ADR-008.
- The new filename appears in the directory-tree sample at the top of
  the document.
- The new filename appears in the "Claude Code Read Boundary" list.
- The new subsection cites ADR-008 and ADR-004 by id.
- No other contract file is modified.

## Verification

```bash
ls docs/contracts/
grep -q "revision_feedback" docs/contracts/claude_run_directory.md
grep -q "ADR-008" docs/contracts/claude_run_directory.md
```

## Git instructions

Commit locally on the task branch with the message:

```
Add revision feedback input to run directory contract
```

Do not push.
