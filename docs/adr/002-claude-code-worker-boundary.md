# ADR-002: Claude Code Worker Boundary

## Status

Accepted

## Context

The app will use Claude Code to generate tailored resume artifacts, including DOCX files, markdown resumes, change logs, and claim audits.

The system still needs reliable provenance, database consistency, output validation, and human approval.

## Decision

Claude Code will be used as a local worker.

The backend will create the run directory, write input files, invoke Claude Code, validate outputs, compute hashes, and import approved artifacts.

Claude Code must not directly mutate the database.

## Rationale

This keeps the backend as the source of truth for job records, application records, resume versions, hashes, and approval state.

Claude Code is good at generating documents, but the backend should own persistence and validation.

## Consequences

Claude Code may only read and write inside a specific run directory.

The backend must check that required output files exist before marking a run completed.

The backend must compute hashes for generated artifacts before storing resume versions.

## Alternatives Considered

- Let Claude Code write directly to the database: rejected because it weakens provenance and validation.
- Generate DOCX entirely in the backend: possible later, but Claude Code artifact generation is useful for MVP.
- Use only Claude web artifacts: useful as fallback, but harder to automate and version locally.

## Notes

The run directory contract is defined in `docs/contracts/claude_run_directory.md`.
