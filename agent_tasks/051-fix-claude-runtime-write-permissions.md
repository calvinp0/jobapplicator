# Task 051: Fix Claude Runtime Write Permissions

## Goal

Fix the backend Claude runtime invocation so tailored-resume generation can write the required output files non-interactively.

Current observed run log:

```text
$ claude input/tailoring_prompt.md  (cwd=/home/calvin/code/jobapply/runs/<run_id>)
The write keeps being denied...
Need write permission on output/.
```

The backend successfully creates a run and invokes Claude Code, but Claude Code cannot write:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

As a result, the run fails with:

```text
expected output file missing: output/tailored_resume.docx, output/tailored_resume.md, output/change_log.md, output/claim_audit.md
```

This task should make the runtime invocation suitable for non-interactive local generation.

Do not change frontend UI.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/routers/runs.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
runtime_prompts/resume_tailoring.md
docs/contracts/claude_run_directory.md
.claude/settings.local.json
docs/contracts/agent_orchestration.md
```

Also inspect how `scripts/agentctl.sh` launches Claude successfully for implementation tasks, especially permission mode and worktree/current-directory handling.

## Current Failure

The worker launches Claude roughly as:

```text
claude input/tailoring_prompt.md
```

with:

```text
cwd=<run_dir>
```

Claude Code then refuses to write files under:

```text
<run_dir>/output/
```

because the runtime process does not have the correct non-interactive write permission configuration.

## Required Behavior

When invoking Claude for a tailoring run, the backend worker must allow Claude to write inside the run directory only.

The allowed write scope should include:

```text
<run_dir>/output/
<run_dir>/run.log
```

The worker should not grant broad access to the whole repository unless unavoidable.

The worker must continue to use:

```text
cwd=<run_dir>
```

The worker must ensure the output directory exists before launching Claude:

```text
<run_dir>/output/
```

The worker log should include a clear command/progress line such as:

```text
jobapply: launching Claude Code with cwd=<run_dir>
jobapply: permission mode=<mode>
jobapply: output directory=<run_dir>/output
```

Do not print secrets.

## Configuration

If the project already has environment variables for Claude invocation, use them.

Inspect and preserve existing variables such as:

```text
JOBAPPLY_CLAUDE_BINARY
JOBAPPLY_CLAUDE_DRY_RUN
JOBAPPLY_CLAUDE_EXTRA_ARGS
```

Add a focused variable if needed, for example:

```text
JOBAPPLY_CLAUDE_PERMISSION_MODE=acceptEdits
```

or use `JOBAPPLY_CLAUDE_EXTRA_ARGS` if it already supports passing:

```text
--permission-mode acceptEdits
```

The default local-dev behavior should be able to generate files without manual approval.

## Safety Rules

Do not grant unrestricted writes outside the run directory if avoidable.

Do not modify `.claude/settings.local.json`.

Do not commit local Claude settings.

Do not require the user to manually approve writes during a backend run.

Do not change task harness behavior unless strictly needed.

Do not push.

## Output Contract

This task does not replace task 049.

After Claude exits, the worker must still validate required outputs:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

If files are missing, status remains `failed` with a clear `error_message`.

If files exist, status becomes `completed`.

## Tests

Update backend tests so there is coverage for:

1. Worker creates or ensures `output/` before launching Claude.
2. Worker passes the configured permission mode / extra args to the Claude command.
3. A fake Claude process can write all four output files into `output/`.
4. Missing outputs still cause `failed`.
5. Dry-run behavior still works according to the existing contract.

Do not require the real Claude binary in tests.

## Acceptance Criteria

- A local backend run no longer asks the user to approve writes to `output/`.
- Claude is launched with the intended permission mode or extra args.
- `output/` exists before Claude starts.
- A successful fake Claude invocation writes all four output files and results in `completed`.
- Missing-output fake invocation results in `failed`.
- Run log records the launch cwd, output directory, and permission mode/args without secrets.
- Backend tests pass.
- The run directory contract documents the runtime permission expectation.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py backend/tests/test_run_directory.py
pytest
```

Manual verification:

1. Start backend.
2. Open a job.
3. Click Generate draft.
4. Confirm the run log no longer says write was denied.
5. Confirm output files are written under the run directory.
6. Confirm the run reaches `completed` and then imports into a draft.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix Claude runtime write permissions
```

Do not push.
