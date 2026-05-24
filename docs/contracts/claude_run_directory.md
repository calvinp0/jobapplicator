# Claude Run Directory Contract

Each Claude Code run uses this structure:

```text
runs/<run_id>/
├── input/
│   ├── job_description.md
│   ├── master_resume.md
│   ├── evidence_bank.md
│   ├── candidate_profile.md
│   ├── project_notes.md
│   ├── skills_inventory.md
│   ├── tailoring_preferences.md
│   ├── resume_dos_and_donts.md
│   ├── tailoring_prompt.md
│   └── revision_feedback.md      # only present on follow-up runs
├── output/
│   ├── tailored_resume.docx
│   ├── tailored_resume.md
│   ├── change_log.md
│   └── claim_audit.md
└── metadata.json
```

## Input Files

### `job_description.md`

The captured job description and structured job metadata.

### `master_resume.md`

The baseline resume selected for this application.

This is the main source for existing resume content, dates, roles, education, publications, and formatting expectations.

### `evidence_bank.md`

A structured set of factual evidence that may be used to support resume rewrites.

Examples:

- projects
- technical achievements
- publications
- software contributions
- teaching experience
- leadership experience
- measurable outcomes
- tools used
- domains worked in

### `candidate_profile.md`

Stable background context about the candidate.

This may include:

- target career direction
- preferred positioning
- general research background
- industries of interest
- preferred seniority framing
- long-term goals
- recurring strengths

This file provides context, but it is not by itself sufficient evidence for adding concrete claims unless the claim is also supported by the master resume or evidence bank.

### `project_notes.md`

Additional markdown notes about projects, work, research, or accomplishments.

This file can grow over time.

Each note should be factual and ideally include:

- project name
- dates or approximate timeframe
- role
- technologies used
- what was built
- outcome or impact
- evidence strength

### `skills_inventory.md`

Canonical list of skills, tools, domains, and technologies.

Recommended sections:

- strong skills
- working knowledge
- exposure only
- avoid overstating
- skills to emphasize for specific job families

### `tailoring_preferences.md`

General preferences for resume style and positioning.

Examples:

- prefer technical clarity over sales language
- avoid inflated claims
- keep resume ATS-safe
- prefer concise bullets
- emphasize open-source software when relevant
- emphasize computational chemistry and ML intersection when relevant

### `resume_dos_and_donts.md`

Hard rules for rewriting.

Examples:

- do not invent metrics
- do not claim production ownership unless explicitly supported
- do not add tools that only appear in the job description
- do not exaggerate leadership
- do not remove PhD/research context unless targeting a non-research role
- do emphasize RMG/ARC when relevant
- do preserve dates and institution names

### `tailoring_prompt.md`

The final rendered runtime prompt given to Claude Code.

It should instruct Claude Code to read all input files and write the required output files.

### `revision_feedback.md`

User-authored feedback on a prior tailored draft, used to drive a follow-up tailoring run.

This file is **only present on follow-up tailoring runs** that were created in response to user feedback on an earlier `ResumeVersion`. First-draft tailoring runs do not have this file in their `input/` directory, and the worker must not assume it exists.

Defined by ADR-008. The backend writes it when creating the follow-up `ClaudeRun`; the runtime prompt instructs the worker to read it as a discrete input rather than splicing its contents into `tailoring_prompt.md`.

Contents:

- the user's free-text feedback as a markdown body
- an identifier for the source `ResumeVersion` that the feedback targets
- optionally, structured feedback flags (e.g., common-asks checkboxes from the frontend) rendered as small frontmatter or a short list at the top of the file

Boundaries the worker must respect when reading this file:

- Per ADR-004, feedback does not override evidence constraints. If the user asks for a claim that is not supported by `master_resume.md`, `evidence_bank.md`, or `project_notes.md`, the revised draft must either omit the claim or surface it as a gap in `output/claim_audit.md`. Unsupported claims must never be silently inserted.
- Per ADR-002, Claude Code may not write to the database or to anything outside the run directory. The feedback file is a read-only input; the worker's only response to it is updated output files in `output/`.

## Claude Code Read Boundary

Claude Code may read:

```text
input/job_description.md
input/master_resume.md
input/evidence_bank.md
input/candidate_profile.md
input/project_notes.md
input/skills_inventory.md
input/tailoring_preferences.md
input/resume_dos_and_donts.md
input/tailoring_prompt.md
input/revision_feedback.md
```

`input/revision_feedback.md` is only present on follow-up tailoring runs (see ADR-008); when absent, the worker must treat the run as a first-draft tailoring run.

## Claude Code Write Boundary

Claude Code may write:

```text
output/tailored_resume.docx
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
```

Claude Code must not write outside the run directory.

The backend validates outputs at two boundaries:

1. **Worker (post-invocation).** After the Claude subprocess exits with code
   `0`, the worker checks that every required output file under `output/`
   exists. If any are missing the run is marked `failed` with an
   `error_message` that lists the missing files (e.g.
   `expected output file missing: output/tailored_resume.docx, output/claim_audit.md`).
   A run only reaches `completed` when the exit code is `0` *and* the full
   output contract is satisfied. This prevents a successful-looking run from
   silently producing no draft and surfacing the failure later at import time.
2. **Import.** `/runs/{id}/import` re-validates the same files (and rejects
   any that resolve outside the run directory) before creating a
   `ResumeVersion` row and transitioning the run to `imported`.

### Dry-run worker

When `JOBAPPLY_CLAUDE_DRY_RUN=1`, the worker skips the Claude subprocess and
writes placeholder versions of all four required output files itself
(plain-text markdown for the `.md` files; a minimal valid Word package for
`tailored_resume.docx`). A dry-run is therefore importable end-to-end, which
makes it useful for local smoke testing of the run/import/approve flow
without invoking Claude.


## Metadata

`metadata.json` should include:

```json
{
  "run_id": "...",
  "job_id": "...",
  "master_resume_id": "...",
  "capture_method": "...",
  "created_at": "...",
  "input_files": {},
  "expected_outputs": [],
  "prompt_hash": "...",
  "input_hash": "..."
}
```
