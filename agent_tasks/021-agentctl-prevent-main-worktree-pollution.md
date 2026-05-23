# Task 021: Prevent Main Worktree Pollution During Agent Runs

## Goal

Fix the agent orchestration harness so Claude Code task runs do not accidentally write files into the main checkout.

Recent frontend tasks created files correctly in the task worktree, but also leaked untracked files into the main checkout. This caused `scripts/agentctl.sh complete <task-id>` to fail because the main worktree was dirty.

The harness should make the task worktree the clear execution context and should detect common “shadow files” in main before completion.

This task improves orchestration reliability. Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/queue.yaml
agent_tasks/planning_guidelines.md
```

Relevant observed problem:

```text
main worktree became dirty with files such as:
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/test/jobDetailResumeVersions.test.tsx
frontend/src/test/resumeVersionDetailPage.test.tsx
```

Those files belonged to the task worktree branch, not to untracked main.

## Scope

Update:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
```

Optionally update:

```text
agent_tasks/planning_guidelines.md
```

## Required Behavior

### 1. Launch Claude from the task worktree path

For `run`, `run-interactive`, `review`, and `plan` where relevant, ensure Claude is launched with the current working directory set to the task worktree path.

Do not rely only on:

```bash
claude --worktree <name>
```

The harness should explicitly run Claude from inside the resolved task worktree path, for example:

```bash
(
  cd "$worktree_path"
  "$CLAUDE_BIN" ...
)
```

The prompt should explicitly say:

```text
You are operating in this task worktree:
<worktree_path>

Do not edit the main checkout:
<main_repo_path>
```

### 2. Add a main-worktree pollution check

Before `complete <task-id>` fails generically on dirty main, detect whether the dirty files are untracked files that also exist in the task branch.

If main has untracked files and those exact paths are tracked in the task branch, print a targeted message:

```text
Main contains untracked files that are already present in the task branch.
These are likely leaked task-worktree files.

Clean them with:

  git clean -f <paths...>
```

Do not delete them automatically unless an explicit flag is passed.

### 3. Optional cleanup flag

Add optional support for:

```bash
scripts/agentctl.sh complete <task-id> --clean-shadow-files
```

Behavior:

- only remove untracked files in main
- only remove files whose paths exist in the task branch
- print the files before deleting
- never delete modified tracked files
- never run broad `git clean -fd`
- never delete directories recursively

If this is too much for this task, skip the flag and only print the targeted cleanup command.

### 4. Improve error message for dirty main

If main is dirty, show grouped output:

```text
Tracked changes:
  ...

Untracked files:
  ...

Possible shadow files from task branch:
  ...

Suggested cleanup:
  git clean -f ...
```

## Safety Rules

Do not push.

Do not run broad cleanup commands.

Do not run:

```bash
git clean -fd
git reset --hard
rm -rf
```

Do not auto-delete files unless implementing the explicit `--clean-shadow-files` flag and only for exact untracked shadow files.

Do not modify backend, frontend, extension, runtime prompt, or candidate context code.

## Out of Scope

Do not implement product features.

Do not change task statuses.

Do not change queue dependency logic.

Do not change existing task IDs.

Do not rewrite completed queue history.

Do not change frontend/backend tests.

## Acceptance Criteria

- `run` launches Claude from the task worktree path.
- `review` launches Claude from the task worktree path.
- Prompts include the worktree path and warn not to edit the main checkout.
- `complete` detects untracked main files that are also present in the task branch and prints a targeted cleanup command.
- Existing commands still work:
  - `status`
  - `ready`
  - `sync`
  - `run`
  - `review`
  - `complete`
  - `plan --help`

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh plan --help
scripts/agentctl.sh complete 021 --dry-run
```

If feasible, create a safe temporary shadow-file simulation using an ignored or throwaway path, then verify that `complete` reports the targeted cleanup command. Do not leave temporary files behind.

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Prevent main worktree pollution
```

Do not push.
