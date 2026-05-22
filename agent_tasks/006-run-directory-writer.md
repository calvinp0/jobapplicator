# Task 006: Claude Run Directory Writer

## Goal

Implement the backend module that creates a Claude Code run directory on
disk for a given job and master resume, snapshots the required input files
from candidate context, renders the runtime prompt, computes the input
hash, and writes `metadata.json`.

This task only builds the run directory and the `ClaudeRun` row that
references it. It does not invoke Claude Code (task 007) and does not
import outputs (task 008).

## Background

Read:

- `docs/contracts/claude_run_directory.md`
- `docs/architecture.md` (Claude Code worker boundary, candidate context)
- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/adr/006-candidate-context-as-source-material.md`
- `runtime_prompts/resume_tailoring.md`
- `backend/app/models.py` and `backend/app/schemas.py` (existing models;
  the `ClaudeRun` model already exists from task 002)

## Scope

Add to `backend/app/`:

- a `run_directory.py` module exposing a `create_run_directory(job, master_resume, evidence_bank, candidate_context_root, runs_root)` style function that:
  - allocates a new `run_id` (UUID4)
  - creates `runs/<run_id>/input/`, `runs/<run_id>/output/`
  - writes `input/job_description.md` from the Job
  - writes `input/master_resume.md` from the MasterResume
  - writes `input/evidence_bank.md` from the EvidenceBank (if provided)
  - copies the candidate context files (`candidate_profile.md`,
    `project_notes.md`, `skills_inventory.md`, `tailoring_preferences.md`,
    `resume_dos_and_donts.md`) from `candidate_context/`
  - renders `input/tailoring_prompt.md` from `runtime_prompts/resume_tailoring.md`
  - computes `prompt_hash` and `input_hash` (SHA-256 of the concatenated,
    sorted-by-name input files)
  - writes `metadata.json` per the contract
- a small router or service function `POST /runs` that, given a job_id and
  master_resume_id, calls the above and creates a `ClaudeRun` row with
  `status="created"`, the hashes, and the `run_dir` path
- read-only endpoints `GET /runs` and `GET /runs/{run_id}` returning the
  `ClaudeRun` row
- pytest tests covering: directory layout matches the contract, all
  required input files exist, hashes are stable across two runs with the
  same inputs, `metadata.json` is well-formed, and a missing master resume
  errors clearly

## Allowed files

- `backend/**`
- `docs/contracts/claude_run_directory.md` (only minor clarifications if
  the implementation reveals a gap; prefer not to change it)
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed)

## Forbidden files

- `extension/**`
- `frontend/**`
- `runs/**` at commit time (the directory is runtime output; do not commit
  generated run dirs — keep `runs/.gitkeep` only)
- `runtime_prompts/**` (read only)
- `candidate_context/**` (read only)
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- Other `agent_tasks/*.md`

## Out of scope

- Invoking Claude Code (task 007).
- Validating Claude outputs or creating ResumeVersion rows (task 008).
- Approval workflow, frontend UI, or any extension changes.
- Background workers, job queues, or async execution.
- Changes to existing models from task 002 beyond what is strictly needed
  to back this feature.

## Acceptance criteria

- Calling `create_run_directory(...)` twice with identical inputs produces
  identical `prompt_hash` and `input_hash`.
- Every file listed under "Input Files" in the run directory contract is
  present after a successful call (or explicitly skipped with a clear
  reason in the test for optional ones).
- `metadata.json` validates against the schema in the contract.
- `runs/` stays out of version control (use `.gitignore` if needed).
- `pytest` passes.

## Verification

```bash
pytest
```

## Git commit message

```text
Add Claude run directory writer
```

Do not push.
