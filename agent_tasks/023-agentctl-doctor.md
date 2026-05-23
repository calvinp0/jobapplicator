# Task 023: Add Agent Harness Doctor Command

## Goal

Add a `doctor` command to `scripts/agentctl.sh` that checks whether the local agent harness environment is ready for non-interactive task execution.

Recent tasks exposed recurring setup problems:

- Claude Code blocked expected Bash commands without surfacing interactive approval.
- Frontend worktrees lacked `node_modules`, causing `vitest: command not found`.
- Worktree/main pollution and dirty-main states blocked completion.
- Users only discovered these problems after an agent task had already started.

The `doctor` command should detect common problems before task execution.

This task improves orchestration reliability. Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
agent_tasks/queue.yaml
```

Relevant observed issues:

```text
cd frontend && npm test
sh: line 1: vitest: command not found
```

and Claude Code reporting that `git add`, `git commit`, `npm install`, and test commands required approval without an interactive prompt.

Task 022 added workspace preparation before verification. This task adds preflight diagnostics so failures are easier to understand before dispatch.

## Scope

Update:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

Optionally update:

```text
agent_tasks/queue.yaml
```

## Required Command

Add:

```bash
scripts/agentctl.sh doctor
```

Optional task-specific form:

```bash
scripts/agentctl.sh doctor <task-id>
```

The task-specific form may be implemented if straightforward. If not, implement the global form first and document that task-specific checks are future work.

## Required Checks

`doctor` should check and print a clear PASS/WARN/FAIL report.

### Git checks

Check:

```text
main worktree path
current branch
whether main worktree is clean
whether a merge is in progress
whether configured task worktrees exist
```

If main is dirty, print:

```bash
git status --short
```

### Queue checks

Check:

```text
agent_tasks/queue.yaml exists
queue can be parsed
task IDs are unique
task files exist
statuses are valid
dependencies reference existing tasks
ready tasks have dependencies done
```

### Tool checks

Check availability of:

```text
git
python
claude
npm
pytest
```

Use `command -v`.

Do not fail if optional tools are missing unless needed by current ready tasks.

### Claude settings checks

Check whether `.claude/settings.local.json` exists.

If it exists:

- validate it as JSON using Python
- print whether it is valid
- warn if common useful permissions appear missing

Useful permission patterns to look for include:

```text
Bash(git add:*)
Bash(git commit:*)
Bash(npm install:*)
Bash(npm test:*)
Bash(npm run build:*)
Bash(pytest:*)
Bash(bash -n:*)
```

Do not print secrets or full settings contents.

### Workspace checks

If `frontend/package.json` exists:

- check whether `frontend/node_modules/.bin/vitest` exists in main
- warn if missing
- print the command to prepare it:

```bash
cd frontend && npm install
```

If `extension/package.json` exists:

- check whether `extension/node_modules` exists in main
- warn if missing
- print the command to prepare it:

```bash
cd extension && npm install
```

### Ready-task verification checks

For each ready task in `queue.yaml`, print:

```text
task id
verification commands
whether commands appear frontend/extension/backend related
whether worktree exists
```

Do not run task verification commands in `doctor`.

## Output Format

Use a readable text format, for example:

```text
Agent Harness Doctor

Git
  PASS main worktree clean
  PASS no merge in progress

Queue
  PASS queue parses
  PASS task IDs unique
  WARN task 018 ready but frontend node_modules missing

Tools
  PASS git: /usr/bin/git
  PASS claude: /usr/bin/claude
  PASS npm: /usr/bin/npm

Claude permissions
  PASS settings.local.json valid JSON
  WARN missing Bash(git commit:*)
```

Exit codes:

```text
0 = no FAIL items
1 = one or more FAIL items
```

Warnings should not make the command fail.

## Safety Rules

Do not push.

Do not run `npm install`.

Do not run `pytest`.

Do not run task verification commands.

Do not mutate files except the files in scope.

Do not print secrets.

Do not inspect `.env` files.

Do not modify product code.

## Out of Scope

Do not implement product features.

Do not fix permissions automatically.

Do not install dependencies automatically.

Do not change task statuses.

Do not change queue dependency logic.

Do not change completed task history.

## Acceptance Criteria

- `scripts/agentctl.sh doctor` runs from the repo root.
- It validates `queue.yaml`.
- It validates `.claude/settings.local.json` if present.
- It reports missing common Claude permission patterns as warnings.
- It reports frontend/extension dependency-prep warnings without installing anything.
- It exits with code 0 when there are only warnings.
- Existing commands still work:
  - `status`
  - `ready`
  - `run`
  - `review`
  - `complete`
  - `plan --help`

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh doctor
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh plan --help
```

If `doctor` returns warnings only, it should still exit 0.

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Add agent harness doctor command
```

Do not push.
