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

The user updates most statuses by hand when transitioning a task between
states (typically from `ready` to `running` when starting, and from
`running` to `review` after the agent commits). The one transition the
harness can write itself is `review` → `done`, via the `complete` command
(see below), which refuses to mark a task done until its worktree branch is
reachable from `main`.

## Task ID Resolution

Commands that take a `<task-id>` argument (`run`, `run-interactive`,
`review`, `sync`, `complete`) accept either the full id or a numeric
shortcut:

- `014-backend-application-submit-and-open-file` — full id, always works.
- `014` — three-digit numeric prefix.
- `14` — any all-digit reference; zero-padded to three digits before
  matching (so `14` becomes `014` and `8` becomes `008`).

The shortcut is resolved against existing task ids of the form `<NNN>-...`:

1. If the input exactly matches an existing task id, it is used as-is.
2. Otherwise, if the input is all digits, it is zero-padded to three
   digits and matched against the `NNN-` prefix of every task id.
3. Exactly one match is required. Zero or multiple matches cause the
   command to fail with a clear error listing the candidates.

When a shortcut is resolved, the harness prints
`Resolved task <ref> -> <full-id>` to stderr before running the command,
so logs and error messages always show the full id.

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

## Sync Command

```
scripts/agentctl.sh sync <task-id>
```

Refreshes the task's worktree without invoking Claude:

1. Looks up the task and reads its `worktree` field.
2. If `worktree` is `main`, exits with a no-op message.
3. Ensures the worktree exists (creating it at
   `.claude/worktrees/<worktree>` on branch `worktree-<worktree>` if not).
4. Verifies the worktree's working tree is clean. (Unlike `run`, `sync`
   does **not** require the main checkout to be clean — it only touches
   the child worktree.)
5. If the worktree branch is behind `main`, merges `main` into it with
   `--no-edit`. On conflict the merge is aborted and the command exits
   non-zero so the operator can resolve manually.

Use `sync` to keep a long-running task's worktree current with `main` in
between `run` invocations.

## Complete Command

```
scripts/agentctl.sh complete <task-id> [--dry-run]
```

Marks a task `done` in `queue.yaml` after verifying its branch has landed
on `main`:

1. Looks up the task and its current status.
2. If status is already `done`, exits successfully without changes.
3. Otherwise, unless the task targets `main`, verifies that the branch
   `worktree-<worktree>` is reachable from `main` (i.e. already merged).
   If the branch exists locally but is not yet merged, the command
   refuses and prints the manual merge command to run first. A branch
   that does not exist locally is treated as already cleaned up
   post-merge.
4. Rewrites the task's `status` line in `queue.yaml` to `"done"`,
   preserving surrounding formatting and comments.
5. Prints the suggested follow-up commit command.

With `--dry-run`, steps 1–3 still run (so the merge-reachability check is
still enforced), but step 4 is skipped and the planned transition is
printed instead.

## Plan Command

```
scripts/agentctl.sh plan "<high-level goal>"
scripts/agentctl.sh plan --ultraplan "<high-level goal>"
scripts/agentctl.sh plan --help
```

The plan command generates scoped agent task packs from a high-level goal,
so future implementation tasks do not have to be hand-written one at a time.

The harness has three distinct agent roles. Each runs as a separate Claude
Code session.

- **Planner** — reads the queue, docs, ADRs, and contracts, and writes new
  task files and queue entries. Does not implement product code.
- **Builder** — invoked by `run`. Implements a single task within its
  `allowed_paths`. Commits locally.
- **Reviewer** — invoked by `review`. Reads the builder's commit and reports
  on scope, ADRs, tests, overbuild, and unrelated changes.

The planner's full role contract — including required task-file structure,
status semantics, and anti-patterns — lives in
`agent_tasks/planning_guidelines.md`. This section is the harness-side
summary.

### Local planner mode

