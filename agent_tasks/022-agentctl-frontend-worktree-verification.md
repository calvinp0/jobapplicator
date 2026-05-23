# Task 022: Make Frontend Worktree Verification Reliable

## Goal

Fix recurring frontend-task friction in `scripts/agentctl.sh`.

Frontend task worktrees often do not have `node_modules`, so verification fails with `vitest: command not found` unless `npm install` has already been run manually.

The harness should make frontend verification reliable without requiring manual `cd frontend && npm install` in every new worktree.

This task improves orchestration reliability. Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
agent_tasks/queue.yaml
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

Observed failure:

```text
cd frontend && npm test
sh: line 1: vitest: command not found
```

The worktree had no `frontend/node_modules`.

## Scope

Update:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

Optionally update:

```text
agent_tasks/queue.yaml
```

## Required Behavior

Before running verification commands for a task, the harness should prepare known package workspaces when needed.

For frontend tasks:

If the task verification includes commands under `frontend`, and `frontend/node_modules/.bin/vitest` does not exist, run:

```bash
cd frontend && npm install
```

before running verification.

For extension tasks:

If the task verification includes commands under `extension`, and `extension/node_modules` does not exist, run:

```bash
cd extension && npm install
```

before running verification.

## Safety Rules

Do not run `npm install` globally.

Do not run `npm install` unless the task verification clearly references `frontend` or `extension`.

Do not modify product code.

Do not modify backend, frontend, extension source files.

Do not push.

## Verification Command Normalization

Ensure generated/planned task guidance says verification commands must be repo-root-relative:

Frontend:

```bash
cd frontend && npm test
cd frontend && npm run build
```

Extension:

```bash
cd extension && npm test
cd extension && npm run build
```

Backend:

```bash
pytest
```

## Acceptance Criteria

- `complete <frontend-task>` should not fail merely because `frontend/node_modules` is missing.
- The harness prepares `frontend` before frontend verification.
- The harness prepares `extension` before extension verification.
- Existing commands still work:
  - status
  - ready
  - run
  - review
  - complete
  - plan --help

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh complete 018 --dry-run
```

If feasible, test against an existing frontend worktree by temporarily moving `frontend/node_modules` aside inside the worktree, running dry-run or verification-prep code, then restoring it. Do not leave the worktree broken.

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Make frontend worktree verification reliable
```

Do not push.
