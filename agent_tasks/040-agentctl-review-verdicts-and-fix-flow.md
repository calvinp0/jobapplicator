# Task 040: Add Structured Review Verdicts and Fix Flow

## Goal

Make `agentctl review` actionable.

Currently reviews are free-form text. They often say things like:

```text
Approve, with minor caveats.
```

but the harness has no structured way to decide:

```text
Can this task be completed?
Should the caveat become a follow-up?
Should the same task be fixed before merge?
Should the task be rejected?
```

Add a structured review verdict system and a `fix` command so review feedback becomes part of the task workflow.

This task improves the agent orchestration harness. Do not implement product features.

## Background

Read:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
agent_tasks/queue.yaml
```

Observed workflow problem:

```text
scripts/agentctl.sh review <task-id>
```

produces useful review text, but the result is not machine-readable. `complete` does not know whether the review approved the task, requested changes, rejected it, or was blocked.

## Scope

Update:

```text
scripts/agentctl.sh
docs/contracts/agent_orchestration.md
agent_tasks/planning_guidelines.md
```

Optionally create:

```text
.agentctl/reviews/.gitkeep
```

Do not edit product code.

## Required Review Verdicts

Every review must end with exactly one structured verdict:

```text
APPROVE
APPROVE_WITH_NOTES
REQUEST_CHANGES
REJECT
BLOCKED
```

Definitions:

```text
APPROVE
  The task satisfies the spec. It may be completed.

APPROVE_WITH_NOTES
  The task satisfies the spec. Notes are optional follow-ups and do not block completion.

REQUEST_CHANGES
  The task is close but misses required behavior, acceptance criteria, verification, scope, or tests.
  It must be fixed before completion.

REJECT
  The implementation is wrong enough that it should not be patched casually.
  The operator should abort/reset/rewrite the task.

BLOCKED
  The review could not make a decision because verification did not run, the task branch is dirty,
  the task spec is ambiguous, dependencies are missing, or the branch lacks a commit.
```

## Review Artifact

`review <task-id>` must write a review artifact.

Preferred path:

```text
.agentctl/reviews/<task-id>.md
```

The file should start with a machine-readable front matter block:

```yaml
---
task_id: "033-frontend-workflow-language"
verdict: "REQUEST_CHANGES"
reviewed_at: "2026-05-23T12:34:56Z"
reviewer: "claude-code"
---
```

Then include sections:

```markdown
# Review: <task-id>

## Verdict

REQUEST_CHANGES

## Required fixes

- ...

## Optional notes

- ...

## Evidence checked

- ...

## Scope / allowed-path check

...

## Verification status

...
```

If there are no required fixes, use:

```text
None.
```

If there are no optional notes, use:

```text
None.
```

## Review Prompt Requirements

Update the review prompt built by `agentctl` so the reviewer is forced to classify findings.

The prompt must say:

```text
You must end with exactly one verdict:
APPROVE, APPROVE_WITH_NOTES, REQUEST_CHANGES, REJECT, or BLOCKED.
```

The prompt must say:

```text
A caveat that violates acceptance criteria is REQUEST_CHANGES, not APPROVE_WITH_NOTES.
A caveat that is purely optional is APPROVE_WITH_NOTES.
If verification did not run or the branch is dirty, use BLOCKED unless the task explicitly allows that state.
```

The prompt must require:

```text
Required fixes must be concrete and actionable.
Optional notes must not block completion.
Do not use vague verdicts like "conditional pass" unless mapped to one of the allowed verdicts.
```

## Complete Behavior

Update:

```bash
scripts/agentctl.sh complete <task-id>
```

so it reads the latest review artifact before completing.

Rules:

```text
APPROVE
  allow completion

APPROVE_WITH_NOTES
  allow completion

REQUEST_CHANGES
  refuse completion and print required fixes

REJECT
  refuse completion and print rejection summary

BLOCKED
  refuse completion and print blocker summary

missing review artifact
  refuse completion by default, unless --skip-review is explicitly passed
