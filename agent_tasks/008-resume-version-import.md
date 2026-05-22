# Task 008: Resume Version Import and Approval

## Goal

After a Claude Code run completes, validate the expected output files,
compute their hashes, create a `ResumeVersion` row linked to the run, and
expose endpoints for the user to inspect and approve the version.

This is the backend half of the human-in-the-loop boundary: Claude
generated, the backend validates and imports, the user approves.

## Background

Read:

- `docs/architecture.md` (Claude Code worker boundary, human-in-the-loop)
- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/003-human-in-the-loop-submission.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/contracts/claude_run_directory.md` (write boundary, expected outputs)
- `agent_tasks/006-run-directory-writer.md`
- `agent_tasks/007-claude-code-worker.md`
- `backend/app/models.py` (existing `ResumeVersion`, `ClaudeRun`)

## Scope

Add to `backend/app/`:

- a `run_import.py` module exposing `import_run_outputs(run_id)` that:
  - loads the `ClaudeRun` and asserts `status="completed"`
  - validates that every expected output file exists:
    `output/tailored_resume.docx`, `output/tailored_resume.md`,
    `output/change_log.md`, `output/claim_audit.md`
  - rejects any file written outside the run directory
  - computes per-file SHA-256 hashes and a combined `output_hash`
  - assigns the next `version_number` for `(job_id, master_resume_id)`
  - creates a `ResumeVersion` row with `source="claude_run"`,
    `approved_at=None`, paths to the docx/md files, and the hashes
  - sets `claude_run.status="imported"` on success
- routes:
  - `POST /runs/{run_id}/import` → calls `import_run_outputs`
  - `GET /resume-versions` and `GET /resume-versions/{id}` (read)
  - `POST /resume-versions/{id}/approve` → sets `approved_at`
- pytest tests covering: successful import path, missing required output
  fails clearly, output written outside the run dir is rejected, version
  numbers increment per (job, master_resume), and approval sets the
  timestamp exactly once (re-approval is idempotent or rejected — your
  call, documented in the test)

## Allowed files

- `backend/**`
- `agent_tasks/queue.yaml` (status updates only if explicitly instructed)

## Forbidden files

- `extension/**`
- `frontend/**`
- `runs/**` at commit time
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/contracts/claude_run_directory.md`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- Other `agent_tasks/*.md`

## Out of scope

- Invoking Claude Code (task 007).
- Frontend approval UI (task 010 territory).
- Email/Gmail linking, application status flows, or submission tracking
  beyond what is already in the existing models.
- Generating DOCX in the backend or modifying Claude's outputs.

## Acceptance criteria

- A run that produces all four expected outputs imports successfully and
  results in exactly one new `ResumeVersion` row with non-null hashes.
- A run missing any expected output produces a clear error and does not
  create a `ResumeVersion` row.
- An output file outside the run directory is rejected.
- Approval transitions the row to `approved_at != None`; the rule for
  re-approval is covered by a test.
- `pytest` passes.

## Verification

```bash
pytest
```

## Git commit message

```text
Add resume version import and approval
```

Do not push.
