# Task 020: Make `complete` Merge Task Branches

## Goal

Improve `scripts/agentctl.sh complete` so it performs the full integration workflow instead of requiring the user to manually merge task branches into `main`.

The user should be able to run:

```bash
scripts/agentctl.sh complete 014
```

and have the harness:

1. resolve the short task ID
2. verify the task branch
3. merge the task branch into `main`
4. mark the task done
5. promote unblocked tasks
6. commit the queue update

This task improves the agent orchestration harness. Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
agent_tasks/queue.yaml
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

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

### `complete <task-id>`

`complete <task-id>` should perform the full integration workflow.

Example:

```bash
scripts/agentctl.sh complete 014
```

should:

1. Resolve `014` to the full queue ID.
2. Load the task metadata from `agent_tasks/queue.yaml`.
3. Confirm `main` worktree is clean.
4. Confirm the task worktree exists.
5. Run the task verification commands from `queue.yaml`.
6. Confirm the task branch has at least one commit not already on `main`, unless the task is already marked `done`.
7. Merge the task branch into `main` using:

```bash
git merge --no-ff <task-branch>
```

8. If the merge succeeds:
   - set the task status to `done`
   - promote any `planned` task whose dependencies are all `done` to `ready`
   - commit the queue status update with:

```text
Update agent task statuses
```

9. Print the remaining ready tasks.

### Already-done behavior

If the task is already marked `done`, `complete <task-id>` should exit successfully with a clear message:

```text
Task <id> is already done.
```

It should not create a new commit.

### Already-merged behavior

If the task branch is already merged into `main` but the queue status is not `done`, `complete <task-id>` should skip the merge step and proceed to update queue statuses.

### Merge-conflict behavior

If the merge fails due to conflicts, the command should stop and print clear recovery instructions.

It must not mark the task done.

It must not modify `queue.yaml`.

It should print something like:

```text
Merge conflict while completing <task-id>.

Resolve conflicts in main, then run:

  git status
  bash -n scripts/agentctl.sh
  scripts/agentctl.sh complete --continue <task-id>
```

### `complete --continue <task-id>`

Add:

```bash
scripts/agentctl.sh complete --continue <task-id>
```

This command is used after the user manually resolves a merge conflict.

It should:

1. Resolve the task ID.
2. Confirm the repo is in a merge state or has a merge resolution staged/ready.
3. Confirm there are no conflict markers in tracked text files changed by the merge.
4. Run verification commands from the queue.
5. Finish the merge commit if needed.
6. Set the task status to `done`.
7. Promote newly unblocked tasks.
8. Commit the queue status update.
9. Print ready tasks.

If no merge is in progress and the branch is already merged, it should behave like normal `complete`.

### `complete <task-id> --dry-run`

Keep or add dry-run support.

Dry-run should print what would happen without changing files:

```text
would run verification
would merge branch <branch> into main
would mark <task-id> done
would promote <ids>
would commit queue update
```

Dry-run must not mutate `queue.yaml`.

Dry-run must not merge branches.

## Safety Rules

Do not push.

Do not delete worktrees.

Do not run `git reset --hard`.

Do not run `git clean`.

Do not auto-resolve merge conflicts.

Do not mark a task `done` if verification fails.

Do not mark a task `done` if merge fails.

Do not modify product code.

## Numeric Task IDs

All new `complete` behaviors must support numeric task shortcuts already implemented by task 019.

These should all work:

```bash
scripts/agentctl.sh complete 014
scripts/agentctl.sh complete --continue 014
scripts/agentctl.sh complete 014 --dry-run
scripts/agentctl.sh complete 014-backend-application-submit-and-open-file
```

## Out of Scope

Do not implement backend features.

Do not implement frontend features.

Do not implement extension features.

Do not change queue task IDs.

Do not change completed task history except through status updates performed by `complete`.

Do not push.

## Acceptance Criteria

The following commands work:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh complete 020 --dry-run
```

If there is a safe already-done task, this should also work:

```bash
scripts/agentctl.sh complete 019 --dry-run
```

The usage output must document:

```text
scripts/agentctl.sh complete <task-id> [--dry-run]
scripts/agentctl.sh complete --continue <task-id>
```

The implementation should make the normal workflow:

```bash
scripts/agentctl.sh run <task-id>
scripts/agentctl.sh review <task-id>
scripts/agentctl.sh complete <task-id>
```

without requiring a manual `git merge` unless there is a real merge conflict.

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh complete 020 --dry-run
```

Also run one safe already-done dry-run check:

```bash
scripts/agentctl.sh complete 019 --dry-run
```

Do not run a destructive completion test on an unrelated task.

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Make complete merge task branches
```

Do not push.
