# ADR-004: Evidence-Constrained Resume Tailoring

## Status

Accepted

## Context

The app will generate tailored resumes for specific job descriptions. Resume tailoring is useful only if it remains truthful and does not invent unsupported experience.

The candidate context may include resumes, project notes, skills, preferences, and do/don't rules.

## Decision

Resume tailoring must be evidence-constrained.

Concrete resume claims must be supported by approved source material such as master resumes, evidence bank entries, and project notes.

Candidate profile, skills inventory, tailoring preferences, and do/don't rules may guide positioning and style, but they are not enough by themselves to justify adding concrete claims.

## Rationale

The system should rewrite, reorder, emphasize, and clarify real experience. It should not hallucinate employers, dates, titles, tools, metrics, publications, responsibilities, or achievements.

## Consequences

Each generated resume should include a claim audit.

Unsupported or weakly supported job requirements should be listed as gaps rather than silently inserted into the resume.

Runtime prompts must explicitly enforce evidence constraints.

## Alternatives Considered

- Free-form resume rewriting: rejected because it risks unsupported claims.
- Manual-only resume editing: rejected because it misses the value of the assistant.
- Evidence-constrained generation with claim audit: accepted.

## Notes

The claim audit should become part of the generated output contract.
