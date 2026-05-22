# Task 011: Evaluation Harness

## Goal

Add a small evaluation harness that runs reproducible checks against the
Claude run directory writer and the resume tailoring prompt, so future
prompt or input changes can be regression-tested without invoking real
Claude Code.

The harness operates on fixtures and on the deterministic parts of the
run-writer pipeline. It does not call the Claude API.

## Background

Read:

- `docs/contracts/claude_run_directory.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/adr/006-candidate-context-as-source-material.md`
- `runtime_prompts/resume_tailoring.md`
- `agent_tasks/006-run-directory-writer.md`

## Scope

Under `evals/`:

- `fixtures/` — at least two job-description fixtures (a clear match and a
  weak/mismatched one) plus a stub master resume and stub evidence bank
- `harnesses/` — Python harness modules that:
  - exercise `create_run_directory(...)` against the fixtures and assert
    the run directory layout, expected files, and that
    `prompt_hash`/`input_hash` are stable across two runs
  - lint the rendered `tailoring_prompt.md` against required sections
    (Inputs, Required Outputs, Evidence Rules, Forbidden Edits, Claim
    Audit) — string presence checks, no semantic claims
  - check that `runtime_prompts/resume_tailoring.md` references every
    file listed under "Input Files" in the run directory contract
- `evals/README.md` describing how to add a new fixture and how to run the
  harness
- pytest tests that drive the harness and run as part of the existing
  `pytest` command

## Allowed files

- `evals/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed)

## Forbidden files

- `backend/**` (except importing the public run-writer entry point — do
  not modify backend code)
- `extension/**`
- `frontend/**`
- `runs/**`
- `runtime_prompts/**`
- `candidate_context/**` (read only via fixtures, do not modify)
- `docs/**`
- Other `agent_tasks/*.md`

## Out of scope

- Calling real Claude Code or any LLM API.
- Evaluating resume quality semantically (no LLM-judge here).
- Performance benchmarking.
- CI configuration changes (a follow-up task can wire this into CI).
- Modifying the run-writer module — if the harness needs new hooks,
  prefer a separate task to add them.

## Acceptance criteria

- Running `pytest` from the repo root runs both backend tests and the
  eval harness.
- Each fixture produces a stable `input_hash` on two consecutive runs.
- The prompt-lint check fails loudly if a required section is removed
  from `runtime_prompts/resume_tailoring.md` (verified by a test that
  monkeypatches the prompt text in a tmp dir).
- The contract-reference check fails loudly if the runtime prompt drops
  one of the input files listed in the contract.
- No fixtures contain real personal data; all are synthetic.

## Verification

```bash
pytest
```

## Git commit message

```text
Add evaluation harness
```

Do not push.
