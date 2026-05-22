# Task 003: Agent Orchestration Harness

## Goal

Add a lightweight agent orchestration harness so future implementation tasks can be run through isolated worktrees, task files, verification commands, and review steps.

This task improves the development workflow. It must not implement product features.

## Background

Read:

- `docs/product_requirements.md`
- `docs/architecture.md`
- `docs/adr/*.md`
- `agent_tasks/001-scaffold-project.md`
- `agent_tasks/002-backend-models-and-capture-api.md` if present

## Scope

Create:

```text
scripts/agentctl.sh
agent_tasks/queue.yaml
docs/contracts/agent_orchestration.md
```

Optionally create:

```text
scripts/README.md
```

## Required Behavior

The harness should support at least these commands:

```bash
scripts/agentctl.sh run <task-id>
scripts/agentctl.sh review <task-id>
scripts/agentctl.sh status
scripts/agentctl.sh list
```

The harness should read task metadata from:

```text
agent_tasks/queue.yaml
```

Each queued task should include:

```yaml
id:
title:
file:
branch:
worktree:
status:
depends_on:
verification:
allowed_paths:
```

## Orchestration Model

The harness should:

1. Check that `agent_tasks/queue.yaml` exists.
2. Resolve the requested task by ID.
3. Check that the task file exists.
4. Check dependency statuses.
5. Check that the current git worktree is clean before starting a new run.
6. Start Claude Code in an isolated worktree using the task's `worktree` value.
7. Pass the full task file content to Claude Code.
8. Ask Claude to:
   - read the referenced background docs
   - stay within scope
   - respect allowed paths
   - run verification
   - stage and commit changes
   - not push
9. Print recent commits and git status after the agent returns.

## Claude Command

Use Claude Code with `--worktree` where available.

The implementation should use a variable so the command can be overridden:

```bash
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
```

The implementation should support a permission mode environment variable:

```bash
CLAUDE_PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-acceptEdits}"
```

The run command may use:

```bash
"$CLAUDE_BIN" --worktree "$WORKTREE" --permission-mode "$CLAUDE_PERMISSION_MODE" -p "$PROMPT"
```

If the local Claude Code version does not support these flags, document the expected command and keep the script easy to adjust.

## Review Command

`review <task-id>` should start a review-oriented Claude prompt.

The review prompt should check:

- Did the implementation stay within task scope?
- Were allowed paths respected?
- Were ADRs respected?
- Were tests meaningful?
- Was anything overbuilt?
- Were unrelated files changed?
- Is the commit message appropriate?

The review command should not modify files by default.

Use:

```bash
CLAUDE_REVIEW_PERMISSION_MODE="${CLAUDE_REVIEW_PERMISSION_MODE:-plan}"
```

## Queue File

Create `agent_tasks/queue.yaml` with entries for completed/current/planned tasks:

```yaml
tasks:
  - id: "001-scaffold"
    title: "Normalize project scaffold"
    file: "agent_tasks/001-scaffold-project.md"
    branch: "main"
    worktree: "main"
    status: "done"
    depends_on: []
    verification:
      - "tree -a -I '.git|__pycache__|node_modules'"
    allowed_paths:
      - "**"

  - id: "002-backend-models"
    title: "Add backend models and capture API"
    file: "agent_tasks/002-backend-models-and-capture-api.md"
    branch: "main"
    worktree: "main"
    status: "done"
    depends_on:
      - "001-scaffold"
    verification:
      - "pytest"
    allowed_paths:
      - "backend/**"
      - "docs/contracts/api_capture_payload.md"
      - "agent_tasks/queue.yaml"

  - id: "003-agent-orchestration"
    title: "Add agent orchestration harness"
    file: "agent_tasks/003-agent-orchestration-harness.md"
    branch: "agent/003-agent-orchestration"
    worktree: "agent-003-agent-orchestration"
    status: "ready"
    depends_on:
      - "002-backend-models"
    verification:
      - "bash -n scripts/agentctl.sh"
      - "scripts/agentctl.sh list"
      - "scripts/agentctl.sh status"
    allowed_paths:
      - "scripts/**"
      - "agent_tasks/queue.yaml"
      - "docs/contracts/agent_orchestration.md"
      - "agent_tasks/003-agent-orchestration-harness.md"

  - id: "004-extension-capture"
    title: "Add browser extension current-page capture"
    file: "agent_tasks/004-extension-capture.md"
    branch: "agent/004-extension-capture"
    worktree: "agent-004-extension-capture"
    status: "planned"
    depends_on:
      - "003-agent-orchestration"
    verification:
      - "npm test"
      - "npm run build"
    allowed_paths:
      - "extension/**"
      - "docs/contracts/browser_extension_capture.md"
      - "agent_tasks/queue.yaml"

  - id: "005-run-directory-writer"
    title: "Add Claude run directory writer"
    file: "agent_tasks/005-run-directory-writer.md"
    branch: "agent/005-run-directory-writer"
    worktree: "agent-005-run-directory-writer"
    status: "planned"
    depends_on:
      - "003-agent-orchestration"
      - "002-backend-models"
    verification:
      - "pytest"
    allowed_paths:
      - "backend/**"
      - "docs/contracts/claude_run_directory.md"
      - "agent_tasks/queue.yaml"
```

If task 002 is not committed yet, mark it as `review` instead of `done`.

## Agent Orchestration Contract

Create `docs/contracts/agent_orchestration.md`.

It should explain:

- task files
- queue metadata
- statuses
- worktree isolation
- run command
- review command
- verification commands
- merge policy
- permission strategy

Use these statuses:

```text
planned
ready
running
review
blocked
done
failed
```

State that completed task branches are not pushed automatically.

State that the user approves merges.

## Script Requirements

`scripts/agentctl.sh` should be Bash.

Use strict mode:

```bash
set -euo pipefail
```

It may use Python or `yq` internally to parse YAML, but if adding a dependency, document it.

Prefer Python standard library if possible.

The script should fail clearly if:

- task ID is missing
- queue file is missing
- task ID is unknown
- task file is missing
- dependency is not done
- git tree is dirty
- Claude command fails

## Out of Scope

Do not implement backend features.

Do not implement frontend features.

Do not implement browser extension logic.

Do not implement Claude run directory creation.

Do not modify application data models unless absolutely necessary.

Do not change existing ADR decisions.

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh list
scripts/agentctl.sh status
```

Do not run product tests unless the script changes require it.

## Git

After changes:

1. Run verification.
2. Stage all files.
3. Commit locally with:

```text
Add agent orchestration harness
```Do not push.wq

