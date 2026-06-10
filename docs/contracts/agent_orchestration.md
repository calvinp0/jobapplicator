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
scripts/agentctl.sh review-status <task-id>
```

The review command starts a separate Claude Code session focused on reviewing
the work the run command produced. It uses
`CLAUDE_REVIEW_PERMISSION_MODE` (default `acceptEdits`) — the reviewer
needs to write exactly one file, the structured review artifact (see
below). The review prompt explicitly forbids editing anything else and
forbids staging, committing, or pushing.

The review prompt asks the reviewer to assess:

- whether the implementation stayed within the task's scope
- whether the task's `allowed_paths` were respected
- whether the relevant ADRs in `docs/adr/` were respected
- whether the tests are meaningful or thin
- whether anything was overbuilt
- whether unrelated files were changed
- whether the commit message is appropriate
- whether verification actually ran, the task worktree is clean, and the
  task branch has at least one commit beyond `main`

### Review verdicts

Every review must end with exactly one verdict:

```
APPROVE              The task satisfies the spec. It may be completed.
APPROVE_WITH_NOTES   The task satisfies the spec. Notes are optional
                     follow-ups and do not block completion.
REQUEST_CHANGES      The task is close but misses required behavior,
                     acceptance criteria, verification, scope, or tests.
                     Must be fixed before completion.
REJECT               The implementation is wrong enough that it should
                     not be patched casually. The operator should abort,
                     reset, or rewrite the task.
BLOCKED              The review could not make a decision because
                     verification did not run, the task branch is dirty,
                     the task spec is ambiguous, dependencies are
                     missing, or the branch has no commit.
```

Mapping rules the reviewer is instructed to follow:

- A caveat that violates acceptance criteria is `REQUEST_CHANGES`, not
  `APPROVE_WITH_NOTES`.
- A caveat that is purely optional is `APPROVE_WITH_NOTES`.
- If verification did not run or the branch is dirty, the verdict is
  `BLOCKED` unless the task explicitly allows that state (e.g. a
  planning-only task with no code commits).
- "Conditional pass" or other vague phrasing is not allowed; the
  reviewer must pick one of the five verdicts.

### Review artifact

The reviewer writes the artifact to:

```
<task-worktree>/.agentctl/reviews/<task-id>.md
```

The file lives inside the task's worktree so the three sessions that
care about it — `review` (running in the task worktree), `complete`
(running in main but resolving the task worktree to read the file), and
`fix` (running in the task worktree) — coordinate through one path.
For tasks whose `worktree` is `main`, the artifact lives in the main
checkout at the same relative path. The artifact starts with YAML
front matter and a fixed set of sections:

```yaml
---
task_id: "033-frontend-workflow-language"
verdict: "REQUEST_CHANGES"
reviewed_at: "2026-05-23T12:34:56Z"
reviewer: "claude-code"
---
```

```markdown
# Review: <task-id>

## Verdict

REQUEST_CHANGES

## Required fixes

- ...                    (or "None.")

## Optional notes

- ...                    (or "None.")

## Evidence checked

- ...

## Scope / allowed-path check

...

## Verification status