```

Add optional explicit bypass:

```bash
scripts/agentctl.sh complete <task-id> --skip-review
```

This should print a warning and require an obvious flag. If implementing this complicates parsing, omit the bypass and document that manual completion requires editing/removing the review artifact.

Do not silently complete tasks with rejected or blocked reviews.

## Fix Command

Add:

```bash
scripts/agentctl.sh fix <task-id>
```

Behavior:

1. Resolve numeric task IDs.
2. Load the latest review artifact for the task.
3. Refuse if the latest verdict is `APPROVE` or `APPROVE_WITH_NOTES`.
4. Refuse if there is no review artifact.
5. Launch Claude Code in the same task worktree.
6. Prompt Claude to address only the `Required fixes`.
7. Prompt Claude not to expand scope.
8. Prompt Claude to run the task verification commands.
9. Prompt Claude to amend the existing task commit if possible:

```bash
git commit --amend --no-edit
```

or make a small follow-up commit if amendment is not safe.

The fix prompt should include:

```text
You are fixing task <task-id> based only on the latest review.
Do not implement optional notes unless they are trivial and in-scope.
Do not edit files outside allowed_paths.
Address every required fix.
Run verification.
Commit the fix.
```

## Review Status Command

Add a lightweight command if easy:

```bash
scripts/agentctl.sh review-status <task-id>
```

It should print:

```text
task id
latest verdict
review artifact path
required fixes summary
optional notes summary
```

If this is too much, document how to inspect `.agentctl/reviews/<task-id>.md`.

## Dirty Branch / Missing Commit Handling

The review prompt and/or harness should treat these as blockers:

```text
task worktree has uncommitted changes
task branch has no commits relative to main
verification did not run
```

If these are present, the review verdict should normally be:

```text
BLOCKED
```

unless the task is explicitly a planning-only task that does not require code commits.

## Safety Rules

Do not push.

Do not auto-delete worktrees.

Do not auto-reset branches.

Do not modify product code.

Do not rewrite completed queue history.

Do not mark tasks done inside `review` or `fix`.

Do not allow `complete` to proceed on `REQUEST_CHANGES`, `REJECT`, or `BLOCKED`.

## Out of Scope

Do not implement product features.

Do not redesign the frontend.

Do not implement abort/reset worktree commands in this task.

Do not build a full review database.

Do not require external services.

## Acceptance Criteria

- `scripts/agentctl.sh review <task-id>` writes `.agentctl/reviews/<task-id>.md`.
- Review artifact contains structured front matter with `verdict`.
- Review prompt requires one of the allowed verdicts.
- `complete <task-id>` allows `APPROVE` and `APPROVE_WITH_NOTES`.
- `complete <task-id>` blocks `REQUEST_CHANGES`, `REJECT`, and `BLOCKED`.
- `complete <task-id>` blocks missing review artifact unless an explicit bypass is implemented.
- `fix <task-id>` launches Claude in the existing task worktree using the latest review artifact.
- Existing commands still work:
  - `status`
  - `ready`
  - `run`
  - `review`
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
scripts/agentctl.sh plan --help
```

Add safe dry-run or fixture-style checks if existing script structure supports them.

At minimum, manually verify with a harmless existing task or a synthetic review artifact:

```bash
mkdir -p .agentctl/reviews
cat > .agentctl/reviews/040-agentctl-review-verdicts-and-fix-flow.md <<'EOF'
---
task_id: "040-agentctl-review-verdicts-and-fix-flow"
verdict: "REQUEST_CHANGES"
reviewed_at: "2026-05-23T00:00:00Z"
reviewer: "test"
---

# Review: 040-agentctl-review-verdicts-and-fix-flow

## Verdict

REQUEST_CHANGES

## Required fixes

- Synthetic required fix for harness verification.

## Optional notes

None.
EOF
```

Then verify `complete 040 --dry-run` refuses because the verdict is `REQUEST_CHANGES`.

Replace with `APPROVE` and verify `complete 040 --dry-run` would proceed.

Do not leave synthetic review artifacts in a misleading state unless they are clearly overwritten by the real review.

## Documentation Updates

Update `docs/contracts/agent_orchestration.md` to document:

```text
review verdicts
review artifacts
complete gating
fix command
review-status command if implemented
how to handle minor caveats
how to handle rejected tasks
```

Update `agent_tasks/planning_guidelines.md` so future tasks can state:

```text
Minor caveats that do not affect acceptance criteria should be APPROVE_WITH_NOTES.
Missing required behavior should be REQUEST_CHANGES.
Dirty worktree or missing commit should be BLOCKED.
```

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add structured review verdicts and fix flow
```

Do not push.
