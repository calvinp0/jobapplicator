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
│   └── tailoring_prompt.md
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
```

## Claude Code Write Boundary

Claude Code may write:

```text
output/tailored_resume.docx
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
```

Claude Code must not write outside the run directory.

The backend validates outputs before importing them.


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
