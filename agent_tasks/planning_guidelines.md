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
  builder's commit and reports on scope, ADR compliance, tests, overbuild, and
  unrelated changes. Default permission mode is read-only.

Planners must not perform builder or reviewer work in the same session.

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

## Preserving completed history

The planner must not modify any existing queue entry whose status is `done`.
The completed queue is the project's history; rewriting it is forbidden even
to clean up wording.

If a planned task is superseded, write a new task that explicitly references
the superseded id in its Background section, and leave the original entry
intact (mark it `blocked` only if it must not be dispatched).

## Local vs. Ultraplan modes

- `scripts/agentctl.sh plan "<goal>"` launches Claude Code locally and the
  planner writes files directly. The operator reviews the diff before
  committing.
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

Verification commands must run from the repository root.

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
pytest
```