`scripts/agentctl.sh plan "<high-level goal>"` launches Claude Code locally
with a planner prompt that:

1. Requires reading `docs/product_requirements.md`, `docs/architecture.md`,
   `docs/contracts/*.md`, `docs/adr/*.md`,
   `agent_tasks/planning_guidelines.md`, and `agent_tasks/queue.yaml` first.
2. Asks the planner to produce one or more scoped task markdown files under
   `agent_tasks/` and matching entries in `agent_tasks/queue.yaml`.
3. Names the next free numeric id by continuing the existing sequence in
   `queue.yaml`.
4. Forbids product implementation, ADR edits, and edits to
   `docs/product_requirements.md` / `docs/architecture.md`.
5. Forbids marking any new task `done`. Only `planned`, `ready`, or
   `blocked` may be emitted.
6. Asks the planner not to stage or commit — the operator reviews the diff
   and commits.

The planner runs in the main checkout (no sub-worktree), with permission
mode `CLAUDE_PLAN_PERMISSION_MODE` (default `acceptEdits`). The harness
refuses to start the planner when the main checkout is dirty, mirroring
`run`'s behavior.

### Ultraplan mode

`scripts/agentctl.sh plan --ultraplan "<high-level goal>"` is deterministic
and does not invoke Claude Code. It writes a self-contained prompt file
under `.agent_plans/<YYYY-MM-DD-HHMMSS>-ultraplan.md` that includes:

- the high-level goal
- the current completed-task history from `queue.yaml`
- the current open tasks (ready / planned / blocked / running / review)
- references to the relevant docs, ADRs, contracts, and planning guidelines
- the planner directives (allowed and forbidden paths, required task-file
  sections, required queue-entry fields, status restrictions)
- the instruction not to implement product code
- the instruction to preserve completed task history
- the instruction to keep tasks small and `allowed_paths` narrow

After writing the file, the command prints manual handoff instructions:
open Claude Code, run `/ultraplan` against the generated prompt, review the
proposed plan, and then save the new task files under `agent_tasks/` and
update `queue.yaml`. The file-based handoff is the reliable fallback even
if a local `/ultraplan` command is not available.

### Generated task file requirements

Every task file the planner produces must include, in order:

```
Goal
Background
Scope
Allowed files
Forbidden files
Out of scope
Acceptance criteria
Verification
Git instructions
```

### Generated queue entry requirements

Every queue entry the planner produces must include:

```yaml
- id: "<NNN>-<slug>"
  title: "<human-readable summary>"
  file: "agent_tasks/<NNN>-<slug>.md"
  branch: "agent/<NNN>-<slug>"          # or "main" for in-place tasks
  worktree: "agent-<NNN>-<slug>"        # or "main" for in-place tasks
  status: "planned" | "ready" | "blocked"
  depends_on: [...]
  verification: [...]
  allowed_paths: [...]
```

The planner must never emit `done`, `running`, `review`, or `failed` as a
status. Those statuses are owned by the builder, reviewer, and `complete`
flows.

### Planner safety boundary

The planner may edit only:

```
agent_tasks/**
docs/contracts/agent_orchestration.md
.agent_plans/**
.gitignore
```

The planner must not edit:

```
backend/**
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/adr/**
docs/product_requirements.md
docs/architecture.md
```

If a high-level goal seems to require changes to a forbidden path, the
planner must instead queue a new builder task whose `allowed_paths` cover
that path, and leave the change to be implemented under review.

`.agent_plans/` is gitignored so draft prompts and intermediate plans do
not accumulate in history. Promote a plan by copying its scoped task files
into `agent_tasks/` and committing those.

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
scripts/agentctl.sh sync <task-id>
scripts/agentctl.sh complete <task-id> --dry-run
scripts/agentctl.sh plan --help
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
| `CLAUDE_PLAN_PERMISSION_MODE`     | `acceptEdits`  | Permission mode for `plan` (local planner). |
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
