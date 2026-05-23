# Task 028: Propagate Claude Permissions to Task Worktrees

## Goal

Fix the agent harness so non-interactive Claude Code runs do not repeatedly ask for approval for ordinary development commands.

Recent runs showed Claude Code blocking commands such as:

```text
npm install
npm test
npm run build
git add
git commit
ln -s
```

inside task worktrees, even though the main project has `.claude/settings.local.json` configured.

The likely cause is that Claude is launched from the task worktree, but the worktree does not have access to the main checkout's `.claude/settings.local.json`.

This task should make permission configuration available inside each task worktree.

Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

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

When `agentctl` creates or prepares a task worktree, it must ensure the task worktree has Claude local settings available.

If the main checkout contains:

```text
.claude/settings.local.json
```

then the worktree should get:

```text
<task-worktree>/.claude/settings.local.json
```

Acceptable implementations:

```bash
mkdir -p "$worktree_path/.claude"
ln -sfn "$main_repo/.claude/settings.local.json" "$worktree_path/.claude/settings.local.json"
```

or:

```bash
mkdir -p "$worktree_path/.claude"
cp "$main_repo/.claude/settings.local.json" "$worktree_path/.claude/settings.local.json"
```

Prefer symlink if reliable. Use copy if symlinks complicate cleanup.

## Safety Rules

Do not commit `.claude/settings.local.json`.

Do not print the full settings file.

Do not print secrets.

Do not broaden permissions automatically.

Do not edit product code.

Do not push.

## Doctor Update

Update:

```bash
scripts/agentctl.sh doctor
```

to report whether task worktrees can see Claude settings.

Expected output examples:

```text
PASS main .claude/settings.local.json valid JSON
PASS worktree 027 has Claude settings visible
WARN worktree 018 missing .claude/settings.local.json
```

It should not print file contents.

## Run Behavior

Before launching Claude in:

```text
run
run-interactive
review
plan if applicable
```

the harness should call the permission propagation helper.

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh doctor
scripts/agentctl.sh sync 027
```

Then verify the file exists:

```bash
test -e .claude/worktrees/agent-027-frontend-dashboard-home/.claude/settings.local.json
```

If task 027 is still dirty, do not modify its product files.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Propagate Claude permissions to worktrees
```

Do not push.
