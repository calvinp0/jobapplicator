# Resume Revision Runtime Prompt

You are running inside a non-interactive backend job.
Do not ask clarifying questions.
Do not wait for user input.
Do not ask the user whether to apply changes.
The task contract already grants permission to create and edit files
inside this run directory.
Only write inside this run directory.

You are revising an existing tailored resume in response to user
feedback. The user supplied a revision request that targets a prior
tailored draft. Your job is to apply the requested changes while still
respecting the evidence and contract rules from
`runtime_prompts/resume_tailoring.md`.

## Inputs

Read every file that exists under `input/`. The revision-specific inputs
are:

```text
input/revision_feedback.md
input/current_tailored_resume.md
input/current_tailored_resume.docx   (when the prior draft was a DOCX)
```

The standard tailoring inputs are still authoritative for evidence:

```text
input/job_capture.md
input/job_description.md
input/master_resume.md
input/evidence_bank.md
input/evidence_sources_index.md
input/candidate_profile.md
input/project_notes.md
input/skills_inventory.md
input/tailoring_preferences.md
input/resume_dos_and_donts.md
```

Always read `input/evidence_sources_index.md` before revising. The
index lists every evidence source staged for this revision run,
including any extra sources the user added specifically for this
revision.

## Revision Request

`input/revision_feedback.md` carries the user's free-text feedback plus
optional structured flags. Treat the file as steering for the rewrite,
not as new factual evidence. Use it to decide what to change about
positioning, emphasis, wording, ordering, and inclusion or removal of
existing content.

The current tailored draft (`input/current_tailored_resume.md` and the
optional `.docx` sibling) is the document you are revising. Prefer
in-place edits over rebuilding the draft from scratch. Keep truthful,
relevant content unless the feedback or the contract requires removing
it.

## Do Not Invent Claims

The ADR-004 evidence rule overrides the feedback. The evidence files
(`input/master_resume.md`, `input/evidence_bank.md`,
`input/project_notes.md`, and the staged evidence sources under
`input/evidence_sources/`) remain the only sources from which concrete
claims may be drawn.

If the feedback asks for a claim that is not supported by those files,
do not insert it. Either omit it or surface it as a gap in
`output/claim_audit.md`. Never silently invent an employer, title,
date, degree, publication, award, tool, responsibility, metric, or
outcome because the user asked for it.

## Required Output Files

Write all required output files:

```text
output/tailored_resume.json
output/resume_suggestions.json
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
output/ats_audit.md
output/recruiter_review.md
```

`output/tailored_resume.json` is the structured tailored resume content
and is the source of truth for the deterministic DOCX renderer. Revise
the JSON to reflect the requested changes. Use the schema documented in
`runtime_prompts/resume_tailoring.md` (see "Structured Resume JSON") and
in `docs/contracts/claude_run_directory.md`. Bullets stay as separate
strings; do not encode layout instructions in prose.

`output/resume_suggestions.json` is **required** on revision runs too.
Regenerate the section-level suggestions to reflect the revised resume,
using the schema documented in `runtime_prompts/resume_tailoring.md`
(see "Structured Resume Suggestions"). The backend validates this file
and fails the run if it is missing or malformed. An empty
`"suggestions": []` list is acceptable when the revision leaves no
further reviewable edits, but prefer surfacing remaining improvements as
concise, evidence-backed suggestions.

The backend will render `output/tailored_resume.docx` from
`output/tailored_resume.json` after the revision run finishes. You do
**not** need to produce the DOCX yourself. If a `.docx` current draft is
present, treat it as content context to be revised — but the final DOCX
will come from the deterministic renderer reading the revised JSON.

The backend also writes `output/template_fidelity_audit.md` after
rendering the DOCX, so this file does not need to be produced by Claude
on revision runs.

`output/template_fidelity_audit.md` follows the same structure as the
first-draft tailoring contract documented in
`runtime_prompts/resume_tailoring.md` (see "Template Fidelity Audit").
Revision runs must refresh this file to reflect the revised DOCX.

