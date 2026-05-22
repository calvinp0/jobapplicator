# Agent Orchestration Contract

This document defines how agent tasks are described, queued, executed, and reviewed
in this repository. It is the source of truth for the behavior of
`scripts/agentctl.sh` and `agent_tasks/queue.yaml`.

The harness is a development workflow, not a product feature.

## Task Files

Each task is a single markdown file under `agent_tasks/`, named with a numeric
prefix and a short slug:

```
agent_tasks/<NNN>-<slug>.md
```

A task file states, at minimum:

- a goal
- background documents the agent should read
- the scope (what to do)
- explicit out-of-scope statements
- verification commands
- the required commit message

Task files are immutable once a task is in flight. Edits should land in a new
task file rather than mutating one already running or reviewed.

## Queue Metadata

`agent_tasks/queue.yaml` carries one entry per task. Each entry uses the
following keys.

| Key             | Type                | Description |
|-----------------|---------------------|-------------|
| `id`            | string              | Stable identifier, e.g. `003-agent-orchestration`. |
| `title`         | string              | Human-readable summary. |
| `file`          | string              | Path to the task markdown file, repo-relative. |
| `branch`        | string              | Branch the task targets (`main` for in-place tasks, otherwise `agent/<id>`). |
| `worktree`      | string              | Worktree name passed to `claude --worktree`. Use `main` for in-place tasks. |
| `status`        | string (enum below) | Current state of the task. |
| `depends_on`    | list of task ids    | Other tasks that must be `done` before this one may run. |
| `verification`  | list of commands    | Shell commands the agent must run before committing. |
| `allowed_paths` | list of globs       | Globs the agent's writes must stay within. `**` means anywhere. |

## Statuses

Status values are:

- `planned` — written down but not yet ready to run; usually blocked by design work.
- `ready` — dependencies satisfied, can be picked up by an agent now.
- `running` — an agent is currently executing the task.
- `review` — the agent has committed; awaiting human review.
- `blocked` — explicitly blocked on external work; details should live in the task file.
- `done` — reviewed, merged, and considered complete.
- `failed` — attempted and abandoned; new attempts should use a new task id.

The harness reads statuses but does not write them. The user updates the queue
when transitioning a task between states (typically from `ready` to `running`
when starting, from `running` to `review` after the agent commits, and from
`review` to `done` after the user accepts the work).

## Worktree Isolation

Tasks whose `worktree` is `main` run on the current checkout in place. They are
reserved for foundational changes (initial scaffold, top-level docs) where there
is no risk of conflicting parallel work.

All other tasks run in an isolated git worktree, created by Claude Code via
`--worktree <name>`. This keeps the main checkout clean and allows multiple
tasks to be inspected in parallel without rebasing.

The harness refuses to start a new run when the current git tree is dirty.

## Run Command

```
scripts/agentctl.sh run <task-id>
```

The run command:

1. Verifies that `agent_tasks/queue.yaml` exists.
2. Resolves the task id and reads its metadata.
3. Verifies the task file exists on disk.
4. Verifies that every entry in `depends_on` has status `done`.
5. Verifies the current git tree is clean.
6. Refuses to re-run a task whose status is already `done`.
7. Ensures the task worktree exists. If a worktree whose final path segment
   matches the task's `worktree` field is not already registered with git, the
   harness creates one at `.claude/worktrees/<worktree>` on a new branch
   `worktree-<worktree>` branched from `main`. Tasks whose worktree is `main`
   skip this step.
8. If the worktree branch is behind `main`, merges `main` into it with
   `--no-edit`. If the merge has conflicts, the harness aborts the merge
   (`git merge --abort`) and exits non-zero so the operator can resolve
   manually.
9. Starts Claude Code with `--worktree <worktree>` and the permission mode from
   `CLAUDE_PERMISSION_MODE` (default `acceptEdits`).
10. Passes the full task file content into the Claude prompt, along with
    instructions to:
    - read the referenced background documents
    - stay within the task's scope
    - touch only files inside `allowed_paths`
    - run the listed verification commands
    - stage and commit changes locally with the commit message named in the task
    - **not** push
11. After Claude returns, prints recent commits, `git status`, and the exact
    next command (`scripts/agentctl.sh review <task-id>`).

If the local Claude Code build does not support `--worktree` or
`--permission-mode`, the equivalent manual workflow is to run Claude Code from
inside the worktree path printed by the harness. The script is short enough
that adjusting the invocation is straightforward.

## Review Command

```
scripts/agentctl.sh review <task-id>
```

The review command starts a separate Claude Code session focused on reviewing
the work the run command produced. It uses
`CLAUDE_REVIEW_PERMISSION_MODE` (default `plan`) so the reviewer does not
write to disk by default.

The review prompt asks the reviewer to assess:

- whether the implementation stayed within the task's scope
- whether the task's `allowed_paths` were respected
- whether the relevant ADRs in `docs/adr/` were respected
- whether the tests are meaningful or thin
- whether anything was overbuilt
- whether unrelated files were changed
- whether the commit message is appropriate

## Verification Commands

Verification commands listed under a task's `verification` field are run by the
agent during the task, not by `agentctl.sh`. They exist so the task file is
self-describing — anyone reading it (human or agent) can reproduce the check.

The harness's own behavior is independently verifiable with:

```
bash -n scripts/agentctl.sh
scripts/agentctl.sh list
scripts/agentctl.sh status
scripts/agentctl.sh ready
```

`ready` is a convenience query that filters `list` to only tasks whose
status is `ready` — i.e. tasks the operator can dispatch right now.

## Merge Policy

Completed task branches are **not** pushed automatically by the harness. The
agent commits locally; the user is responsible for review, push, and merge.

The user approves every merge. There is no automatic promotion of a `review`
task to `done`.

## Permission Strategy

The harness exposes Claude Code's permission mode via environment variables so
the operator can dial autonomy up or down without editing the script:

| Variable                          | Default        | Purpose |
|-----------------------------------|----------------|---------|
| `CLAUDE_BIN`                      | `claude`       | Claude Code executable. |
| `CLAUDE_PERMISSION_MODE`          | `acceptEdits`  | Permission mode for `run`. |
| `CLAUDE_REVIEW_PERMISSION_MODE`   | `plan`         | Permission mode for `review`. |
| `CLAUDE_PYTHON`                   | `python3`      | Python interpreter used to parse the queue file. |

`acceptEdits` lets the agent write files in the worktree without prompting per
edit but still surfaces other tool calls. `plan` keeps the reviewer read-only.
Stricter modes (`default`, `dontAsk`) and looser modes (`bypassPermissions`)
are available via the same variable.

## Dependencies

The script is plain Bash with `set -euo pipefail`. It shells out to `python3`
with PyYAML to parse `queue.yaml`. PyYAML is a documented external dependency;
set `CLAUDE_PYTHON` to a Python interpreter that has it (for example, the
project's mamba environment). No other dependencies beyond `git` and Claude
Code itself.

## Failure Modes

The script fails clearly when:

- the task id argument is missing
- `agent_tasks/queue.yaml` is missing
- the requested task id is unknown
- the task's `file` does not exist on disk
- any of the task's dependencies is not `done`
- the current git tree is dirty
- the Claude Code invocation exits non-zero
