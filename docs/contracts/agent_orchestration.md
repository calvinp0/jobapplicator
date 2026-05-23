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
`running` to `review` after the agent commits). The harness owns two
transitions of its own, both performed by the `complete` command (see
below):

- `review` → `done` for the task being completed, after its branch has
  been merged into `main` (or was already merged) and verification has
  passed.
- `planned` → `ready` for any task whose dependencies are all `done` once
  the completing task lands. This promotion happens as part of the same
  queue-status commit.

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

All other tasks run in an isolated git worktree at
`.claude/worktrees/<worktree>` on branch `worktree-<worktree>`, branched
from `main`. The harness creates the worktree on first use. This keeps
the main checkout clean and allows multiple tasks to be inspected in
parallel without rebasing.

The harness refuses to start a new run when the current git tree is dirty.

### Launching Claude inside the task worktree

`run`, `run-interactive`, and `review` launch Claude with the process
working directory set to the task worktree path. The harness does this
by `cd`-ing into the worktree directory before invoking `$CLAUDE_BIN`.
`--worktree <name>` is also passed for Claude Code builds that honor it,
but the explicit `cd` is the authoritative isolation mechanism — the
harness does not rely on `--worktree` alone.

The Claude prompt for `run` and `run-interactive` includes a
worktree-context header that names the task worktree path and the main
checkout path, and instructs the agent not to edit the main checkout.
This is defense-in-depth against a Claude session that drifts out of its
worktree and writes files into the main repository checkout (referred to
below as "shadow files").

### Permission propagation

Claude Code reads `.claude/settings.local.json` relative to its working
directory, but that file is gitignored — so a fresh task worktree starts
with no Claude permission allowlist and prompts on every routine command
(`npm install`, `git add`, `npm test`, etc.). To avoid that, every
command that may launch Claude inside a task worktree (`run`,
`run-interactive`, `review`, `sync`) calls a permission-propagation
helper after ensuring the worktree exists. The helper symlinks
`<main>/.claude/settings.local.json` to
`<task-worktree>/.claude/settings.local.json` so the operator's
permission allowlist is visible inside the worktree.

The helper:

- is a no-op when the main checkout has no `.claude/settings.local.json`.
- is a no-op when the target is the main checkout itself.
- is a no-op when the correct symlink already exists.
- never reads or prints the settings file contents.
- never overwrites an existing non-symlink file at the target; that case
  warns and proceeds so a custom per-worktree settings file is preserved.

`.claude/settings.local.json` remains gitignored at every worktree
level, so the symlink is never committed.

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
9. Starts Claude Code from inside the resolved task worktree path
   (`cd <worktree-path>`) with `--worktree <worktree>` and the
   permission mode from `CLAUDE_PERMISSION_MODE` (default
   `acceptEdits`). The explicit `cd` is the authoritative isolation
   mechanism; `--worktree` is passed for builds that honor it but is
   not relied on alone.
