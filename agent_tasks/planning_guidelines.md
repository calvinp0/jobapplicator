# Planning Guidelines

This document is the contract for the agent planner (`scripts/agentctl.sh plan`
and `scripts/agentctl.sh plan --ultraplan`). It is referenced from the planner
prompts so a planning agent and a human reviewer can apply the same rules.

It complements `docs/contracts/agent_orchestration.md`, which defines the
broader task / queue / worktree contract. When the two disagree, the
orchestration contract wins; this file fills in the planner-specific gaps.

## Roles

The harness has three roles. Each one is a separate Claude Code session.

- **Planner** (this document). Reads the queue, docs, ADRs, and contracts.
  Produces scoped task files and queue entries. Does not implement product
  code. Does not push or merge.
- **Builder**. Invoked by `scripts/agentctl.sh run <task-id>`. Implements a
  single task within its `allowed_paths`. Commits locally with the task's
  required commit message. Does not push.
- **Reviewer**. Invoked by `scripts/agentctl.sh review <task-id>`. Reads the
  builder's commit and writes a structured review artifact at
  `.agentctl/reviews/<task-id>.md` ending in exactly one verdict (see
  "Review verdict semantics" below).
- **Fixer**. Invoked by `scripts/agentctl.sh fix <task-id>` when a review
  returns `REQUEST_CHANGES`, `REJECT`, or `BLOCKED`. Reads the latest
  review artifact and addresses only its `Required fixes`, staying
  within the task's `allowed_paths`.

Planners must not perform builder, reviewer, or fixer work in the same
session.

## What the planner may edit

```
agent_tasks/**
docs/contracts/agent_orchestration.md
.agent_plans/**
.gitignore
```

## What the planner must not edit

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

If a high-level goal seems to require changes to a forbidden path (for
example, the goal implies an ADR amendment, or a product-requirements
update), the planner must instead propose a new task whose `allowed_paths`
cover that path, and let the builder make the change under review.

## Required task file structure

Every generated task markdown file must include these sections, in order:

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

- **Goal**: one paragraph stating what the task accomplishes and why.
- **Background**: an explicit list of docs the builder must read first
  (architecture, ADRs, contracts, product requirements, prior task files).
- **Scope**: what to change. Prefer bullet points. Be specific about files
  and behaviors.
- **Allowed files**: globs the builder may touch. Must match the
  `allowed_paths` of the matching queue entry.
- **Forbidden files**: globs the builder must not touch. At minimum, include
  the forbidden paths the planner itself is bound by when those would be
  out of scope for the builder task.
- **Out of scope**: features or refactors the builder must defer to a later
  task.
- **Acceptance criteria**: bullet list of observable conditions that must hold
  when the task is complete.
- **Verification**: exact shell commands the builder must run before
  committing. These must also appear in the queue entry's `verification`
  list.
- **Git instructions**: the exact commit message the builder must use, and
  the explicit `Do not push.` reminder.

## Required queue entry fields

Every generated `agent_tasks/queue.yaml` entry must include:

```yaml
- id: "<NNN>-<slug>"
  title: "<human-readable summary>"
  file: "agent_tasks/<NNN>-<slug>.md"
  branch: "agent/<NNN>-<slug>"          # or "main" for in-place tasks
  worktree: "agent-<NNN>-<slug>"        # or "main" for in-place tasks
  status: "planned" | "ready" | "blocked"
  depends_on:
    - "<other-task-id>"
  verification:
    - "<shell command>"
  allowed_paths:
    - "<glob>"
```

- **id**: continue the existing numeric sequence in `queue.yaml`. Never
  reuse a number.
- **status**: planners may only emit `planned`, `ready`, or `blocked`.
  Planners must never emit `done`, `running`, `review`, or `failed`.
- **depends_on**: list the task ids whose completion the new task assumes.
  Use the *most recent* relevant id in each dependency line, not every
  ancestor.
- **allowed_paths**: keep narrow. Sibling tasks should ideally not overlap
  in their writeable areas, so two tasks from the same plan can run in
  parallel without conflict.

## Status semantics for planner output

- `planned` — the task is well-described but not yet ready to dispatch
  (for example, it depends on another planned task, or a design decision is
  pending).
- `ready` — dependencies are satisfied (or none exist) and the operator can
  dispatch the task immediately with `scripts/agentctl.sh run <id>`.
