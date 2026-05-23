# Task 019: Add Numeric Task ID Shortcuts

## Goal

Allow `scripts/agentctl.sh` commands to accept short numeric task references such as `014` or `14` instead of requiring the full task ID.

For example:

```bash
scripts/agentctl.sh run 014
scripts/agentctl.sh review 014
scripts/agentctl.sh complete 014
scripts/agentctl.sh sync 014
```

should resolve to the queue entry whose ID starts with `014-`.

This improves usability of the agent orchestration harness. Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
agent_tasks/queue.yaml
docs/contracts/agent_orchestration.md
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

Add task reference resolution for all commands that accept a task ID:

```bash
run
run-interactive
review
sync
complete
```

The resolver should support:

```text
014
14
014-backend-application-submit-and-open-file
```

Resolution rules:

1. If the input exactly matches an existing task ID, use it.
2. If the input is all digits:
   - normalize it to a 3-digit prefix using zero-padding
   - `14` becomes `014`
   - `8` becomes `008`
3. Match the normalized numeric prefix against task IDs of the form `<NNN>-...`.
4. If exactly one task matches, use that full task ID.
5. If zero tasks match, fail clearly.
6. If multiple tasks match, fail clearly and list matches.

Examples:

```bash
scripts/agentctl.sh run 014
```

should print or internally resolve:

```text
014-backend-application-submit-and-open-file
```

## User-Facing Output

When a short ID is resolved, print a short line such as:

```text
Resolved task 014 -> 014-backend-application-submit-and-open-file
```

Do not print this for exact full-ID matches unless the existing script style prefers it.

## Out of Scope

Do not change queue structure.

Do not rename existing task IDs.

Do not implement product features.

Do not change backend, frontend, extension, runtime prompts, or candidate context.

## Acceptance Criteria

These commands work if the corresponding task exists in `queue.yaml`:

```bash
scripts/agentctl.sh run --dry-run 014
```

If `run --dry-run` does not exist, test with a non-mutating command or add a safe resolver test command.

At minimum, verify:

```bash
scripts/agentctl.sh sync 014
scripts/agentctl.sh review 014 --dry-run
scripts/agentctl.sh complete 014 --dry-run
```

If `review --dry-run` does not exist, do not add it unless simple. Instead verify the resolver through commands that already support dry-run or safe behavior.

Also verify existing full IDs still work:

```bash
scripts/agentctl.sh ready
scripts/agentctl.sh status
scripts/agentctl.sh sync 014-backend-application-submit-and-open-file
```

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
scripts/agentctl.sh status
scripts/agentctl.sh ready
scripts/agentctl.sh sync 014
scripts/agentctl.sh complete 014 --dry-run
```

## Git

After changes:

1. Run verification.
2. Stage changed files.
3. Commit locally with:

```text
Add numeric task ID shortcuts
```

Do not push.
