# Task 013: Add Agent Planner Command

## Goal

Add a planner mode to `scripts/agentctl.sh` so future implementation task packs can be generated from high-level goals instead of being manually written one task at a time.

The planner should support:

1. local planning through Claude Code
2. optional Ultraplan handoff when the user explicitly asks for it

This task improves the agent workflow. Do not implement product features.

## Background

Read:

```text
docs/contracts/agent_orchestration.md
agent_tasks/queue.yaml
scripts/agentctl.sh
docs/product_requirements.md
docs/architecture.md
docs/adr/*.md
docs/contracts/*.md
```

## Scope

Update:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
```

Create if useful:

```text
agent_tasks/planning_guidelines.md
```

Create if needed:

```text
.agent_plans/.gitkeep
```

Update `.gitignore` so temporary planning outputs are not accidentally committed unless explicitly promoted.

## Required Commands

Add:

```bash
scripts/agentctl.sh plan "<high-level goal>"
scripts/agentctl.sh plan --ultraplan "<high-level goal>"
scripts/agentctl.sh plan --help
```

## Local Planner Behavior

`plan "<high-level goal>"` should run a local Claude Code planning task.

The local planner should:

1. Accept a high-level goal as a string.
2. Read the current queue state from `agent_tasks/queue.yaml`.
3. Read the architecture docs, ADRs, contracts, and product requirements.
4. Create one or more scoped task markdown files under `agent_tasks/`.
5. Update `agent_tasks/queue.yaml` with matching entries.
6. Preserve existing completed task history.
7. Avoid rewriting existing task files unless explicitly instructed.
8. Avoid product implementation.

Generated task files must include:

```text
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

Generated queue entries must include:

```yaml
id:
title:
file:
branch:
worktree:
status:
depends_on:
verification:
allowed_paths:
```

Generated task statuses may be:

```text
planned
ready
blocked
```

The planner must not mark generated tasks as `done`.

## Ultraplan Mode

`plan --ultraplan "<high-level goal>"` should not assume fully automated Ultraplan execution.

It should create an Ultraplan-ready prompt file under:

```text
.agent_plans/
```

Use a timestamped filename such as:

```text
.agent_plans/2026-05-22-120000-ultraplan.md
```

The generated Ultraplan prompt should include:

- the high-level goal
- current completed tasks from `queue.yaml`
- current ready/planned/blocked tasks from `queue.yaml`
- references to relevant docs, ADRs, and contracts
- task-file output requirements
- queue-entry output requirements
- instruction not to implement product code
- instruction to preserve completed task history
- instruction to keep tasks small and path-scoped

After creating the prompt file, print instructions similar to:

```text
Open Claude Code and run /ultraplan using .agent_plans/<file>.md.
After reviewing and approving the plan, save the generated task files under agent_tasks/ and update queue.yaml.
```

If the local Claude Code version supports invoking Ultraplan directly, the script may print the suggested `/ultraplan` command, but it must keep the file-based manual handoff as the reliable fallback.

## Planner Prompt Requirements

The local planner prompt should clearly say:

```text
You are a planning agent, not an implementation agent.

Create scoped implementation task files and queue entries only.

Do not implement product code.

Prefer several small tasks over one large task.

Respect ADRs and contracts.

Preserve completed queue history.

Do not change product direction.

Do not mark new tasks as done.

Keep allowed_paths narrow and non-overlapping where possible.
```

## Safety Rules

The planner may edit only:

```text
agent_tasks/**
docs/contracts/agent_orchestration.md
.agent_plans/**
.gitignore
```

The planner must not edit:

```text
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

The planner must not implement backend, frontend, extension, runtime prompt, or resume-generation logic.

## Documentation Updates

Update `docs/contracts/agent_orchestration.md` to document:

- the `plan` command
- the `plan --ultraplan` mode
- planner vs builder vs reviewer roles
- generated task file requirements
- generated queue entry requirements
- safety boundaries for planning

## Implementation Notes

Prefer reusing existing queue parsing helpers in `scripts/agentctl.sh`.

Do not introduce heavy dependencies.

If the script needs to parse YAML beyond existing helpers, use the same strategy already used by `agentctl.sh`.

Keep `plan --ultraplan` deterministic: it should create a prompt file and print the next manual step.

## Out of Scope

Do not implement product features.

Do not implement Gmail.

Do not implement autopilot.

Do not implement automatic merging.

Do not change existing task statuses unless needed for this task's own queue entry.

Do not rewrite completed task entries.

## Acceptance Criteria

- `scripts/agentctl.sh plan --help` works.
- `scripts/agentctl.sh plan --ultraplan "Add Gmail response tracking"` creates an Ultraplan-ready prompt file under `.agent_plans/`.
- The generated Ultraplan prompt includes current queue context and task-generation instructions.
- `scripts/agentctl.sh plan "Add a placeholder future task for Gmail response tracking"` can create scoped task markdown and queue entries, without touching product code.
- Existing commands still work:
  - `list`
  - `status`
  - `ready`
  - `run`
  - `review`
  - `sync`
  - `complete`

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh list
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh plan --help
scripts/agentctl.sh plan --ultraplan "Add Gmail response tracking"
```

If testing local planner behavior, use a harmless placeholder planning goal:

```bash
scripts/agentctl.sh plan "Add a placeholder future task for Gmail response tracking"
```

If this creates placeholder tasks, they must be scoped and queued. Do not implement product code.

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Add agent planner command
```

Do not push.