- `blocked` — explicitly blocked on external work. The task file must
  describe the blocker.

`scripts/agentctl.sh work` runs a promotion sweep before selecting a task:
any `planned` task whose `depends_on` are all `done` is promoted to `ready`
and the queue update is committed. This means a planner that leaves the head
of a new pack `planned` (for example because it was authored while a
dependency was still in flight) self-heals once that dependency lands — the
operator does not have to hand-edit statuses. Marking the head `ready` when
its dependencies are already `done` is still preferred, but no longer
required for `work` to pick it up.

## Preserving completed history

The planner must not modify any existing queue entry whose status is `done`.
The completed queue is the project's history; rewriting it is forbidden even
to clean up wording.

If a planned task is superseded, write a new task that explicitly references
the superseded id in its Background section, and leave the original entry
intact (mark it `blocked` only if it must not be dispatched).

## Local vs. Ultraplan modes

- `scripts/agentctl.sh plan "<goal>"` launches Claude Code locally and the
  planner writes files directly. When the session finishes the harness
  prints the diff and then commits the planner's output automatically
  (commit message `Plan: <goal>`), staging only the planner's allowed paths.
  This hands a ready-to-dispatch pack to `work` with no manual git step; the
  operator can still amend or revert the commit after review.
- `scripts/agentctl.sh plan --ultraplan "<goal>"` writes an Ultraplan-ready
  prompt under `.agent_plans/`, but does not invoke Claude Code. The
  operator opens Claude Code, runs `/ultraplan` against the generated
  prompt, reviews the proposed plan, and only then saves the task files
  and queue entries.

`.agent_plans/` is gitignored so draft prompts and intermediate plans do not
accumulate in history. Promote a plan by copying its scoped task files into
`agent_tasks/` and committing those.

## Anti-patterns

- **One mega-task.** Prefer several small tasks with narrow `allowed_paths`
  over one task that spans many components.
- **Bundled refactors.** Do not slip refactors into a feature task. Plan a
  separate refactor task if the cleanup is worth doing.
- **Touching forbidden paths.** The planner must not edit product code,
  ADRs, or `docs/product_requirements.md` / `docs/architecture.md`. If a
  change to those is needed, propose a new builder task for it.
- **Marking new tasks `done`.** Planners do not complete work; they queue
  it.
- **Hidden dependencies.** If task B can only run after task A, list A in
  B's `depends_on`. Do not rely on operator memory.

## Verification command working directories

Verification commands must be repo-root-relative — `scripts/agentctl.sh`
runs them from the task worktree root, not from a subdirectory. Use
explicit `cd <workspace> && ...` for package-specific commands so the
working directory is unambiguous to a human reading the task file.

For frontend tasks, use:

```bash
cd frontend && npm test
cd frontend && npm run build
```

For extension tasks, use:

```bash
cd extension && npm test
cd extension && npm run build
```

For backend tasks, use:

```bash
python -m pytest
```

Prefer `python -m pytest` over a bare `pytest` so the invocation always
resolves to the active environment's pytest. The harness runs backend
verification with the JobApplicator backend interpreter (see
`resolve_backend_python` in `scripts/agentctl.sh`), prepends that
interpreter's `bin/` to `PATH`, logs `using python: <path>`, and runs a
dependency preflight (`import fastapi, pydantic, docx`) first — so
backend tests never silently run under an unrelated conda env such as
`rmg_env`. To pin a specific interpreter, set
`JOBAPPLY_BACKEND_PYTHON=/path/to/python` (or
`JOBAPPLY_BACKEND_CONDA_ENV=<env-name>`) before invoking agentctl.

The harness inspects each task's verification list and, before running
the commands, prepares the `frontend/` or `extension/` workspace if it
is referenced and `node_modules` has not yet been installed there.
Planners do not need to add an explicit `npm install` step.

## Claude permission propagation

`scripts/agentctl.sh` symlinks the main checkout's
`.claude/settings.local.json` into each task worktree (under
`<worktree>/.claude/settings.local.json`) before launching Claude for
`run`, `run-interactive`, `review`, or `sync`. This is what lets a
non-interactive task agent run routine commands (`npm install`,
`npm test`, `git add`, `git commit`) without surfacing a permission
prompt for each one.

