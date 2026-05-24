# Task 046: Runtime prompt consumes revision feedback

Task ID: `046-runtime-prompt-revision-feedback`

## Goal

Update the resume-tailoring runtime prompt so that when the new
revision-feedback input file is present, the worker uses it to guide
the rewrite while still respecting ADR-004's evidence constraints.

## Background

Read first:

- `docs/adr/008-revision-feedback-flow.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/contracts/claude_run_directory.md` (post task 043)
- `runtime_prompts/resume_tailoring.md`

The runtime prompt is the worker's instruction file. After this change
it must:

- Read the revision-feedback input file when it exists.
- Treat the file as user-supplied steering, not as new evidence.
- Still refuse to add claims that are not supported by master resume,
  evidence bank, or project notes — even if the feedback asks for them.
- Reflect any rejected feedback items in the claim audit so the user
  can see what was and was not honored.

## Scope

- Update `runtime_prompts/resume_tailoring.md` to:
  - List the revision-feedback file in the read-inputs section.
  - Add behavior rules: when present, use feedback to guide rewrites;
    when absent, behave exactly as before.
  - Re-state the ADR-004 evidence constraint as overriding feedback.
  - Require the claim audit to record honored vs. rejected feedback
    items.
- Do not change first-draft behavior when the file is absent. The
  prompt must remain backward-compatible for runs that have no
  revision feedback.

## Allowed files

```
runtime_prompts/resume_tailoring.md
agent_tasks/046-runtime-prompt-revision-feedback.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/**
frontend/**
extension/**
candidate_context/**
runs/**
docs/**
runtime_prompts/*.md
```

The catch-all `runtime_prompts/*.md` is forbidden except the one file
in "Allowed files" above (`resume_tailoring.md`). Do not create new
prompt files in this task.

## Out of scope

- Adding new prompt files (defer to a later task if needed).
- Backend or contract changes (covered by tasks 043–045).
- Frontend wiring (task 039).

## Acceptance criteria

- `runtime_prompts/resume_tailoring.md` references the revision-feedback
  input file by the filename fixed in ADR-008 / task 043.
- The prompt explicitly says feedback cannot override evidence rules
  (cites ADR-004 by id).
- The prompt requires honored/rejected feedback to be reflected in the
  claim audit.
- No other file is modified.

## Verification

```bash
ls runtime_prompts/
grep -q "revision_feedback" runtime_prompts/resume_tailoring.md
grep -q "ADR-004" runtime_prompts/resume_tailoring.md
```

## Git instructions

Commit locally on the task branch with the message:

```
Update tailoring prompt to consume revision feedback
```

Do not push.
