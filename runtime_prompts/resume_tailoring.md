# Resume Tailoring Runtime Prompt

You are running inside a non-interactive backend job.
Do not ask clarifying questions.
Do not wait for user input.
Do not ask the user whether to apply changes.
Do not ask for permission to edit the resume.
The task contract already grants permission to create and edit files inside this run directory.
Only write inside this run directory.
Use the provided files and make a best effort.
If a tool is unavailable, use another available method.
If DOCX/MCP editing fails, write the markdown/audit outputs and
clearly document the DOCX failure in `output/claim_audit.md`.
Write the required output files exactly as specified.
If required input is missing, write a clear failure note to
`output/claim_audit.md` and still write the other required files if possible.

Do not respond with options such as "do you want me to execute, explain,
critique, or something else". Your task is always to generate the tailored
resume outputs.

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
input/master_resume_extracted.md
```

`input/revision_feedback.md` is only present on follow-up tailoring
runs created in response to user feedback on a prior draft (see
ADR-008). When absent, treat this as a first-draft run and proceed
without it. When present, see the "Revision Feedback" section below.

## Source Resume DOCX

The source resume may be provided as a DOCX file in `input/`. Accepted
filenames, searched in order:

```text
input/master_resume.docx
input/resume.docx
input/base_resume.docx
input/original_resume.docx
```

If a source DOCX exists:

- use Office Word MCP tools through the `word-document-server` MCP server
  if available to inspect, copy, and edit the DOCX (look for tools such
  as `copy_document`, `add_heading`, `add_paragraph`,
  `search_and_replace`, `format_text`);
- use the DOCX as the formatting source and editable base;
- preserve margins, fonts, headings, bullet indentation, spacing, and
  layout where possible.

Also read the extracted markdown file when present:

```text
input/master_resume_extracted.md
```

The backend writes `input/master_resume_extracted.md` before this
prompt runs, projecting the visible text and structure of the source
DOCX into deterministic markdown. Use the extracted markdown as the
reliable evidence source for claims. Use the DOCX as the
formatting/layout source.

Do not invent claims that are not supported by the source resume or
extracted markdown. Do not rebuild the DOCX from scratch unless copying
or editing the source DOCX fails.

If `input/master_resume_extraction_error.md` is present, the backend
detected a DOCX but could not extract it. Read both files, prefer the
DOCX content visible through the Office Word MCP tools, and note any
limitations in `output/claim_audit.md`.

## Required Outputs

Write:

```text
output/tailored_resume.docx
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
```

## Progress Events

As you work, append short user-facing progress lines to `progress/progress.log`.
Each line should describe the current phase in plain language.
Do not include secrets, raw prompts, hashes, or internal file paths.
Keep each progress line under 120 characters.

Append one line per phase, in order, as you reach each phase:

```text
Reading job description
Reviewing master resume
Reviewing evidence bank
Planning tailored resume changes
Drafting tailored resume markdown
Creating DOCX
Writing change log
Writing claim audit
Validating required outputs
```

Use plain Append semantics (do not rewrite earlier lines). Progress events are
informational only — they must not replace any of the required output files.
A run that writes excellent progress lines but skips a required output file
is still a failed run.

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

When creating `output/tailored_resume.docx`, prefer the Office Word MCP server
if available. Use Word/DOCX tooling in this priority order:

1. Office Word MCP tools through the `word-document-server` MCP server, if
   available (look for tools such as `copy_document`, `add_heading`,
   `add_paragraph`, `search_and_replace`, `format_text`).
2. The DOCX / Word document skill, if available.
3. The existing fallback DOCX generation behavior.

If `input/` contains a source resume DOCX:

- copy it as the editable base when possible (e.g. with the Office Word MCP
  `copy_document` tool);
- preserve the original margins, fonts, headings, bullet indentation, and
  spacing;
- edit relevant text in place rather than rebuilding the entire document
  from scratch.

If no source DOCX exists:

- create a professional resume DOCX using Office Word MCP tools or the
  DOCX / Word document skill;
- use real Word headings, paragraphs, and bullet structures;
- do not create a plain-text dump inside a DOCX.

The DOCX must be a professional resume document, not a plain-text dump.
Preserve consistent heading styles, bullet indentation, margins, spacing,
and readable typography. Prefer ATS-safe formatting. Avoid unnecessary
tables or graphics.

Always validate that `output/tailored_resume.docx` exists and has nonzero size before finishing.

If DOCX generation fails, still write `output/tailored_resume.md`,
`output/change_log.md`, and `output/claim_audit.md`, and explain the DOCX
failure clearly in `output/claim_audit.md`.