Planners do not need to mention permission propagation in generated task
files; it is harness infrastructure. The symlinked settings file remains
gitignored at every worktree level, so it never lands in a commit.

## Review verdict semantics

Reviewers (invoked by `scripts/agentctl.sh review <id>`) write a
structured artifact at `.agentctl/reviews/<id>.md` whose front matter
must contain exactly one verdict:

```
APPROVE              The task satisfies the spec. complete may proceed.
APPROVE_WITH_NOTES   The task satisfies the spec. Notes are optional
                     follow-ups and do not block completion.
REQUEST_CHANGES      The task is close but misses required behavior,
                     acceptance criteria, verification, scope, or tests.
                     Must be fixed before completion.
REJECT               The implementation is wrong enough that it should
                     not be patched casually. Abort, reset, or rewrite.
BLOCKED              The review could not decide because verification
                     did not run, the worktree is dirty, the spec is
                     ambiguous, dependencies are missing, or the task
                     branch has no commit.
```

Mapping rules for planners writing review-related task language and for
reviewers categorizing findings:

- Minor caveats that do not affect the task's acceptance criteria are
  `APPROVE_WITH_NOTES`. Put them in `Optional notes` so they do not
  block completion.
- Missing required behavior (or missing verification, or scope drift,
  or thin/missing tests) is `REQUEST_CHANGES`. Put each item in
  `Required fixes` as a concrete, actionable bullet.
- Dirty task worktree or missing commit on the task branch is
  `BLOCKED` unless the task explicitly allows that state (e.g. a
  planning-only task with no code commits).
- Implementation that is wrong enough that patching would be reckless
  is `REJECT`. Do not soften REJECT into REQUEST_CHANGES; the operator
  needs the signal.

Planners do not need to add review-verdict guidance to every task file
— this contract covers it for the whole project. Task files only need
to specify their own acceptance criteria and verification commands
clearly enough that the reviewer can decide.

`scripts/agentctl.sh complete <id>` reads the latest artifact and
refuses to mark the task `done` on `REQUEST_CHANGES`, `REJECT`,
`BLOCKED`, or missing artifact (unless `--skip-review` is explicitly
passed for the missing-artifact case). `scripts/agentctl.sh fix <id>`
launches a follow-up Claude session that addresses only `Required
fixes`. See `docs/contracts/agent_orchestration.md` for the full flow.

## Preflight check before dispatch

`scripts/agentctl.sh doctor` performs a read-only preflight check of the
local harness environment (git state, queue.yaml, tool availability,
Claude permission settings, and node workspace readiness). Operators
should run it before dispatching a fresh batch of tasks, especially
after pulling new work — the report surfaces a missing
`frontend/node_modules`, a missing common Claude permission pattern, a
dirty main checkout, or a broken dependency in `queue.yaml` before the
first `run`. Planners do not need to reference `doctor` from generated
task files; it is purely an operator-facing diagnostic. See the Doctor
Command section in `docs/contracts/agent_orchestration.md` for the
exact checks performed.

## Normal operator flow

The normal operator dispatch flow is:

```
scripts/agentctl.sh doctor
scripts/agentctl.sh next                       # see the recommendation
scripts/agentctl.sh work --until-blocked       # drive the queue
```

`work` runs the full `run -> review -> (auto-fix on REQUEST_CHANGES) ->
complete` lifecycle, with a default cap of two auto-fix attempts per
task, and writes a journal file under `.agentctl/journal/` for every
invocation. `--until-blocked` keeps processing freshly-promoted ready
tasks until a stop condition (REJECT, BLOCKED, max fix attempts, dirty
worktree, or any subcommand failure) requires human judgment.

The individual commands remain available for manual intervention:

```
scripts/agentctl.sh run <id>        # builder only
scripts/agentctl.sh review <id>     # reviewer only
scripts/agentctl.sh fix <id>        # fixer only
scripts/agentctl.sh complete <id>   # integration only
```

Use them when you want to inspect each stage between invocations, when
recovering from a stop condition (a `REJECT` verdict, a merge conflict,
a verification regression), or when you do not want the auto-fix loop
running unattended. See the *Next Command* and *Work Command* sections
in `docs/contracts/agent_orchestration.md` for the full contract,
including the stop-condition list and the manual-recovery table.