10. Passes the full task file content into the Claude prompt, along
    with a worktree-context header that names the worktree path and the
    main checkout path and instructs the agent not to edit the main
    checkout, plus instructions to:
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
scripts/agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files]
scripts/agentctl.sh complete --continue <task-id>
```

The `complete` command performs the full integration workflow for a
finished task: it runs verification, merges the task's worktree branch
into `main`, marks the task `done`, promotes any newly-unblocked tasks
from `planned` to `ready`, and commits the queue-status update with the
message `Update agent task statuses`.

### Normal flow

1. Resolves the task id (numeric shortcut or full id).
2. Loads the task metadata from `queue.yaml`. If `status` is already
   `done`, prints `Task <id> is already done.` and exits successfully
   without committing anything.
3. Locates the worktree whose checked-out branch is `main` (via
   `git worktree list --porcelain`) and refuses to proceed if that
   worktree has uncommitted changes. The dirty-main report is grouped
   into "Tracked changes", "Untracked files", and — when the task
   branch exists — "Possible shadow files from task branch", which
   lists untracked files in main whose paths are already tracked in
   `worktree-<worktree>`. These are likely files that should only have
   lived on the task branch and leaked into the main checkout. The
   report prints a targeted `git clean -f -- <paths>` command for those
   files, and also points at the `--clean-shadow-files` flag (see
   below). The harness never auto-runs cleanup at this point.
4. Confirms the task worktree exists. For tasks whose `worktree` is
   `main`, this step is a no-op (the task ran in place).
5. Prepares known package workspaces if the task's verification commands
   reference them. If any verification command references `frontend` and
   the task worktree has no `frontend/node_modules/.bin/vitest`, the
   harness runs `npm install` inside `frontend/`. The same rule applies
   to `extension/` (using `extension/node_modules` as the install marker).
   The harness only prepares workspaces the verification commands
   actually mention, never installs globally, and never touches
   unrelated directories. If `npm install` fails, the task is **not**
   marked done.
6. Runs every command in the task's `verification` list inside the task
   worktree. If any command fails, the task is **not** marked done and
   nothing is merged or committed.
7. Determines whether the task branch (`worktree-<worktree>`) is already
   reachable from `main`. If so, the merge step is skipped. Otherwise
   the command requires the branch to have at least one commit beyond
   `main`; a branch that is identical to `main` is treated as "nothing
   to integrate" and `complete` exits with an error explaining that the
   agent has not committed any work yet.
8. If a merge is needed, runs `git merge --no-ff --no-edit
   worktree-<worktree>` in the main worktree. On conflict, the merge is
   **not** aborted: `complete` stops, leaves the conflicted merge in
   place, and prints recovery instructions that direct the operator to
   resolve the conflicts and run `complete --continue <task-id>`.
   `queue.yaml` is not modified in this case.
9. Rewrites the completing task's `status` line to `"done"` and, in the
   same pass, promotes every `planned` task whose dependencies are all
   `done` to `ready`. The in-place text edit preserves YAML comments and
   quoting.
10. Stages and commits `agent_tasks/queue.yaml` with the message
    `Update agent task statuses`.
11. Prints the remaining list of tasks with status `ready`.

### `--dry-run`

`complete <task-id> --dry-run` validates the same preconditions (main
worktree clean, task worktree exists, branch state) and prints the
sequence of actions it would take, without:

- running verification commands
- merging branches
- modifying `queue.yaml`
- creating any commits

The output lines have the form:

```
would run verification (in <task-worktree>)
would merge branch <branch> into main
would mark <id> done
would promote <ids>
would commit queue update
```

For an already-done task, dry-run prints `Task <id> is already done.`
and exits successfully. For a branch whose tip already matches `main`,
dry-run prints `would skip merge (...)` in place of the merge line.

### `--clean-shadow-files`

`complete <task-id> --clean-shadow-files` performs targeted cleanup of
"shadow files" in the main checkout before the dirty-main check runs.
A shadow file is an untracked file in the main worktree whose path is
already tracked in the task branch (`worktree-<worktree>`). These are
the files most likely to have leaked out of a misbehaving task run.

The flag's behavior is deliberately narrow:

- It only removes files reported by the shadow-file detection above.
- It never removes modified tracked files.
- It never runs `git clean -fd` or any recursive directory clean.
- It removes each shadow file via `git clean -f -- <path>`, one at a
  time, after printing the full list.
- It does nothing for tasks whose `worktree` is `main` (there is no
  separate task branch to compare against).

When combined with `--dry-run`, the flag prints the files it would
remove without removing them.

If main remains dirty after shadow-file cleanup (e.g. because the
dirtiness is in modified tracked files), `complete` exits with the
normal dirty-main report and does not proceed to merge or status
updates.

### `--continue` after a merge conflict

`complete --continue <task-id>` resumes the integration flow after the
operator has resolved a merge conflict by hand:

1. Resolves the task id.
2. Confirms either a merge is in progress in the main worktree
   (`MERGE_HEAD` exists) or the task branch is already merged into
   `main`. If neither holds, the command tells the operator to run a
   normal `complete` instead.
3. If a merge is in progress, refuses to continue while any tracked
   files still have unresolved conflict markers (`git diff --diff-filter=U`).
4. Prepares known package workspaces (`frontend/`, `extension/`) inside
   the main worktree using the same rules as the normal flow, then runs
   the task's verification commands in the main worktree (the post-merge
   state). If preparation or verification fails, the task is **not**
   marked done.
5. Finalizes the merge commit with `git commit --no-edit` if one is
   still pending.
6. Marks the task `done`, promotes newly-unblocked tasks to `ready`,
   and commits the queue update with `Update agent task statuses`.
7. Prints the remaining ready tasks.

`complete --continue` and `--dry-run` are mutually exclusive.

### Safety rules

`complete` never:

- pushes anything
- deletes a worktree
- runs `git reset --hard` or `git clean`
- auto-resolves merge conflicts
- marks a task `done` when verification or the merge has failed
- modifies `queue.yaml` when the merge has failed

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

## Doctor Command

```
scripts/agentctl.sh doctor
```

`doctor` runs a read-only preflight check of the local agent harness
environment and prints a PASS / WARN / FAIL report. It exists to catch
the common setup failures that previously only surfaced after an agent
task had already started — missing `node_modules` in `frontend/` or
`extension/`, a dirty main checkout, a missing `.claude/settings.local.json`
permission that quietly blocks routine commands, or a queue.yaml with
broken dependencies.

`doctor` performs the following groups of checks:

- **Git** — locates the main worktree, confirms its HEAD is on `main`,
  reports whether it is clean (and prints `git status --short` if not),
  reports whether a merge is in progress, and warns when a directory
  under `.claude/worktrees/` exists without being a registered git
  worktree.
- **Queue** — verifies `agent_tasks/queue.yaml` exists and parses as
  YAML, that task ids are unique, that statuses are valid, that every
  `file` exists on disk, that `depends_on` references known task ids,
  and warns if any `ready` task has a dependency that is not yet `done`.
- **Tools** — checks for `git`, `python`, `python3`, `claude`, `npm`,
  and `pytest` via `command -v`. Missing optional tools are warnings,
  not failures.
- **Claude permissions** — checks whether `.claude/settings.local.json`
  exists in the main checkout, validates it as JSON, and warns about
  any of the following well-known patterns that are absent from
  `permissions.allow`: `Bash(git add:*)`, `Bash(git commit:*)`,
  `Bash(npm install:*)`, `Bash(npm test:*)`, `Bash(npm run build:*)`,
  `Bash(pytest:*)`, `Bash(bash -n:*)`. Then, for each registered task
  worktree, reports whether `.claude/settings.local.json` is visible
  inside it (`PASS worktree <name> has Claude settings visible` or
  `WARN worktree <name> missing .claude/settings.local.json`). The file's
  contents are never printed.
- **Workspaces** — if `frontend/package.json` exists, checks for
  `frontend/node_modules/.bin/vitest`; if `extension/package.json`
  exists, checks for `extension/node_modules`. A missing marker is a
  warning, and `doctor` prints the exact `cd <dir> && npm install`
  command — but never runs it.
- **Ready tasks** — for each task whose status is `ready`, prints the
  task id, its verification kind (frontend / extension / backend),
  whether its worktree exists, and the literal verification commands.
  `doctor` never executes a task's verification commands.

### Exit codes

```
0  no FAIL items (warnings only is still success)
1  at least one FAIL item was emitted
```

### Safety boundary

`doctor` is read-only. It never:

- pushes
- runs `npm install`, `pytest`, or any task verification command
- mutates files, including `.claude/settings.local.json` or
  `agent_tasks/queue.yaml`
- prints the contents of `.claude/settings.local.json` or `.env` files

A task-specific form, `scripts/agentctl.sh doctor <task-id>`, is
reserved for future work; today the command accepts only the
zero-argument global form and exits non-zero with a clear message if
a task id is supplied.

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
scripts/agentctl.sh doctor
scripts/agentctl.sh sync <task-id>
scripts/agentctl.sh complete <task-id> --dry-run
scripts/agentctl.sh complete --continue <task-id>
scripts/agentctl.sh plan --help
```

`ready` is a convenience query that filters `list` to only tasks whose
status is `ready` — i.e. tasks the operator can dispatch right now.

## Merge Policy

Task branches are merged into `main` locally by `complete` (see above);
the harness never pushes anything. The builder commits inside the task
worktree, the reviewer assesses the commit, and only when the operator
runs `complete` does the branch land on `main` — at which point
`complete` performs a `git merge --no-ff --no-edit` and writes the
queue-status update commit.

The operator approves every merge by choosing to run `complete`. There
is no automatic promotion of a `review` task to `done`; the harness
only runs the merge and queue update when the operator invokes it
explicitly.

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
