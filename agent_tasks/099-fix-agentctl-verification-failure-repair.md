# Task 099: Teach agentctl fix to Repair Verification Failures

## Goal

Update the agent harness so `scripts/agentctl.sh fix <task>` can repair failed verification runs, not only failed review verdicts.

Current observed behavior:

```text
verification failed; not marking 097-add-firefox-extension-support done
```

Then:

```text
scripts/agentctl.sh fix 97
Resolved task 97 -> 097-add-firefox-extension-support
error: latest review verdict for 097-add-firefox-extension-support is APPROVE; nothing to fix.
error: Run 'scripts/agentctl.sh complete 097-add-firefox-extension-support' instead.
```

This is wrong when verification failed.

If review is approved but verification failed, `fix` should launch a repair agent using the verification failure log.

Do not change application features in this task.
Do not change Gmail behavior except in test fixtures if needed by the repair prompt.
Do not change browser extension behavior.
Do not bypass tests.

## Background

The agent system currently has plan/run/review/fix/complete behavior.

But verification can fail after review approval.

In that case, the task is not complete and `fix` should be able to act.

Example failure:

```text
Task:
  097-add-firefox-extension-support

Review:
  APPROVE

Verification:
  FAILED

Failing command:
  pytest

Failing test:
  backend/tests/test_gmail_application_search.py::test_search_updates_email_status_to_email_received

Failure:
  AssertionError: assert 'needs_review' == 'email_received'
```

The harness should not tell the user to run `complete` while verification is failing.

## Inspect

Inspect:

```text
scripts/agentctl.sh
.agentctl/
agent_tasks/queue.yaml
docs/contracts/agent_orchestration.md
```

Search:

```bash
rg "fix|review verdict|APPROVE|verification failed|complete command failed|journal|pytest" scripts docs .agentctl agent_tasks
```

Use the existing harness architecture.

## Required Behavior

When running:

```bash
scripts/agentctl.sh fix <task>
```

the harness should decide what to fix in this order:

```text
1. If latest verification failed, run a verification-failure repair.
2. Else if latest review verdict is not approved, run review-feedback repair.
3. Else if task is incomplete for another known reason, show actionable reason.
4. Else say nothing to fix and allow complete.
```

Verification failure must take precedence over review approval.

## Verification Failure Detection

Detect latest verification failure from existing state.

Possible sources:

```text
latest journal
task worktree logs
agentctl state files
stored verification result
command exit code records
```

Use the actual current harness data.

The detection should identify:

```text
task id
worktree path
failing verification command
exit code
relevant log excerpt
journal path
```

If exact failing test can be extracted, include it.

## Repair Prompt Requirements

When verification failed, `fix` should launch the agent with a prompt that includes:

```text
Task id
Task file
Worktree path
Failing verification command
Failure excerpt
Relevant journal path
Instruction to fix the failure in the existing worktree
Instruction to run targeted test first
Instruction to run full verification after targeted fix
Instruction not to bypass or weaken tests unless the test expectation is obsolete and the reason is documented
```

Example repair prompt:

```text
Task 097 passed review but failed verification.

Fix the verification failure in the existing worktree:
<worktree>

Failing command:
pytest

Failure excerpt:
...
AssertionError: assert 'needs_review' == 'email_received'

Determine whether the code is wrong or the test expectation is obsolete.
Make the smallest correct change.
Run the targeted failing test first.
Then run the task verification commands.
Do not mark the task complete until verification passes.
```

## CLI UX Requirements

If verification failed, `fix` should print:

```text
Latest review verdict is APPROVE, but verification failed.
Launching verification-failure repair agent.
```

It should not print:

```text
nothing to fix
Run complete instead
```

unless verification is passing.

## Completion Guard

`complete` should continue refusing to complete a task if verification failed.

If complete currently suggests wrong next steps, update it to say:

```text
Verification failed. Run:
scripts/agentctl.sh fix <task>
```

instead of suggesting completion.

## Journal Requirements

Record in the task journal:

```text
verification_failure_fix_started
failing_command
failure_excerpt
repair_started_at
repair_completed_at
post_fix_verification_result
```

Use existing journal format.

## Tests

Add or update harness tests if available.

If there are no harness tests, add shell-level tests or documented manual tests.

Tests should prove:

1. `fix <task>` runs review repair when review failed and verification did not run/pass.
2. `fix <task>` runs verification repair when review approved but verification failed.
3. Verification failure takes precedence over review approval.
4. `fix <task>` includes failing command in repair prompt.
5. `fix <task>` includes failure excerpt in repair prompt.
6. `fix <task>` does not suggest `complete` while verification is failed.
7. `complete <task>` refuses completion after verification failure and suggests `fix`.
8. Existing approved-and-verified task still says nothing to fix.

If automated tests are too hard, add a reproducible manual harness test in docs.

## Acceptance Criteria

- `scripts/agentctl.sh fix <task>` can repair verification failures.
- Review approval no longer blocks fix when verification failed.
- Failing command and log excerpt are passed to the repair agent.
- `complete` points to `fix` after verification failure.
- Task journal records verification repair attempts.
- Existing review-fix behavior still works.
- Tests or manual verification pass.

## Verification

Run:

```bash
bash -n scripts/agentctl.sh
```

Run any existing harness tests.

Manual verification:

1. Use or create a task worktree with:
   - review verdict APPROVE
   - failing verification command
2. Run:

```bash
scripts/agentctl.sh fix <task>
```

3. Confirm it does not say:

```text
nothing to fix
```

4. Confirm it launches a repair using the verification failure.
5. Confirm after repair, verification can be rerun.
6. Confirm `complete` works only after verification passes.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Teach agentctl fix to repair verification failures
```

Do not push.
