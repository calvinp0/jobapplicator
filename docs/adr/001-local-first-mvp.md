# ADR-001: Local-First MVP

## Status

Accepted

## Context

The project needs to generate tailored resumes, store exact resume versions, track job applications, and run Claude Code locally. The MVP should be useful before any hosted deployment exists.

## Decision

The MVP will be local-first.

The backend, database, run directories, generated resume files, runtime prompts, and Claude Code execution will all run locally.

## Rationale

A local-first design gives direct control over generated files, resume versions, hashes, prompts, and application records. It also avoids needing hosted infrastructure before the core workflow is proven.

## Consequences

The MVP will use local storage and a local database.

Generated runs will be written under `runs/`.

The architecture should not assume a cloud service is required.

## Alternatives Considered

- Hosted-first app: more complex and unnecessary for the MVP.
- Browser-only app: weaker local file/process control.
- Fully manual folder workflow: simpler, but less useful as an application tracker.

## Notes

A hosted version can be added later after the local workflow is stable.
