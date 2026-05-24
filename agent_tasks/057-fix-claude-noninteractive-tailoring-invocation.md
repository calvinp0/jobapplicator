# Task 057: Fix Claude Non-Interactive Tailoring Invocation

## Goal

Fix the backend Claude tailoring worker so resume generation runs as a non-interactive backend job.

Current observed run log:

```text
$ claude input/tailoring_prompt.md  (cwd=/home/calvin/code/jobapply/runs/<run_id>)
Let me know which direction — and if it's #1, I'd want to first peek at what's in input/...
Claude Code process exited with code 0
validating output files
missing expected output file: output/tailored_resume.docx
missing expected output file: output/tailored_resume.md
missing expected output file: output/change_log.md
missing expected output file: output/claim_audit.md
marking run failed
```

This means Claude Code is acting like an interactive assistant instead of executing the tailoring contract.

The worker must invoke Claude in a non-interactive mode where it reads the tailoring prompt and writes the required output files without asking the user what to do.

Do not change frontend UI.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/tests/test_claude_worker.py
runtime_prompts/resume_tailoring.md
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
```

Also inspect the local Claude CLI help/output if needed:

```bash
claude --help
```

The implementation should use the actual CLI behavior available in this environment rather than guessing.

## Current Problem

The backend currently launches Claude roughly as:

```text
claude input/tailoring_prompt.md
```

with:

```text
cwd=<run_dir>
```

This is not sufficient. Claude responds conversationally and asks what the user wants, instead of treating the prompt file as a non-interactive instruction contract.

## Required Behavior

The worker must launch Claude so that:

```text
- Claude receives the full contents of input/tailoring_prompt.md as the task prompt
- Claude runs non-interactively
- Claude does not ask clarifying questions
- Claude does not wait for user input
- Claude writes required files under output/
- Claude exits after writing the files or after writing/logging a concrete failure
```

The required output files remain:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

## Invocation Requirements

Determine the correct local Claude CLI invocation.

Acceptable approaches include, depending on `claude --help`:

```text
claude --print <prompt text>
claude -p <prompt text>
cat input/tailoring_prompt.md | claude --print
claude --print "$(cat input/tailoring_prompt.md)"
```

Use the actual supported syntax for this installed Claude Code version.

Do not use an invocation that merely passes the prompt file path as a conversational argument unless the CLI explicitly documents that as prompt-file execution.

The run log should record the command shape without dumping the full prompt:

```text
jobapply: launching Claude Code in non-interactive mode
jobapply: prompt file=input/tailoring_prompt.md
jobapply: cwd=<run_dir>
jobapply: permission mode=<mode>
```

Do not print secrets.

## Prompt Contract Update

Update `runtime_prompts/resume_tailoring.md` so the runtime prompt explicitly says:

```text
You are running inside a non-interactive backend job.
Do not ask clarifying questions.
Do not wait for user input.
Make a best effort using the provided input files.
Write the required output files exactly as specified.
If required input is missing, write a clear failure note to output/claim_audit.md and still write the other required files if possible.
```

The prompt should also say:

```text
Do not respond with options such as "do you want me to execute, explain, critique, or something else".
Your task is always to generate the tailored resume outputs.
```

## Failure Handling

If Claude exits with code `0` but asks a clarifying question and produces no output files, the worker should still mark the run as failed due to missing outputs, as task 049 already requires.

This task should not remove output validation.

## Tests

Update backend tests so they prove:

1. The worker reads the prompt file contents and passes them to the Claude invocation, rather than only passing the prompt file path.
2. The worker uses non-interactive mode / print mode / stdin mode according to the chosen CLI syntax.
3. The fake Claude binary can assert it received prompt text containing the non-interactive instruction.
4. A fake Claude binary that writes all four files results in `completed`.
5. A fake Claude binary that writes no files results in `failed`.
6. The run log records non-interactive launch mode.

Do not require the real Claude binary in tests.

## Acceptance Criteria

- Backend worker no longer invokes Claude in a way that causes it to ask what the user wants.
- Runtime prompt explicitly forbids clarifying questions.
- Worker passes the prompt contents to Claude in the correct non-interactive mode.
- Successful fake Claude writes all four outputs and run becomes `completed`.
- Missing outputs still make run `failed`.
- Run log clearly shows non-interactive launch mode.
- Backend tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_run_directory.py
pytest
```

Manual verification:

1. Start backend.
2. Open a job.
3. Click Generate draft.
4. Confirm run log does not contain:
   - "Let me know which direction"
   - "Could you clarify"
   - "Do you want me to..."
5. Confirm Claude writes output files or fails with a concrete non-interactive error.
6. Confirm successful run imports into a new draft.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix non-interactive Claude tailoring invocation
```

Do not push.
