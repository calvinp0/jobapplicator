# Resume Tailoring Runtime Prompt

You are generating a tailored resume for one job application.

## Inputs

Read:

```text
input/job_capture.md
input/job_description.md
input/master_resume.md
input/evidence_bank.md
input/candidate_profile.md
input/project_notes.md
input/skills_inventory.md
input/tailoring_preferences.md
input/resume_dos_and_donts.md
```

## Required Outputs

Write:

```text
output/tailored_resume.docx
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
```

## Goal

Tailor the selected master resume to the job description.

The result should be truthful, ATS-safe, and relevant to the role.

## Evidence Rules

Concrete resume claims must be supported by:

```text
input/master_resume.md
input/evidence_bank.md
input/project_notes.md
```

The following files may guide style and positioning, but must not be used alone to invent concrete claims:

```text
input/candidate_profile.md
input/skills_inventory.md
input/tailoring_preferences.md
input/resume_dos_and_donts.md
```

## Allowed Edits

You may:

- reorder sections
- rewrite bullets for relevance
- emphasize matching skills
- remove weakly relevant content
- adjust the summary
- improve clarity and concision

## Forbidden Edits

You must not invent:

- employers
- job titles
- dates
- degrees
- publications
- awards
- tools
- responsibilities
- metrics
- project outcomes

## Claim Audit

In `output/claim_audit.md`, list important claims in the tailored resume and identify their supporting source.

If a job requirement is weakly supported or unsupported, list it as a gap instead of adding it to the resume.

## Change Log

In `output/change_log.md`, summarize:

- sections reordered
- bullets rewritten
- keywords emphasized
- requirements matched
- requirements not supported

## DOCX

Create `output/tailored_resume.docx` with clean professional formatting.
Prefer ATS-safe formatting.
Avoid unnecessary tables or graphics.
