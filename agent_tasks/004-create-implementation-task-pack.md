# Task 004: Create Implementation Task Pack

## Goal

Create the next implementation task pack for the job application cockpit.

This task should generate multiple scoped agent task files and update `agent_tasks/queue.yaml` so future work can run through `scripts/agentctl.sh`.

Do not implement product features in this task.

## Background

Read:

- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/contracts/claude_run_directory.md`
- `docs/contracts/agent_orchestration.md`
- `docs/adr/*.md`
- `runtime_prompts/resume_tailoring.md`
- `agent_tasks/queue.yaml`

## Scope

Create these task files:

```text
agent_tasks/005-extension-capture.md
agent_tasks/006-run-directory-writer.md
agent_tasks/007-claude-code-worker.md
agent_tasks/008-resume-version-import.md
agent_tasks/009-frontend-shell.md
agent_tasks/010-frontend-job-capture-flow.md
agent_tasks/011-eval-harness.md
```

Update:

```text
agent_tasks/queue.yaml
```

so these tasks are listed with:

- id
- title
- file
- branch
- worktree
- status
- depends_on
- verification
- allowed_paths

## Task Design Rules

Each generated task must include:

- Goal
- Background docs
- Scope
- Allowed files
- Forbidden files
- Out of scope
- Acceptance criteria
- Verification commands
- Git commit message

Each task must be small enough for one agent run.

Each task must avoid touching unrelated folders.

## Required Dependency Plan

Use this dependency structure:

```text
005-extension-capture
  depends on: 002-backend-models, 003-agent-orchestration

006-run-directory-writer
  depends on: 002-backend-models, 003-agent-orchestration

007-claude-code-worker
  depends on: 006-run-directory-writer

008-resume-version-import
  depends on: 007-claude-code-worker

009-frontend-shell
  depends on: 003-agent-orchestration

010-frontend-job-capture-flow
  depends on: 005-extension-capture, 009-frontend-shell

011-eval-harness
  depends on: 006-run-directory-writer
```

## Parallelization Notes

Mark these as `ready` if dependencies are already done:

```text
005-extension-capture
006-run-directory-writer
009-frontend-shell
```

These can run in parallel because they should mostly touch separate paths:

```text
extension/**
backend/**
frontend/**
```

Mark later tasks as `blocked` or `planned`.

## Out of Scope

Do not implement backend logic.

Do not implement extension logic.

Do not implement frontend UI.

Do not invoke Claude Code.

Do not run product tests unless needed.

## Verification

Run:

```bash
scripts/agentctl.sh list
scripts/agentctl.sh status
```

Also inspect:

```bash
ls agent_tasks/
```

## Git

After changes:

1. Stage all files.
2. Commit locally with:

```text
Add implementation task pack
```

Do not push.