...
```

`Required fixes` is the contract for the `fix` command: every bullet
listed there must be addressed before the task can be approved.
`Optional notes` are non-blocking follow-ups; `complete` may proceed
when the verdict is `APPROVE_WITH_NOTES` even if optional notes are
present.

Review artifacts are written into `.agentctl/reviews/` inside the task
worktree (or the main checkout for `worktree: main` tasks) but are not
required to be committed. The directory itself is tracked via
`.agentctl/reviews/.gitkeep`. For `worktree: main` tasks the artifact
ends up in the main checkout's `.agentctl/reviews/`; `complete` filters
untracked `.agentctl/reviews/*.md` files out of its dirty-main check so
those leftover artifacts do not block integration.

### Review-status command

```
scripts/agentctl.sh review-status <task-id>
```

`review-status` is a read-only inspector that prints, for one task:

- the resolved task id
- the latest verdict (or `(none — no review artifact)` if missing, or
  `(invalid — ...)` if the front matter is malformed)
- the artifact path on disk
- a summary of the `Required fixes` section
- a summary of the `Optional notes` section

It never invokes Claude. Use it before running `complete` or `fix` to
double-check the verdict.

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

## Fix Command

```
scripts/agentctl.sh fix <task-id>
```

`fix` launches a Claude Code session in the existing task worktree to
repair whichever failure mode is blocking completion. It exists so the
operator does not have to hand-craft a follow-up prompt when something
goes wrong between `run` and `complete`.

### Failure-mode selection

`fix` inspects two signals before picking a repair strategy. The order
is fixed: a failed verification always takes precedence over the review
verdict, because a task that passed review can still have a failed
verification (verification runs in `complete`, after review).

1. **Verification failed.** If the verification state file
   (`.agentctl/verifications/<task-id>.md`) records `status: failed`,
   `fix` launches a verification-failure repair regardless of the review
   verdict. The operator-facing banner is:
   ```
   Latest review verdict is <verdict>, but verification failed.
   Launching verification-failure repair agent.
   ```
   The repair prompt embeds the failing command, the failure excerpt,
   the task file, and the full verification state file, and instructs
   the agent to diagnose the failure, make the smallest correct change,
   re-run the targeted failing test, then re-run the full verification
   list. The prompt forbids bypassing or weakening tests (no `xfail`,
   no `--skip`, no commenting out) unless a test expectation is genuinely
   obsolete and the reason is documented in the commit message.

2. **Review verdict is `REQUEST_CHANGES`, `REJECT`, or `BLOCKED`.** If
   verification is not in a failed state, `fix` falls back to the
   review-feedback repair. The prompt embeds the task file and the full
   review artifact and instructs the agent to address only the
   `Required fixes` section.

3. **Nothing to fix.** If verification is `passed` (or `missing`, i.e.
   `complete` was never run) AND the review verdict is `APPROVE` or
   `APPROVE_WITH_NOTES`, `fix` refuses with `nothing to fix` and tells
   the operator to run `complete`.

The command:

1. Resolves the task id and loads its metadata.
2. Refuses if the task is already `done`.
3. Resolves the task worktree path and propagates Claude permission
   settings into it.
4. Reads the verification state file at
   `.agentctl/verifications/<task-id>.md`. If it records
   `status: failed`, dispatches the verification-failure repair (step 5).
   Otherwise reads the review artifact and dispatches the
   review-feedback repair if the verdict requires changes.
5. Launches Claude Code from inside the task worktree with permission
   mode `CLAUDE_FIX_PERMISSION_MODE` (default `acceptEdits`).
6. For verification-failure repairs, writes a journal entry under
   `.agentctl/journal/<timestamp>-<task-id>-verification-fix.md` with
   the failing command, failure excerpt, start/end timestamps, and the
   post-fix on-disk verification status.

After the session ends, `fix` prints recent commits and `git status`,
and points the operator at:

- `scripts/agentctl.sh complete <task-id>` after a verification-failure
  repair (`complete` re-runs verification and refreshes the state file).
- `scripts/agentctl.sh review <task-id>` after a review-feedback repair.

`fix` never:

- pushes
- modifies `agent_tasks/queue.yaml`
- changes the verdict in the existing review artifact (the next review
  writes a new one)
- updates the verification state file itself (only `complete`'s
  verification runner writes that file; `fix` reads it)
- runs on a task that is already `done`
- bypasses or weakens tests (the prompt explicitly forbids `--skip`,
  `xfail`, commenting out tests, etc.)

### Verification state file

`.agentctl/verifications/<task-id>.md` is harness-owned and never
committed. The `complete` dirty-main filter ignores untracked files
under `.agentctl/verifications/` for the same reason it ignores
`.agentctl/reviews/` artifacts.

Format mirrors review artifacts:

```yaml
---
task_id: "097-add-firefox-extension-support"
status: "failed"
exit_code: 1
recorded_at: "2026-05-26T11:00:23Z"
---
```

```markdown
# Verification: 097-add-firefox-extension-support

## Failing command

pytest

## Failure excerpt

```
(tail of stdout/stderr from the failing command)
```
```

For `status: passed`, the body shows a single "verification passed at
<ts>" line and the failing-command / failure-excerpt sections are
omitted. The state file is overwritten in place every time
`run_verification_commands` runs, so the file always reflects the most
recent verification attempt.

## Complete Command

```
scripts/agentctl.sh complete <task-id> [--dry-run] [--clean-shadow-files] [--skip-review]
scripts/agentctl.sh complete --continue <task-id>
```

The `complete` command performs the full integration workflow for a
finished task: it checks the review verdict, runs verification, merges
the task's worktree branch into `main`, marks the task `done`, promotes
any newly-unblocked tasks from `planned` to `ready`, and commits the
queue-status update with the message `Update agent task statuses`.

### Review verdict gate

`complete` reads `.agentctl/reviews/<task-id>.md` before doing anything
expensive. Based on the verdict in its front matter:

- `APPROVE` — proceed.
- `APPROVE_WITH_NOTES` — proceed, printing the optional notes for the
  operator's awareness.
- `REQUEST_CHANGES` — refuse; print the `Required fixes` section and
  point at `scripts/agentctl.sh fix <task-id>`.
- `REJECT` — refuse; print the reviewer's notes and explain that a
  REJECT means the task should not be patched casually.
- `BLOCKED` — refuse; print the blocker summary and ask the operator
  to resolve the blocker and re-run review.
- missing artifact — refuse by default; pass `--skip-review` to
  bypass.
- malformed artifact (no recognized verdict in front matter) — refuse
  always. `--skip-review` does NOT bypass a malformed artifact; that
  case is treated as a reviewer or operator typo and surfaced loudly.

This gate runs before the dirty-main check, the merge, and verification,
so a bad verdict fails fast.

### Normal flow

1. Resolves the task id (numeric shortcut or full id).
2. Loads the task metadata from `queue.yaml`. If `status` is already
   `done`, prints `Task <id> is already done.` and exits successfully
   without committing anything.
3. Runs the review verdict gate (see above).
5. Locates the worktree whose checked-out branch is `main` (via
   `git worktree list --porcelain`) and refuses to proceed if that
   worktree has uncommitted changes. Untracked files under
   `.agentctl/reviews/` and `.agentctl/verifications/` are filtered out
   of this check because both are harness-owned and not required to be
   committed. The
   dirty-main report is grouped into "Tracked changes", "Untracked
   files", and — when the task branch exists — "Possible shadow files
   from task branch", which lists untracked files in main whose paths
   are already tracked in `worktree-<worktree>`. These are likely
   files that should only have lived on the task branch and leaked into
   the main checkout. The report prints a targeted `git clean -f -- <paths>`
   command for those files, and also points at the
   `--clean-shadow-files` flag (see below). The harness never auto-runs
   cleanup at this point.
6. Confirms the task worktree exists. For tasks whose `worktree` is
   `main`, this step is a no-op (the task ran in place).
7. Prepares known package workspaces if the task's verification commands
   reference them. If any verification command references `frontend` and
   the task worktree has no `frontend/node_modules/.bin/vitest`, the
   harness runs `npm install` inside `frontend/`. The same rule applies
   to `extension/` (using `extension/node_modules` as the install marker).
   The harness only prepares workspaces the verification commands
   actually mention, never installs globally, and never touches
   unrelated directories. If `npm install` fails, the task is **not**
   marked done.
8. Runs every command in the task's `verification` list inside the task
   worktree. The outcome is recorded to
   `.agentctl/verifications/<task-id>.md` (see *Fix Command* above).
   If any command fails, the task is **not** marked done, nothing is
   merged or committed, and `complete` prints the recovery hint:
   ```
   Verification failed. Run:
     scripts/agentctl.sh fix <task-id>
   ```
   The next `complete` run will re-execute verification and overwrite
   the state file.
9. Determines whether the task branch (`worktree-<worktree>`) is already
   reachable from `main`. If so, the merge step is skipped. Otherwise
   the command requires the branch to have at least one commit beyond
   `main`; a branch that is identical to `main` is treated as "nothing
   to integrate" and `complete` exits with an error explaining that the
   agent has not committed any work yet.
10. If a merge is needed, runs `git merge --no-ff --no-edit
    worktree-<worktree>` in the main worktree. On conflict, the merge is
    **not** aborted: `complete` stops, leaves the conflicted merge in
    place, and prints recovery instructions that direct the operator to
    resolve the conflicts and run `complete --continue <task-id>`.
    `queue.yaml` is not modified in this case.
11. Rewrites the completing task's `status` line to `"done"` and, in the
    same pass, promotes every `planned` task whose dependencies are all
    `done` to `ready`. The in-place text edit preserves YAML comments and
    quoting.
12. Stages and commits `agent_tasks/queue.yaml` with the message
    `Update agent task statuses`.
13. Prints the remaining list of tasks with status `ready`.

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

### `--skip-review`

`complete <task-id> --skip-review` is an explicit bypass for the review
verdict gate. It only matters when there is no review artifact at all
(`.agentctl/reviews/<task-id>.md` does not exist) — in that case, the
flag prints a loud warning and lets `complete` proceed as if the verdict
were `APPROVE`.

The flag **does not** bypass a present verdict of `REQUEST_CHANGES`,
`REJECT`, or `BLOCKED`. To override one of those verdicts the operator
must delete or edit the review artifact themselves; the harness will
not silently complete a task the reviewer rejected.

The flag also does not bypass a malformed artifact (front matter
present but no recognized verdict). That case is treated as a reviewer
or operator typo and surfaced loudly so it can be corrected.

`--skip-review` is mutually exclusive with `--continue`.

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
- runs `git reset --hard` or `git clean` (except the narrow
  `--clean-shadow-files` flag, which removes only the exact untracked
  files reported as shadow files)
- auto-resolves merge conflicts
- marks a task `done` when the review verdict is `REQUEST_CHANGES`,
  `REJECT`, or `BLOCKED`
- marks a task `done` when there is no review artifact and
  `--skip-review` was not passed
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

`runtime_prompts/**` carries the default Claude Code prompts used by
the resume tailoring and revision workers. Operators may locally
override these prompts through the prompt harness editor UI
(Advanced → *Prompt harnesses*), which writes to
`candidate_context/settings/prompt_overrides/` — that directory is
gitignored and is not part of the tracked agent task surface. The
planner's safety boundary continues to exclude `runtime_prompts/**`
because changes to the shipped defaults belong in builder tasks with
the appropriate `allowed_paths`.

If a high-level goal seems to require changes to a forbidden path, the
planner must instead queue a new builder task whose `allowed_paths` cover
that path, and leave the change to be implemented under review.

`.agent_plans/` is gitignored so draft prompts and intermediate plans do
not accumulate in history. Promote a plan by copying its scoped task files
into `agent_tasks/` and committing those.

## Next Command

```
scripts/agentctl.sh next
```

`next` is a read-only inspector that prints the single recommended next
operator action — and nothing else. It never invokes Claude, never
mutates files, branches, queue statuses, or worktrees, and never runs
verification.

It picks the recommendation in this order:

1. If any non-done task has a latest review verdict of
   `REQUEST_CHANGES`, the recommendation is
   `scripts/agentctl.sh fix <task-id>`.
2. If any non-done task has a latest review verdict of `REJECT`, the
   command lists those tasks and notes that they require a human
   decision (no auto-fix).
3. If any non-done task has a latest review verdict of `BLOCKED`, the
   command lists those tasks and points at the blocker summary in the
   review artifact.
4. If any task worktree (other than the main checkout) has uncommitted
   changes, the command lists the dirty worktree paths and says to
   finish, commit, or clean them.
5. Otherwise, if a `ready` task exists, the recommendation is
   `scripts/agentctl.sh work <task-id>`.
6. Otherwise, the command prints `No ready tasks.`

`next` also prints, at the bottom, the (possibly empty) list of tasks
whose queue-level status is `blocked` so the operator does not lose
sight of explicitly blocked work.

## Work Command

```
scripts/agentctl.sh work [<task-id>] [--until-blocked]
                         [--max-fix-attempts N] [--max-tasks N] [--dry-run]
scripts/agentctl.sh work --help
```

`work` is the higher-level orchestration command. It runs the
`run -> review -> (auto-fix) -> complete` lifecycle for one or more
ready tasks, capping auto-fixes and writing a per-invocation journal
file. It exists so the operator does not have to drive every task by
hand through four separate commands.

### Selection

- `work` with no positional argument selects the first task whose
  status is `ready` (in queue order). If there are no ready tasks, it
  prints `No ready tasks.` and exits 0.
- `work <task-id>` runs the lifecycle for the specified task if it is
  `ready`; otherwise it prints why and exits non-zero. Numeric
  shortcuts (`work 033`, `work 33`) resolve the same way as every
  other task-id argument.
- `work --until-blocked` loops over ready tasks one at a time. After
  each task finishes the queue is re-queried so freshly-promoted
  `planned -> ready` tasks become eligible. The loop stops on the
  first stop condition (see below).

`--until-blocked` and `<task-id>` are mutually exclusive.

### Lifecycle

For each selected task, `work` runs four stages:

```
[1/4] Run       scripts/agentctl.sh run <id>
[2/4] Review    scripts/agentctl.sh review <id>; read verdict
[3/4] Fix loop  on REQUEST_CHANGES: scripts/agentctl.sh fix <id>;
                re-review; cap at --max-fix-attempts
[4/4] Complete  scripts/agentctl.sh complete <id>
```

After Stage 1, `work` confirms:

- the run subprocess exited 0,
- the task worktree (for tasks whose `worktree` is not `main`) is
  clean, and
- the task branch has at least one commit beyond `main`.

If any of those fail, `work` stops with a clear reason and does not
proceed to review.

### Auto-fix loop

In Stage 2, `work` reads the structured verdict from
`.agentctl/reviews/<task-id>.md` (see *Review Command* above).
Verdict handling:

- `APPROVE` / `APPROVE_WITH_NOTES` — proceed to Stage 4.
- `REQUEST_CHANGES` — invoke `scripts/agentctl.sh fix <id>`, verify
  the worktree is still clean afterward, then loop back to Stage 2 for
  a fresh review. Repeats until `APPROVE` / `APPROVE_WITH_NOTES`,
  `REJECT`, `BLOCKED`, or `--max-fix-attempts` is reached.
- `REJECT` — stop. The operator must decide whether to abandon,
  reset, or rewrite the task. `work` never auto-fixes a `REJECT`.
- `BLOCKED` — stop. The operator must resolve the blocker (run
  verification, commit work, clarify spec, etc.) and re-run review.
  `work` never auto-fixes a `BLOCKED`.
- missing artifact, malformed verdict, or `review` subprocess
  non-zero exit — stop with a "review did not produce a structured
  verdict" reason.

The default `--max-fix-attempts` is `2`. The fix subprocess is invoked
as a fresh `scripts/agentctl.sh fix <id>` each time so the existing
fix-gate (verdict must be `REQUEST_CHANGES` / `REJECT` / `BLOCKED`)
still applies.

### Complete

In Stage 4, `work` invokes `scripts/agentctl.sh complete <id>`. If
`complete` fails (e.g. verification regression, merge conflict, dirty
main), `work` stops with the failure reason. On success, `work` prints
the journal path and the message from `complete` listing newly-ready
tasks. In `--until-blocked` mode the loop continues with those.

### Stop conditions

`work` stops (and `work --until-blocked` exits the loop) on any of:

```
no ready tasks
run subprocess failed
task worktree dirty after run
task branch has no commit beyond main after run
review subprocess failed
review artifact missing
review artifact has no recognized verdict
verdict REJECT
verdict BLOCKED
verdict REQUEST_CHANGES after max-fix-attempts
fix subprocess failed
task worktree dirty after fix
complete subprocess failed (verification, merge conflict, dirty main, …)
--max-tasks reached (--until-blocked only)
```

Every stop prints:

```
Stopped: <reason>

Task:
  <task-id>

Worktree:
  <path>     # (or "(main checkout)" for tasks whose worktree is main)

Journal:
  .agentctl/journal/<timestamp>-<task-id>.md

Next:
  <suggested command>
```

`work` does NOT auto-resolve merge conflicts. When `complete` hits a
conflict it prints the standard recovery hint (resolve in main, run
`complete --continue <id>`); `work` surfaces that failure as a stop
condition and the operator drives recovery by hand.

### Journal files

Every `work` invocation writes one journal file at:

```
.agentctl/journal/<timestamp>-<task-id>.md
```

The file is created in the main checkout (not in the task worktree)
so all journals live in one place regardless of where the lifecycle
ran. Each file records:

- task id, task title, task file, branch, worktree name
- the main commit at start, the invoking command, start/end timestamps
- the configured `max_fix_attempts` and the `dry_run` flag
- per-stage results (`PASS`, `FAIL`, dry-run skip)
- the verdict read from each review iteration
- the `Required fixes` summary used as input to each fix attempt
- the final outcome — either `completed normally` or the stop reason,
  stop slug, and a suggested next command

Journal files are gitignored. The directory itself is anchored in
git via `.agentctl/journal/.gitkeep`, and `.gitignore` carries:

```
.agentctl/journal/*
!.agentctl/journal/.gitkeep
```

Operators may delete journal files freely; nothing else reads them.
Keeping them around is useful for after-the-fact post-mortems.

### `--dry-run`

`work --dry-run` runs through the lifecycle without invoking Claude
and without mutating `queue.yaml`. For each stage it prints what it
*would* invoke (`(dry-run) would invoke: ... run <id>`, etc.). In
Stage 2 it peeks at any pre-existing review artifact: if one is
present it uses that verdict to predict the flow; if none is present
it assumes `APPROVE` so the operator sees the full would-do sequence.
When a pre-existing `REQUEST_CHANGES` verdict would trigger auto-fix,
dry-run stops at that point with a `dry-run-stop-at-fix` reason
rather than entering a loop with no real fix to apply.

### Safety rules

`work` never:

- pushes anything
- skips review
- skips verification (`complete` still runs the task's verification
  commands)
- continues after a failed subcommand
- continues after a dirty task worktree
- continues after a `REJECT` or `BLOCKED` verdict
- auto-fixes a `REJECT` or `BLOCKED` verdict
- auto-resolves merge conflicts
- deletes a worktree
- runs `git reset --hard` or a broad `git clean`
- modifies product code itself (it only invokes the existing
  subcommands)

### Manual recovery

When `work` stops, every stop block points at a concrete next
command. Common recoveries:

| Stop reason                                   | Recovery |
|-----------------------------------------------|----------|
| `run-failed`                                  | Read the run output, fix the cause, then `scripts/agentctl.sh work <id>` again. |
| `dirty-after-run` / `dirty-after-fix`         | `cd <worktree> && git status`, then commit, finish, or clean. Re-run `work <id>`. |
| `no-commit-after-run`                         | The agent did not commit; inspect the worktree and either retry `run` or write the task off. |
| `review-no-artifact` / `review-invalid-verdict` | Re-run `scripts/agentctl.sh review <id>` (or hand-edit the artifact to a valid verdict). |
| `verdict-REJECT`                              | Human decision required. Abandon, reset, or rewrite the task. |
| `verdict-BLOCKED`                             | Resolve the blocker described in the review artifact; re-run review. |
| `max-fix-attempts`                            | Inspect the latest review; run `scripts/agentctl.sh fix <id>` manually with operator judgment. |
| `complete-failed` (merge conflict)            | Resolve in main, then `scripts/agentctl.sh complete --continue <id>`. |
| `complete-failed` (verification regression)   | Fix the regression, then re-run `work <id>` from the top (or run individual subcommands by hand). |

The individual `run`, `review`, `fix`, and `complete` commands remain
available for any case where the operator wants finer control.

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
scripts/agentctl.sh next
scripts/agentctl.sh work --help
scripts/agentctl.sh work --dry-run
scripts/agentctl.sh doctor
scripts/agentctl.sh sync <task-id>
scripts/agentctl.sh review-status <task-id>
scripts/agentctl.sh complete <task-id> --dry-run
scripts/agentctl.sh complete --continue <task-id>
scripts/agentctl.sh plan --help
```

`ready` is a convenience query that filters `list` to only tasks whose
status is `ready` — i.e. tasks the operator can dispatch right now.

### Manual harness test: verification-failure repair

The `fix` command's verification-repair path does not have a dedicated
shell test suite. The following scenario exercises every branch covered
by Task 099 against a real (but throwaway) task. Run it from a fresh
checkout where the queue's verification command is something cheap
(e.g. `bash -n scripts/agentctl.sh`).

1. **Bootstrap state files by hand.** Create a fake failed-verification
   state for a task you do not intend to complete:
   ```bash
   MAIN_WT="$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')"
   mkdir -p "$MAIN_WT/.agentctl/verifications" "$MAIN_WT/.agentctl/reviews"
   TASK_ID="099-fix-agentctl-verification-failure-repair"
   cat > "$MAIN_WT/.agentctl/verifications/$TASK_ID.md" <<'EOF'
   ---
   task_id: "099-fix-agentctl-verification-failure-repair"
   status: "failed"
   exit_code: 1
   recorded_at: "2026-05-26T00:00:00Z"
   ---

   # Verification: 099-fix-agentctl-verification-failure-repair

   ## Failing command

   pytest

   ## Failure excerpt

   ```
   AssertionError: expected_email_received != needs_review
   ```
   EOF
   cat > "$MAIN_WT/.agentctl/reviews/$TASK_ID.md" <<'EOF'
   ---
   task_id: "099-fix-agentctl-verification-failure-repair"
   verdict: "APPROVE"
   reviewed_at: "2026-05-26T00:00:00Z"
   reviewer: "manual-test"
   ---

   # Review: 099-fix-agentctl-verification-failure-repair

   ## Verdict

   APPROVE
   EOF
   ```

2. **Verify precedence.** Run `scripts/agentctl.sh fix $TASK_ID` and
   confirm the banner says
   `Latest review verdict is APPROVE, but verification failed.` —
   `fix` should launch a verification-failure repair, NOT say
   `nothing to fix`. Cancel the Claude session immediately.

3. **Verify completion guard.** Run `scripts/agentctl.sh complete $TASK_ID`
   and confirm it refuses with the new recovery hint
   (`Verification failed. Run: scripts/agentctl.sh fix <task-id>`).
   (`complete` will re-run verification too — the state file is
   overwritten with the real outcome.)

4. **Verify review-only fix still works.** Replace the verification
   state's `status: failed` with `status: passed`, change the review
   verdict to `REQUEST_CHANGES`, and re-run
   `scripts/agentctl.sh fix $TASK_ID`. Confirm the banner uses the
   existing review-fix wording (no "verification failed" line) and
   that the prompt sent to Claude contains the review artifact, not the
   verification state.

5. **Verify nothing-to-fix.** Set state to `status: passed` and verdict
   to `APPROVE`. Run `scripts/agentctl.sh fix $TASK_ID` and confirm it
   exits with
   `latest review verdict for <id> is APPROVE; nothing to fix.`

6. **Cleanup.** Remove the test state files when finished:
   ```bash
   rm -f "$MAIN_WT/.agentctl/verifications/$TASK_ID.md" \
         "$MAIN_WT/.agentctl/reviews/$TASK_ID.md"
   ```

Tests prove:

1. `fix` runs verification repair when review approved but verification
   failed (step 2).
2. Verification failure takes precedence over review approval (step 2).
3. The repair prompt includes the failing command and failure excerpt
   (visible in the launch banner printed by `fix`).
4. `complete` refuses after verification failure and suggests `fix`
   (step 3).
5. The existing review-feedback fix path still works on
   `REQUEST_CHANGES` (step 4).
6. An approved-and-verified task still says "nothing to fix" (step 5).

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
| `CLAUDE_REVIEW_PERMISSION_MODE`   | `acceptEdits`  | Permission mode for `review`. The reviewer writes exactly one file (the review artifact); the prompt forbids editing anything else. |
| `CLAUDE_FIX_PERMISSION_MODE`      | `acceptEdits`  | Permission mode for `fix`. |
| `CLAUDE_PLAN_PERMISSION_MODE`     | `acceptEdits`  | Permission mode for `plan` (local planner). |
| `CLAUDE_PYTHON`                   | `python3`      | Python interpreter used to parse the queue file. |

`acceptEdits` lets the agent write files in the worktree without
prompting per edit but still surfaces other tool calls. Stricter modes
(`default`, `dontAsk`) and looser modes (`bypassPermissions`) are
available via the same variable. The reviewer used to default to `plan`
(read-only); it now defaults to `acceptEdits` so it can write the
structured review artifact, with the prompt narrowing what it may write.

### Runtime LLM providers are a separate concern

The Claude Code invocations above belong to the *orchestration harness* —
the agent that implements queued builder tasks. They are unrelated to the
*runtime* LLM provider that the application uses to tailor resumes:

- **Resume tailoring (`auto` flow).** Driven by the CLI provider registry
  in `backend/app/llm_providers.py` (ADR-009). Claude Code is the default;
  Codex and Gemini are alternatives. This is a high-risk, evidence-grounded
  output path and is the only flow that produces the run-directory outputs.
- **Experimental local LLM (task 123).** An opt-in, off-by-default
  subsystem (`backend/app/local_llm.py`) for *low-risk* tasks only —
  job summary, ATS keyword extraction, role-requirement extraction,
  evidence gap planning, email classification, and (experimentally) resume
  suggestions. It speaks an OpenAI-compatible HTTP endpoint
  (Ollama/vLLM/LM Studio), never drives the `auto` tailoring flow, and never
  takes over claim auditing or recruiter review.
- **Provider-routed preflight analysis (task 124).** The low-risk extraction
  tasks above run as a preflight pipeline (`backend/app/preflight.py`) that
  executes *before* the main Claude Code tailoring prompt and writes advisory
  structured artifacts under `input/preflight/`. It routes each task to the
  local LLM when enabled and falls back to a deterministic extractor
  otherwise, so it never requires a local LLM and never fails the run. Claude
  Code remains the default for the final resume tailoring, claim audit, and
  recruiter review. See `docs/llm_providers.md` and
  `docs/contracts/claude_run_directory.md`.

Neither runtime provider changes the agent-task lifecycle, the worktree
isolation rules, or the permission strategy documented above.

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
