# Task 041: Add Agentctl Work Auto-Fix Loop and Journal

## Goal

Add a higher-level `work` command to `scripts/agentctl.sh` so the operator does not have to manually run:

```bash
scripts/agentctl.sh run <task-id>
scripts/agentctl.sh review <task-id>
scripts/agentctl.sh fix <task-id>
scripts/agentctl.sh review <task-id>
scripts/agentctl.sh complete <task-id>
```

for every task.

The command should run the normal task lifecycle, automatically fix `REQUEST_CHANGES` review verdicts when safe, and record a journal of every step.

This task improves orchestration reliability and reduces manual babysitting.

Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
agent_tasks/queue.yaml
.agentctl/reviews/
```

This task assumes task 040 has added structured review verdicts and a `fix` command.

The desired future operator flow is:

```bash
scripts/agentctl.sh work --until-blocked
```

The harness should keep working through ready tasks until something genuinely requires human judgment.

## Scope

Update:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

Create if needed:

```text
.agentctl/journal/.gitkeep
```

Do not edit product code.

## Required Commands

Add:

```bash
scripts/agentctl.sh next
scripts/agentctl.sh work
scripts/agentctl.sh work <task-id>
scripts/agentctl.sh work --until-blocked
```

Support numeric task IDs:

```bash
scripts/agentctl.sh work 033
```

Optional flags:

```bash
scripts/agentctl.sh work --max-fix-attempts 2
scripts/agentctl.sh work --until-blocked --max-tasks 5
scripts/agentctl.sh work --dry-run
```

If parsing all optional flags is too much, implement the core commands first and document the remaining flags as future work.

## Command Semantics

### `next`

Print the next recommended action without mutating anything.

Rules:

1. If any task has a latest review verdict of `REQUEST_CHANGES`, print:

```bash
scripts/agentctl.sh fix <task-id>
```

2. If any task has latest review verdict `REJECT`, print that it needs human decision.

3. If any task has latest review verdict `BLOCKED`, print the blocker summary.

4. If any task worktree is dirty/uncommitted, print the worktree path and say to finish, commit, or clean it.

5. If a ready task exists, print:

```bash
scripts/agentctl.sh work <task-id>
```

6. If no ready tasks exist, print:

```text
No ready tasks.
```

7. If blocked tasks exist, print them separately.

`next` must not mutate files, branches, queue statuses, or worktrees.

### `work`

Run exactly one full lifecycle for the next ready task.

Equivalent to:

```bash
scripts/agentctl.sh run <task-id>
scripts/agentctl.sh review <task-id>
scripts/agentctl.sh complete <task-id>
```

but with guardrails and automatic fixes.

### `work <task-id>`

Run the lifecycle for the specified task if it is ready.

If the task is not ready, print why and exit non-zero.

### `work --until-blocked`

Keep processing ready tasks one at a time until one of the stop conditions occurs.

Default maximum tasks for `--until-blocked` should be conservative, e.g.:

```text
10
```

If max-task parsing is not implemented, document that it currently runs until no ready tasks or until blocked.

## Lifecycle

For each selected task:

### Stage 1 — Run

Run:

```bash
scripts/agentctl.sh run <task-id>
```

After it returns, inspect the task worktree.

The harness must stop if:

```text
- the run command failed
- the task worktree is dirty
- the task branch has no commit relative to main
```

If stopped, print:

```text
Stopped: task run did not produce a clean committed result.

Worktree:
  <path>

Next:
  cd <path>
  git status
  run verification
  git add ...
  git commit ...
```

Do not proceed to review if the task worktree is dirty or uncommitted.

### Stage 2 — Review

Run:

```bash
scripts/agentctl.sh review <task-id>
```

Then read the latest review artifact from:

```text
.agentctl/reviews/<task-id>.md
```

Extract the structured verdict.

Allowed verdicts:

```text
APPROVE
APPROVE_WITH_NOTES
REQUEST_CHANGES
REJECT
BLOCKED
```

If no review artifact exists or no valid verdict is found, stop:

```text
Stopped: review did not produce a structured verdict.
```

### Stage 3 — Auto-fix loop

If verdict is:

```text
APPROVE
APPROVE_WITH_NOTES
```

proceed to completion.

If verdict is:

```text
REQUEST_CHANGES
```

automatically run:

```bash
scripts/agentctl.sh fix <task-id>
```

Then rerun:

```bash
scripts/agentctl.sh review <task-id>
```

Repeat until either:

```text
- verdict becomes APPROVE or APPROVE_WITH_NOTES
- max fix attempts is reached
- fix command fails
- task worktree is dirty/uncommitted after fix
- review returns REJECT or BLOCKED
```

Default max fix attempts:

```text
2
```

If max attempts are reached, stop and print:

```text
Stopped: max fix attempts reached for <task-id>.

Latest review:
  .agentctl/reviews/<task-id>.md

Worktree:
  <path>
