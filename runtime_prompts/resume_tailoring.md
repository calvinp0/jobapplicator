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

Also read, if present:

```text
input/revision_feedback.md
```

`input/revision_feedback.md` is only present on follow-up tailoring
runs created in response to user feedback on a prior draft (see
ADR-008). When absent, treat this as a first-draft run and proceed
without it. When present, see the "Revision Feedback" section below.

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

## Revision Feedback

This section applies only when `input/revision_feedback.md` is present.

The file contains user-authored feedback on a prior tailored draft. It
may include a free-text markdown body and optional structured flags
(such as common-asks checkboxes) at the top.

Treat the file as user-supplied steering for the rewrite, not as new
evidence. Use it to decide what to change about positioning, emphasis,
wording, ordering, and inclusion or removal of existing content.

The ADR-004 evidence rule overrides the feedback. The evidence files
(`input/master_resume.md`, `input/evidence_bank.md`,
`input/project_notes.md`) remain the only sources from which concrete
claims may be drawn. If the feedback asks for a claim that is not
supported by those files, do not insert it. Either omit it or surface
it as a gap in `output/claim_audit.md`. Never silently invent an
employer, title, date, degree, publication, award, tool,
responsibility, metric, or outcome because the user asked for it.

In `output/claim_audit.md`, record each substantive feedback item as
either honored or rejected:

- Honored items: name the change made and cite the evidence that
  supports it.
- Rejected items: name the requested change, state that it was not
  applied, and explain the evidence gap (which files were checked and
  what was missing).

When `input/revision_feedback.md` is absent, behave exactly as
specified by the rest of this prompt; no feedback-tracking section is
required in the claim audit.

## Claim Audit

In `output/claim_audit.md`, list important claims in the tailored resume and identify their supporting source.

If a job requirement is weakly supported or unsupported, list it as a gap instead of adding it to the resume.

If `input/revision_feedback.md` was present, include the honored vs.
rejected feedback breakdown described in the "Revision Feedback"
section above.

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