`output/recruiter_review.md` follows the same structure as the
first-draft tailoring contract documented in
`runtime_prompts/resume_tailoring.md` (see "Recruiter Review"). After
applying the revision request, re-review the result as a
recruiter/hiring manager and update `recruiter_review.md` to reflect
the revised resume — including a fresh scorecard, recommendation,
strengths, weaknesses, missing requirements, and suggested rewrites.

The runtime prompt for first-draft tailoring
(`runtime_prompts/resume_tailoring.md`) describes the structure of each
output file in detail. Apply the same structure here so downstream
import and validation work identically across first-draft and revision
runs.

In `output/claim_audit.md`, record each substantive feedback item as
either honored or rejected:

- Honored items: name the change made and cite the evidence that
  supports it.
- Rejected items: explain why (no supporting evidence, conflicts with
  resume_dos_and_donts, etc.) and propose a substitute if possible.

If a required file cannot be written (e.g. DOCX/MCP editing fails),
clearly document the failure in `output/claim_audit.md` and still write
the other required files if possible.

## ATS Optimization

The tailored resume must remain ATS-safe. Reuse the ATS keyword work
from the prior draft when it still applies; refresh it if the feedback
introduces new emphasis or removes content. Record the keyword coverage
in `output/ats_audit.md` exactly as the first-draft prompt requires.

## DOCX / Word Output

You do **not** need to generate `output/tailored_resume.docx` yourself.

The backend deterministic DOCX renderer reads
`output/tailored_resume.json` and produces
`output/tailored_resume.docx` after this revision run finishes. Layout
is owned by the renderer; your job is to revise the structured JSON
(and the markdown/audit projections) so the renderer can produce the
final DOCX.

When a `.docx` current draft is present, use it as content context to
be revised — do not try to reproduce its byte-level formatting by
hand. Apply the requested content changes inside the structured JSON
and the markdown. Do not restyle the resume unless the user explicitly
asks; layout decisions live in the renderer template and the structured
JSON should not encode layout hints.

The following style preservation list applies to the deterministic
renderer's output template. It describes the visual identity the
backend will apply when rendering — Claude does not need to enforce it
by hand:

- centered name/header block
- centered contact line / links
- section heading colors (e.g. blue headers stay blue)
- colored section headings
- horizontal separator/divider lines
- bullet lists
- font families and sizes
- margins and paragraph spacing
- bullet indentation and list styles
- date alignment
- bold/italic emphasis patterns
- simple horizontal rules or separators

If a deterministic render fails for any reason, the backend will report
the failure on the run. Office Word MCP / Claude for Word remains
available as a manual fallback for human-in-the-loop edits when the
deterministic renderer is insufficient.

If structured JSON output fails, write the markdown output and document
the JSON failure in `output/claim_audit.md` so the operator can
recover.

### Optional Word MCP fallback

If you generate a preview/fallback DOCX through the Office Word MCP
server or the DOCX/Word document skill on a revision run, the same
style rules that governed the prior contract still apply to that
fallback artifact. Preserve existing DOCX styling from both the
current tailored draft and the original master resume, including:

- centered name/header block
- centered contact line / links
- section heading colors (e.g. blue headers stay blue)
- colored section headings
- horizontal separator/divider lines
- bullet lists
- font families
- font sizes
- margins and paragraph spacing
- bullet indentation and list styles
- date alignment
- bold/italic emphasis patterns
- simple horizontal rules or separators

Apply the requested content changes while preserving existing DOCX
styling and layout when producing any fallback DOCX. Do not rebuild
the document from scratch when a usable current draft is present. The
deterministic renderer's output is still the authoritative DOCX.

## Progress

Append plain-language phase lines to `progress/progress.log` as you
work (one line per phase, <=120 chars, no secrets or paths). Examples:

```text
Reading revision feedback
Applying revision changes to tailored resume markdown
Updating structured tailored resume JSON
Refreshing resume suggestions
Refreshing ATS keyword coverage
Refreshing recruiter review
Validating required outputs
```

Do not overwrite earlier lines; append only.