```

Do not auto-fix:

```text
REJECT
BLOCKED
```

These require human judgment.

### Stage 4 — Complete

If final verdict is:

```text
APPROVE
APPROVE_WITH_NOTES
```

run:

```bash
scripts/agentctl.sh complete <task-id>
```

If completion fails, stop and print the completion failure reason.

If completion succeeds, print newly ready tasks and continue if `--until-blocked` was provided.

## Journaling

Every `work` invocation must write a journal file.

Create directory:

```text
.agentctl/journal/
```

Journal files should be gitignored except `.gitkeep`.

Suggested path:

```text
.agentctl/journal/<timestamp>-<task-id>.md
```

Example:

```text
.agentctl/journal/2026-05-23T123456Z-033-frontend-workflow-language.md
```

The journal must record:

```text
task id
task title
branch
worktree path
main commit at start
selected command
start time
end time
run command result
review artifacts created
review verdicts
required fixes summaries
fix attempts
verification commands observed
commits created
merge commit if any
completion result
stop reason if stopped
```

The journal should be append-only for that run.

Do not commit individual journal files.

Commit only:

```text
.agentctl/journal/.gitkeep
```

and ensure `.gitignore` ignores:

```text
.agentctl/journal/*
!.agentctl/journal/.gitkeep
```

## Stop Conditions

`work` and `work --until-blocked` must stop for:

```text
no ready tasks
run failed
task worktree dirty after run
task branch has no commit after run
review missing artifact
review missing valid verdict
REQUEST_CHANGES after max fix attempts
REJECT
BLOCKED
fix failed
task worktree dirty after fix
verification failed
merge conflict
complete failed
human permission required
```

Every stop must print:

```text
Stopped: <reason>

Task:
  <task-id>

Worktree:
  <path>

Journal:
  <journal-path>

Next:
  <suggested command>
```

## Safety Rules

Do not push.

Do not skip review.

Do not skip verification.

Do not continue after a failed command.

Do not continue after a dirty task worktree.

Do not continue after `REJECT` or `BLOCKED`.

Do not auto-fix `REJECT` or `BLOCKED`.

Do not auto-resolve merge conflicts.

Do not auto-delete worktrees.

Do not run `git reset --hard`.

Do not run broad `git clean`.

Do not modify product code.

## Output Requirements

Output should be readable and explicit.

Example success flow:

```text
Selected task: 033-frontend-workflow-language

[1/4] Run
  PASS task branch has committed changes

[2/4] Review
  Verdict: REQUEST_CHANGES
  Required fixes:
    - Add missing test for runNeedsImport

[3/4] Fix attempt 1/2
  PASS fix committed

[2/4] Review
  Verdict: APPROVE

[4/4] Complete
  PASS merged branch
  PASS updated queue status

Done: 033-frontend-workflow-language

Newly ready:
  034-frontend-job-workspace-stepper
  038-frontend-settings-cards

Journal:
  .agentctl/journal/...
```

Example stopped flow:

```text
Stopped: review returned BLOCKED.

Task:
  034-frontend-job-workspace-stepper

Reason:
  Verification did not run.

Next:
  scripts/agentctl.sh fix 034
```

## Interaction With Review Verdicts

This task depends on task 040.

If structured review verdicts are not present, `work` must stop after review and print:

```text
Structured review verdict support not available.
Inspect the review manually, then run complete if appropriate.
```

Do not guess from free-form review text.

## Acceptance Criteria

- `scripts/agentctl.sh next` prints the next recommended action without mutating state.
- `scripts/agentctl.sh work --help` works.
- `scripts/agentctl.sh work <ready-task-id>` runs one task lifecycle.
- `scripts/agentctl.sh work --until-blocked` loops over ready tasks and stops with a clear reason.
- `work` reads structured review artifacts from task 040.
- `work` auto-runs `fix` for `REQUEST_CHANGES`.
- `work` limits automatic fix attempts.
- `work` refuses to auto-fix `REJECT` and `BLOCKED`.
- `work` writes a journal under `.agentctl/journal/`.
- Journal files are gitignored except `.gitkeep`.
- Numeric task IDs work:

```bash
scripts/agentctl.sh work 033
```

- Existing commands still work:
  - `status`
  - `ready`
  - `run`
  - `review`
  - `fix`
  - `complete`
  - `doctor`
  - `plan --help`

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh doctor
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh next
scripts/agentctl.sh work --help
```

If dry-run is implemented:

```bash
scripts/agentctl.sh work --dry-run
```

Add a safe synthetic review-artifact test if practical:

1. Create a temporary review artifact with `REQUEST_CHANGES`.
2. Verify `next` recommends `fix <task-id>`.
3. Replace with `APPROVE`.
4. Verify `work --dry-run` would proceed to completion.

Do not leave misleading synthetic review artifacts behind.

Do not run a destructive full `work --until-blocked` test on real product tasks unless explicitly safe.

## Documentation

Update `docs/contracts/agent_orchestration.md` to document:

```text
next
work
work <task-id>
work --until-blocked
auto-fix behavior
max fix attempts
journal files
stop conditions
manual recovery steps
```

Update `agent_tasks/planning_guidelines.md` to state that the normal operator flow is now:

```bash
scripts/agentctl.sh work --until-blocked
```

and that individual `run` / `review` / `fix` / `complete` commands remain available for manual intervention.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add agentctl work autofix and journal
```

Do not push.
