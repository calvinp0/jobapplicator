# jobapply

Local-first job application cockpit.

This repository hosts the scaffold for an MVP that helps a single user
tailor resumes, track job applications, and version submitted resumes.
All resume generation happens locally through a Claude Code worker,
and the user remains in the loop for confirmation, approval, and
submission.

See `docs/product_requirements.md` and `docs/architecture.md` for the
full specification, and `docs/adr/` for the architectural decisions
that constrain how the system is allowed to behave.

## MVP Workflow

1. User opens a job posting in their browser.
2. User triggers the capture action (extension, clipboard, or paste).
3. The capture provider produces a normalized job capture payload and
   sends it to the local backend.
4. The backend shows the extracted job card for confirmation.
5. User clicks Generate Resume.
6. The backend creates a Claude Code run directory under `runs/<run_id>/`
   and writes a snapshot of selected candidate context plus the rendered
   tailoring prompt into `input/`.
7. Claude Code reads `input/` and writes resume artifacts into
   `output/` per `docs/contracts/claude_run_directory.md`.
8. The backend validates outputs, computes hashes, and imports an
   approved resume version.
9. User opens the generated DOCX and attaches it to the job manually.
10. User marks the application as submitted in the sidecar.

Claude Code is a worker. It does not mutate the database directly and
must not write outside the run directory.

## Repo Layout

```text
backend/             FastAPI service (owns DB, runs, hashes, imports)
frontend/            Local web UI
extension/           Browser extension for current-page capture
candidate_context/   Durable candidate source material (master resumes,
                     evidence bank, project notes, skills, preferences)
runtime_prompts/     Versioned prompt files used by Claude Code
docs/                Product requirements and architecture
docs/adr/            Architectural Decision Records
docs/contracts/      Stable contracts (e.g., Claude run directory)
agent_tasks/         Scoped task specs for coding agents
evals/               Fixtures and harnesses for offline evaluation
runs/                Per-run Claude Code working directories (gitignored)
```

The `candidate_context/` tree is the long-lived source of truth for
resume content. The `runs/` tree is ephemeral per-run scratch space:
its contents are gitignored, but the directory itself is anchored by
`runs/.gitkeep` so the contract is structurally enforced.

## Status

Scaffold only. Backend, frontend, extension, Claude Code invocation,
and resume generation are not implemented yet. Subsequent work is
tracked under `agent_tasks/`.
