# ADR-006: Candidate Context as Source Material

## Status

Accepted

## Context

A single master resume is not enough context for high-quality tailoring.

The system needs reusable information about the candidate's projects, skills, preferences, and hard resume-writing rules.

## Decision

The project will keep reusable candidate context under `candidate_context/`.

The candidate context may include master resumes, project notes, an evidence bank, skills inventory, tailoring preferences, and resume do/don't rules.

## Rationale

Keeping candidate context as markdown makes it easy to update over time and easy for Claude Code to consume during resume generation.

It also separates persistent source material from per-job run snapshots.

## Consequences

The app will copy or render selected candidate context into each run directory.

Each run should be reproducible from its input snapshot.

The backend should not require users to rewrite the same background information for every application.

## Alternatives Considered

- Store everything only in the database: more structured, but less convenient for early iteration.
- Store everything only in one resume file: too limited.
- Use markdown candidate context files: accepted for MVP.

## Notes

Expected folder shape:

```text
candidate_context/
├── master_resumes/
├── project_notes/
├── candidate_profile.md
├── evidence_bank.md
├── skills_inventory.md
├── tailoring_preferences.md
└── resume_dos_and_donts.md
```
