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
│   ├── prompt_snapshot.md        # verbatim snapshot of the effective runtime prompt
│   ├── revision_feedback.md      # only present on follow-up runs
│   ├── current_tailored_resume.md    # prior draft to revise (follow-up runs)
│   ├── current_tailored_resume.json  # optional structured prior draft (follow-up runs)
│   ├── current_tailored_resume.docx  # optional prior draft DOCX (follow-up runs)
│   ├── master_resume.docx        # optional source DOCX (any accepted name)
│   ├── master_resume_extracted.md           # written by the backend when a DOCX is present
│   ├── master_resume_extraction_error.md    # written instead if extraction fails
│   └── preflight/                  # provider-routed preflight analysis (task 124)
│       ├── job_summary.json
│       ├── ats_keywords.json
│       ├── role_requirements.json
│       ├── evidence_gap_plan.json
│       ├── preflight_manifest.json # includes local LLM context-budget checks
│       └── preflight_summary.md    # optional human-readable projection
├── output/
│   ├── tailored_resume.json         # structured resume content; source of truth for the renderer
│   ├── resume_suggestions.json      # section-level reviewable suggestions (required)
│   ├── tailored_resume.docx         # rendered deterministically by the backend from the JSON
│   ├── tailored_resume.md
│   ├── change_log.md
│   ├── claim_audit.md
│   ├── ats_audit.md
│   ├── template_fidelity_audit.md   # written deterministically by the backend renderer
│   └── recruiter_review.md          # required; recruiter/hiring-manager simulated review
├── progress/
│   └── progress.log              # user-facing phase events + worker heartbeats
├── word_handoff/                 # only used when tailoring_method == word_handoff
├── run.log
└── metadata.json
```

The `word_handoff/` directory holds the artifacts produced and consumed when
a run's `tailoring_method` is `word_handoff`. It is not used by the `auto`
path.

## Word Handoff Package

When the backend creates a Claude for Word handoff for a run, it writes the
following layout into `runs/<run_id>/word_handoff/`:

```text
word_handoff/
├── 01_resume_for_claude_word.docx   # source DOCX, copied from input/ when present
├── 02_prompt_for_claude_word.txt    # prompt the user pastes into Claude for Word
└── 03_instructions.md               # manual steps for the operator
```

The numeric prefixes reflect reading order; the directory is opened by a
human.

The source resume DOCX is looked up under `input/` using these accepted
names, in order, with the first match winning:

```text
input/master_resume.docx
input/resume.docx
input/base_resume.docx
input/original_resume.docx
```

If no DOCX is present but a markdown resume is — under any of these accepted
names — the package is still created and the markdown is included in the
prompt as fallback context:

```text
input/master_resume.md
input/resume.md
input/base_resume.md
input/original_resume.md
```

The job description is looked up similarly:

```text
input/job_description.md
input/job_description.txt
input/jd.md
input/jd.txt
```

Successful package creation transitions the run metadata to
`tailoring_method = word_handoff` and `status = word_handoff_ready`, and
appends `jobapply:` progress lines to `run.log` recording the handoff
directory path and the expected Word output relative path
(`output/word_tailored_resume.docx`).

The Word output itself is imported by a follow-up step (the run-import
flow); creating the handoff package only stages inputs and records intent.

### Handoff lifecycle states

`GET /runs/{run_id}/word-handoff/status` reports the on-disk state of the
package, independently of `metadata.json`. The UI uses these states to
decide which controls and copy to render, so the handoff is never claimed
to be "prepared" before the files actually exist on disk:

- `not_prepared` — `word_handoff/` does not exist. The "Prepare for
  Claude for Word" button is enabled.
- `prepared` — `word_handoff/` exists and contains every required file
  (`02_prompt_for_claude_word.txt`, `03_instructions.md`). The prompt
  and instructions panel is rendered along with the folder path and a
  per-file existence list.
- `missing_files` — `word_handoff/` exists but at least one required
  file is absent (typically because the operator deleted or moved
  something). The UI surfaces the missing names and exposes a
  *Regenerate handoff package* action.
- `import_ready` — `output/word_tailored_resume.docx` is present and
  non-empty. The *Import Word Result* button is rendered.
- `imported` — `output/final_resume.docx` is present. Post-import
  success copy is rendered.

The status endpoint is a pure filesystem check — it does not read
`metadata.json` so it stays accurate even if the package was edited or
deleted out from under the run.

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

### `prompt_snapshot.md`

Verbatim snapshot of the effective runtime prompt body used to drive
this run. Identical to `tailoring_prompt.md`'s content — the snapshot
is the contract name and exists so runs stay reproducible even if the
shipped default prompt or the local override changes after the run.

The snapshot's source is one of:

- the shipped default under `runtime_prompts/<id>.md` (first-draft runs
  use `resume_tailoring.md`; revision runs use `resume_revision.md`),
  or
- a local override under
  `candidate_context/settings/prompt_overrides/<id>.md` when the
  prompt harness editor has saved one.

The metadata block records which one (`prompt_id`, `prompt_source`,
`prompt_hash`) so an operator can replay a run with the exact prompt
that produced it. See "Prompt provenance" under *Metadata* below.

### `preflight/preflight_manifest.json`

When a preflight task attempts the experimental local LLM provider, its task
entry includes a `context` object with:

- `context_window_tokens`
- `reserved_output_tokens`
- `max_input_tokens`
- `effective_assumed_context_tokens` — the context window JobApplicator
  budgeted this task against (task 127). Records the assumed context for audit
  even if the budget plumbing changes later.
- `requested_num_ctx` — only present when an Ollama `num_ctx` is configured;
  the server context length requested for the run (task 126/127). Recorded for
  audit; it does not change the budget.
- `estimated_input_tokens_initial`
- `estimated_input_tokens_final`
- `compression_used`
- `fallback_used`
- `over_budget`

When a task **actually issued** a local call (a request reached the server),
its entry also carries (task 133):

- `local_attempted` — `true` only on a task where a local call was issued.
  Present only on attempted tasks; a deterministic-only task (local disabled,
  over-budget before the call, or skipped after repeated timeouts) omits it
  entirely so it stays neutral.
- `performance` — a record of how the local call behaved:
  - `prompt_token_estimate` — the prompt token estimate the call was sent with.
    Reuses the budgeted `context.estimated_input_tokens_final`; it is not
    recomputed.
  - `elapsed_ms` — the call's measured elapsed time. Absent when the call timed
    out (the timeout fires before a latency is recorded).
  - `effective_timeout_seconds` — the per-call timeout that bounded the attempt
    (the provider-aware value resolved in task 130).

A task that fell back *before* contacting the server (budget over-limit, or the
task-132 skip path) is not "attempted" and records neither `local_attempted`
nor `performance`; its prompt token estimate still lives in
`context.estimated_input_tokens_final`.

If a local input remains too large and deterministic fallback is allowed, the
task entry records `status = "fallback"`, `provider = "deterministic"`, and a
clear `fallback_reason`. Local LLM prompts must never be silently truncated.

When the run intends the local provider, the manifest also carries a single
top-level `context` summary recording the run's assumed context and what the
model server actually reports (task 127):

- `assumed_context_tokens` — the context window JobApplicator budgeted against
  for the run (`context_window_tokens`).
- `server_reported_context_tokens` — the model server's own context length
  when it could be read (`int`), else `null`. Only the Ollama-native provider
  exposes this (via its native `/api/show` endpoint).
- `context_verified` — `true` only when the server actually reported a context
  length. An OpenAI-compatible server, an unreachable server, or a missing
  metadata field all leave this `false`.
- `requested_num_ctx` — only present when an Ollama `num_ctx` is configured.
- `note` — a short human-readable explanation (e.g. why the context could not
  be verified).

Server-context detection is best-effort and **reporting only**: a detection
failure records `context_verified = false` and never fails preflight, and a
detected context is never auto-applied to the budget — the user stays in
control of the budget. Deterministic-only runs (the local provider is not the
intended primary) omit the top-level `context` summary entirely.

When the run intends the local provider, the manifest also carries three
top-level boolean signals describing how the local provider fared (task 133):

- `local_attempted` — `true` when at least one task actually issued a local
  call this run. Distinct from `fallback_used`: a run can fall back without ever
  contacting the server (everything over budget), and a run can attempt local
  and still fall back (a timeout or unparseable output).
- `local_degraded` — `true` once a local call timed out this run (task 132).
- `local_skipped` — `true` once repeated timeouts crossed the skip threshold and
  the remaining tasks bypassed the local provider entirely (task 132).

These three flags are present only when the local provider was the intended
primary; a deterministic-only run omits them so it never gains misleading
"attempted" fields.

When `local_attempted` and `fallback_used` are both true, the human-readable
`preflight_summary.md` and the run trace (`run.log` / progress stream) carry a
stable `Local LLM attempted but fell back: <reason>` line (noting *degraded* or
*skipped after repeated timeouts* when applicable) so an operator can see at a
glance that the deterministic artifacts came from a local attempt that
degraded, not from a run that never tried the local provider.

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

### `master_resume.docx` (optional)

A source resume provided as a Word document. Accepted under the same
filename list used by the word-handoff path:

```text
input/master_resume.docx
input/resume.docx
input/base_resume.docx
input/original_resume.docx
```

When present, the backend extracts visible text and basic structure to
`input/master_resume_extracted.md` *before* the Claude Code subprocess
launches. The runtime prompt instructs Claude to treat the DOCX as the
formatting/layout source and the extracted markdown as the reliable
evidence source for claims.

If extraction fails, the backend writes
`input/master_resume_extraction_error.md` (recording the DOCX path and
the failure reason) instead of the extracted markdown. The run is
failed loudly when extraction fails *and* no accepted markdown resume
(`master_resume.md`, `resume.md`, `base_resume.md`,
`original_resume.md`) is present in `input/`.

### `preflight/` (provider-routed preflight analysis, task 124)

Before the main tailoring prompt runs, the backend worker executes a
**provider-routed preflight analysis pipeline** (`backend/app/preflight.py`)
over `input/job_description.md` and writes structured analysis artifacts
under `input/preflight/`. These are **advisory inputs** to the tailoring run,
produced by a lower-risk extraction step that may use the experimental local
LLM (task 123) or a deterministic fallback. They never replace the
truthfulness/evidence contract; if preflight conflicts with the job
description, the job description wins.

Provider routing reuses the Task 123 policy (`app.local_llm`): the
`job_summary`, `ats_keywords`, `role_requirements`, and `evidence_gap_plan`
tasks run on the local provider only when the subsystem is enabled and the
task is toggled on. Otherwise — or on any local connection/JSON failure — a
deterministic extractor produces the same artifacts. The high-risk tailoring,
claim-audit, and recruiter-review steps are **not** part of preflight and stay
on Claude Code in the main run. Preflight is best-effort: a preflight failure
never fails the tailoring run.

Artifacts:

- `job_summary.json` — `company`, `job_title`, `location`,
  `employment_type`, `seniority`, `role_family`, `summary`, `source`.
  Extracted only from the job description; unknown fields are `null`, never
  invented.
- `ats_keywords.json` — `target_company`, `target_job_title`, a `keywords`
  array (each `{keyword, category, kind, evidence, priority}` where
  `category ∈ {required, preferred, industry, responsibility}` and
  `priority ∈ {high, medium, low}`), and a `groups` object
  (`required`/`preferred`/`tools`/`domains`/`responsibilities`). It records
  what the JD asks for; it does **not** decide whether the candidate has a
  keyword — that belongs to the tailoring ATS audit.
- `role_requirements.json` — `requirements` (each with an `id`,
  `requirement`, `importance`, `source_quote`, `keywords`),
  `responsibilities`, and `screening_signals`, grounded in the JD.
- `evidence_gap_plan.json` — `likely_evidence_targets` (each naming
  `candidate_evidence_files_to_check` drawn from staged evidence index
  filenames) and `known_risks_before_tailoring`. This is a **plan of where to
  look**, written before any evidence is read; it must never claim that
  evidence exists.
- `preflight_manifest.json` — `created_at`, top-level `provider`/`model`,
  `fallback_used` (and `fallback_reason` when a local task degraded), a
  `tasks` array recording per-task `name`/`provider`/`model`/`status`/`output`
  (plus, on tasks that issued a local call, `local_attempted` and a
  `performance` record of `prompt_token_estimate`/`elapsed_ms`/
  `effective_timeout_seconds`), and — for local runs — the top-level
  `local_attempted`/`local_degraded`/`local_skipped` signals and a `context`
  summary of the assumed vs. server-reported context (`assumed_context_tokens`,
  `server_reported_context_tokens`, `context_verified`). A `provider` of
  `deterministic` means the heuristic extractor produced the artifact. See
  *`preflight/preflight_manifest.json`* above for the full context and
  performance schema.
- `preflight_summary.md` — optional human-readable projection of the
  manifest.

The runtime tailoring prompt (`runtime_prompts/resume_tailoring.md`) reads
these when present: it uses `ats_keywords.json` as the starting keyword list
for the ATS audit, treats every artifact as advisory, ignores any implied
evidence it cannot actually find, and proceeds normally when the artifacts
are absent.

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
input/current_tailored_resume.md
input/current_tailored_resume.json
input/current_tailored_resume.docx
input/master_resume.docx
input/master_resume_extracted.md
input/master_resume_extraction_error.md
input/preflight/job_summary.json
input/preflight/ats_keywords.json
input/preflight/role_requirements.json
input/preflight/evidence_gap_plan.json
input/preflight/preflight_manifest.json
```

The `input/preflight/*` files are advisory analysis artifacts (see
*`preflight/`* above); they may be absent, and their absence is not an error.

`input/revision_feedback.md` is only present on follow-up tailoring runs (see ADR-008); when absent, the worker must treat the run as a first-draft tailoring run. The `input/current_tailored_resume.{md,json,docx}` files are staged alongside it on revision runs: the markdown and DOCX are the prior draft to revise, and the optional structured JSON (`current_tailored_resume.json`) carries the prior draft's section/entry ids so suggestions stay stable across revisions.

## Claude Code Write Boundary

Claude Code may write:

```text
output/tailored_resume.json
output/resume_suggestions.json
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
output/ats_audit.md
output/recruiter_review.md
progress/progress.log
```

`output/tailored_resume.json` is the structured tailored resume
content and the source of truth for the deterministic DOCX renderer
(task 111). The backend reads this file after Claude exits, validates
its schema, and renders `output/tailored_resume.docx` and
`output/template_fidelity_audit.md` deterministically — Claude is no
longer responsible for producing either of those files. See "Structured
Tailored Resume JSON" below for the schema, and
`backend/app/resume_docx_renderer.py` for the renderer.

The runtime prompt requires Claude to **actually write the files on
disk** and includes a Final Verification Checklist enumerating each
required path. A response that describes the expected files in prose
without writing them counts as missing files — exit code 0 alone is
not enough to mark the run completed (run d6df714b regressed on this
before the prompt mandate was hardened).

Claude may still optionally produce a preview/fallback
`output/tailored_resume.docx` through the Office Word MCP server or
the DOCX / Word document skill, but the backend deterministic
renderer overrides that file with its own output. Treat the structured
JSON, not any Claude-generated DOCX, as the canonical artifact.

`output/ats_audit.md` is the structured ATS audit emitted by the
tailoring worker. It records the keywords extracted from the job
description, their classification (required / preferred / industry /
role), how each keyword was covered by the tailored resume (or why it
was not used), and an ATS-formatting check. The audit is mandatory:
runs missing this file are marked failed by the same output validation
that gates the other required outputs.

`output/template_fidelity_audit.md` is the structured template
fidelity audit. As of task 111 it is written **deterministically by
the backend renderer** (`backend/app/resume_docx_renderer.py`) after
Claude exits, alongside `output/tailored_resume.docx`. It records the
rendering mode (deterministic backend renderer vs. fallback), the
source DOCX (when present), which style features the renderer applied
(centered header, colored section headings, horizontal separators,
bullet lists, margins, font family/size, section spacing), and known
limitations. The audit is no longer produced by Claude and no longer
falls under the "optional output" warning behavior; if the renderer
runs successfully, the audit exists.

`output/resume_suggestions.json` is the section-level, reviewable
suggestions artifact (task 113). It is the main user-facing review
surface: the frontend Resume Review page renders each suggestion and
lets the user accept, reject, or ask to revise it before the resume
state is rebuilt. The file is **required** — the worker validates its
schema after Claude exits and marks the run failed with
`invalid resume suggestions JSON: <reason>` when it is missing or
malformed (the same gate that protects `tailored_resume.json`). See
"Structured Resume Suggestions" below for the schema and review
lifecycle.

`output/recruiter_review.md` is the simulated recruiter/hiring-manager
review of the tailored resume against the target company and role
(task 108). It includes an overall recommendation, a per-category
scorecard, a first 30-second impression, strengths and weaknesses,
missing or under-emphasized requirements, claims that need stronger
evidence, suggested rewrites for the weakest lines, and a
company-specific fit assessment. The review is a **required** output of
the v2 tailoring contract: it is part of ``EXPECTED_OUTPUTS`` and
``run_import``'s ``EXPECTED_OUTPUT_FILES``, so a run is marked failed
(``expected output file missing: output/recruiter_review.md``) when it
is absent, exactly like the other required outputs.

Claude Code must not write outside the run directory.

### Structured Tailored Resume JSON

`output/tailored_resume.json` is the structured tailored resume
content. It is the source of truth for the deterministic DOCX renderer
introduced in task 111. The backend rejects a run whose JSON is
missing or fails schema validation, with a clear error like
`expected output file missing: output/tailored_resume.json` or
`invalid tailored resume JSON: <reason>`.

Schema (stable, evolved additively):

```json
{
  "header": {
    "name": "Full Name",
    "contact_items": ["email", "linkedin", "github", "City, Country"],
    "subtitle": "Optional subtitle line"
  },
  "sections": [
    {"id": "sec_summary", "type": "summary", "heading": "PROFESSIONAL SUMMARY", "paragraphs": ["..."]},
    {"id": "sec_skills", "type": "skills", "heading": "SKILLS",
      "groups": [{"label": "Languages", "items": ["Python"]}]},
    {"id": "sec_experience", "type": "experience", "heading": "WORK EXPERIENCE",
      "entries": [{
        "id": "exp_001",
        "title": "...", "organization": "...", "location": "...",
        "dates": "2024 – Present", "subtitle": "...", "bullets": ["..."]
      }]},
    {"id": "sec_education", "type": "education", "heading": "EDUCATION",
      "entries": [{
        "id": "edu_001",
        "institution": "...", "degree": "...",
        "dates": "...", "location": "..."
      }]},
    {"id": "sec_publications", "type": "publications", "heading": "PUBLICATIONS", "items": ["..."]}
  ],
  "metadata": {
    "target_company": "...",
    "target_job_title": "...",
    "generated_for_ats": true
  }
}
```

Rules:

- `header.name` is required and must be non-empty.
- `sections` must be a non-empty array.
- Every section, and every experience/education entry, carries a stable
  `id` (lowercase snake_case, unique within the document). Suggestions in
  `resume_suggestions.json` reference these ids, and the worker
  cross-validates them (see "Structured Resume Suggestions"). The renderer
  itself ignores ids — they exist for the review surface.
- Section `type` must be one of: `summary`, `skills`, `experience`,
  `education`, `publications`, `projects`, `certifications`, `awards`,
  `other`.
- `summary` uses `paragraphs`; `skills` uses `groups`; `experience`
  and `education` use `entries`; `publications`, `projects`,
  `certifications`, `awards`, and `other` use `items`.
- Bullets are plain strings (one bullet per array element). Do not
  bake `•`, `-`, or newlines into bullet strings.
- The JSON must not encode layout hints (fonts, colors, margins).
  Layout is owned by the renderer.

The renderer is `backend/app/resume_docx_renderer.py`. It applies a
stable professional style (centered name/header, centered contact
line, blue uppercase section headings, horizontal separators, real
Word bullet lists, consistent margins and spacing) regardless of
whether a master DOCX was provided. Word MCP / Claude for Word
remains available as a manual fallback for human-in-the-loop edits
when the deterministic renderer is insufficient.

### Structured Resume Suggestions

`output/resume_suggestions.json` is the section-level review surface
introduced in task 113. Where `tailored_resume.json` is the *finalized*
structured resume, the suggestions file lists concise, evidence-backed
edits the user can accept, reject, or ask to revise before the resume
state is rebuilt. The backend validates it
(`backend/app/resume_suggestions.py`) and fails the run on a missing or
malformed file.

Schema:

```json
{
  "target_company": "Amazon",
  "target_job_title": "Software Development Engineer, AWS Agentic AI",
  "suggestions": [
    {
      "id": "sug_001",
      "section_id": "sec_summary",
      "entry_id": null,
      "bullet_index": null,
      "section_heading": "PROFESSIONAL SUMMARY",
      "operation": "replace_section_text",
      "current_text": "...",
      "suggested_text": "...",
      "reason": "Why this improves the resume for the target role.",
      "evidence_refs": [{"source": "input/evidence_sources/003.md", "quote": "..."}],
      "ats_keywords": ["agentic AI", "distributed systems"],
      "confidence": "high",
      "risk": "low",
      "status": "pending"
    }
  ]
}
```

Rules:

- `id`, `section_id`, `operation`, and `reason` are required on every
  suggestion; `id` must be unique within the document.
- `section_id` must match a section `id` in `tailored_resume.json`.
  Bullet- and entry-level operations set `entry_id` (matching an entry
  `id` in that section) and, for bullet operations, `bullet_index` (a
  0-based index into the entry's `bullets`). The worker cross-validates
  `section_id` and `entry_id` against the resume's declared ids and fails
  the run when a suggestion points at an id that does not exist. (Legacy
  resume JSON without declared ids skips this strict check and falls back
  to fuzzy section matching.)
- `operation` must be one of `replace_section_text`, `rewrite_bullet`,
  `insert_bullet`, `delete_bullet`, `reorder_bullets`, `add_skill`,
  `remove_skill`, `rewrite_entry`. The first implementation rebuilds the
  working resume from `replace_section_text`, `rewrite_bullet`,
  `insert_bullet`, and `add_skill`; the others round-trip through review
  but do not yet mutate the resume on apply.
- `confidence` is one of `high`, `medium`, `low` (a legacy numeric value
  in `[0, 1]` is still accepted for backward compatibility); `risk` is one
  of `low`, `medium`, `high`; `status` is one of `pending`, `accepted`,
  `rejected`, `revised` and starts as `pending`.
- `evidence_refs` are compact `{source, quote}` pairs backing the
  suggestion. Suggestions must not introduce unsupported claims; weak or
  user-provided evidence must be reflected in `risk`.

**Review lifecycle and storage.** On import the suggestions document is
stored on `ResumeVersion.suggestions_json`, and the base
`tailored_resume.json` is captured in
`ResumeVersion.suggestion_review_state` as `base_resume_json`. The
review endpoints under `/resume-versions/{id}` mutate per-suggestion
`status` in place:

- `GET  /resume-versions/{id}/suggestions` — list suggestions + review state.
- `POST /resume-versions/{id}/suggestions/{sid}/accept` — mark `accepted`.
- `POST /resume-versions/{id}/suggestions/{sid}/reject` — mark `rejected`.
- `POST /resume-versions/{id}/suggestions/{sid}/revise` — store a free-text
  `instruction` and mark `revised` (captured for a later revision run, not
  regenerated live).
- `POST /resume-versions/{id}/apply-suggestions` — rebuild a working
  structured resume by applying every `accepted` suggestion onto
  `base_resume_json`, persisting the result as `working_resume_json` in
  `suggestion_review_state`. Because the applied state keeps the
  `tailored_resume.json` schema, it stays renderable: when the source run
  directory exists, a best-effort `output/applied_resume.docx` is rendered
  via `resume_docx_renderer.py`.

This builds on the deterministic DOCX renderer (task 111): the renderer's
schema is the shared structured-resume shape that both the base resume and
the applied working resume conform to.

`progress/progress.log` is an append-only stream of short user-facing phase
events (e.g., `Reading job description`, `Drafting tailored resume markdown`).
The runtime prompt instructs Claude to append one plain-language line per
phase, never to overwrite earlier lines, and never to include secrets, raw
prompts, hashes, or internal paths. Progress events are informational only —
they do not satisfy the required-output contract, and a run that writes
progress lines but omits a required output file is still a failed run.

### Runtime permission expectation

The backend worker invokes Claude Code non-interactively. To let Claude write
the output files without an operator-typed approval, the worker:

- launches the subprocess with `cwd=<run_dir>` (Claude Code's default access
  scope), so writes outside the run directory are not auto-permitted;
- ensures `<run_dir>/output/` exists before launch, since the `acceptEdits`
  permission mode only approves file edits — it does not create directories;
- passes a permission-mode flag (default `acceptEdits`) so the
  `Edit`/`Write` tool calls inside the run directory are auto-approved
  rather than queued for an operator prompt.

The permission mode is configurable via the `JOBAPPLY_CLAUDE_PERMISSION_MODE`
environment variable. Local-dev defaults to `acceptEdits` so a draft run
completes without manual approval. The mode is appended to the run log
(`jobapply: permission mode=<mode>`) alongside the cwd and output directory,
without exposing secrets.

The worker does not pass `--add-dir` or otherwise broaden Claude's write scope
beyond the run directory.

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

### Run log

The worker writes a `run.log` file inside `runs/<run_id>/` capturing both:

- the Claude subprocess's stdout/stderr (interleaved), and
- worker-owned progress milestones prefixed with `jobapply:` (for example
  `jobapply: launching Claude Code`, `jobapply: validating output files`,
  `jobapply: missing expected output file: output/tailored_resume.docx`,
  `jobapply: marking run failed`).

The `jobapply:` lines are written before/after the subprocess so the user can
see meaningful progress even when Claude Code itself produces sparse output.
The file is truncated on each invocation. `GET /runs/{id}/log` returns the
last `N` non-empty lines from this file for the live-progress UI; the
endpoint reads only the tail and strips ANSI escape sequences, never
exposing files outside the run directory. `run.log` is the operator/technical
stream — the default UI surfaces it under *Advanced details* only.

### Progress log

The worker also creates `progress/progress.log` inside `runs/<run_id>/` and
truncates it on every invocation. This file is the user-facing progress feed:
plain-language one-liners with no `jobapply:` prefix and no ANSI codes. Two
writers append to it:

- **Claude Code**, as instructed by the runtime prompt, writes one short line
  per phase (e.g., `Reading job description`,
  `Drafting tailored resume markdown`, `Validating required outputs`).
- **The worker**, on a background thread, appends fallback heartbeats while
  the subprocess is running and Claude has not produced its own events
  (e.g., `Claude Code is running — 15 seconds elapsed`). The heartbeat
  interval defaults to 15 seconds and can be tuned (or disabled) via the
  `JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS` environment variable. Setting it to
  `0` disables the heartbeat thread entirely.

`GET /runs/{id}/progress` returns the last `N` non-empty lines from this
file. The default *Recent activity* panel on the run and job pages prefers
this feed; if it is empty, the UI may fall back to `run.log`. Progress lines
do not satisfy the required-output contract.

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
  "updated_at": "...",
  "input_files": {},
  "expected_outputs": [],
  "prompt_hash": "...",
  "input_hash": "...",
  "tailoring_method": "auto",
  "llm_provider": "claude_code",
  "status": "created",
  "prompt_id": "resume_tailoring",
  "prompt_source": "default",
  "prompt_snapshot_path": "input/prompt_snapshot.md"
}
```

### `tailoring_method`

Describes how the run produces its tailored draft.

Allowed values:

- `auto` — the existing Claude Code subprocess path. Default for new runs.
- `word_handoff` — packages inputs for a manual or semi-automated Claude
  for Word editing session. Reads/writes happen inside `word_handoff/`.

Backwards compatibility: runs created before this field existed have no
`tailoring_method` key. Readers must treat a missing or null value as
`auto`, since that was the only behavior the system supported.

### `llm_provider`

Identifies which CLI tool produced the run's artifacts. This field is
orthogonal to `tailoring_method`: it disambiguates which `auto`-flow
worker ran, and on `word_handoff` runs it carries a descriptive sentinel
so the key is never absent from `metadata.json`.

Recognized values:

- `claude_code` — the Claude Code CLI worker (the default `auto`
  provider).
- `codex` — the Codex CLI worker.
- `gemini` — the Gemini CLI worker.
- `claude_for_word` — sentinel used on runs whose `tailoring_method`
  is `word_handoff`, where no backend CLI is invoked but the field
  must still be present.

Provider ids must be stable, lowercase, and snake_case. Adding a new
provider does not change the required output filenames under `output/`:
every provider satisfies the same read and write boundaries documented
above. See ADR-009 for the decision record covering provider selection,
the cross-provider invariants reasserted from ADR-002 and ADR-004, and
the rationale for keeping this field orthogonal to `tailoring_method`.

### Prompt provenance

Three fields record which runtime prompt drove this run so the result
stays reproducible:

- `prompt_id` — one of `resume_tailoring` (first-draft runs) or
  `resume_revision` (follow-up runs created from user feedback). New
  ids may be added to the registry in `app.prompt_harness`; backwards
  compatibility for older runs is preserved because the snapshot file
  itself is the source of truth.
- `prompt_source` — `default` when the run used the shipped prompt
  under `runtime_prompts/<id>.md`, or `override` when it used the
  local override under
  `candidate_context/settings/prompt_overrides/<id>.md`.
- `prompt_snapshot_path` — relative path inside the run directory to
  the verbatim prompt body the worker used (currently
  `input/prompt_snapshot.md`). The existing `prompt_hash` field
  remains the sha256 of that file's bytes.

The override directory is gitignored — overrides are local-machine
settings. The prompt harness editor UI (Advanced → *Prompt harnesses*)
lets an operator create, edit, validate, and delete overrides without
touching the filesystem directly. Validation only emits warnings about
missing required contract elements (`tailored_resume.md`,
`claim_audit.md`, `ats_audit.md`, etc.); it does not block a save. An
override that omits a required output filename can therefore produce a
failing run, which the operator can recover from by clicking *Restore
default* in the same UI.

### `status`

Workflow-level status of the run, spanning both the `auto` and
`word_handoff` paths. Allowed values:

- `created`
- `input_ready`
- `auto_tailoring_running`
- `auto_tailoring_failed`
- `auto_tailoring_complete`
- `word_handoff_ready`
- `waiting_for_word_result`
- `word_result_imported`
- `validation_failed`
- `completed`
- `failed`

This field is distinct from the DB-level `ClaudeRun.status` column. The
DB column tracks the Claude subprocess lifecycle and continues to use the
shorter set of values (`created`, `running`, `completed`, `failed`,
`imported`) that pre-existing routers and tests rely on. The metadata
status is the source of truth for the broader workflow, including states
that have no DB representation yet (e.g. `waiting_for_word_result`).

Backwards compatibility: runs created before this field existed have no
`status` key. Readers must treat a missing or null value as `created`.

## Exports and downloads (task 122)

The internal artifact names under `output/` are **stable** — workers,
`run_import`, and the validation tests depend on them exactly as listed
above. They are never renamed.

User-facing downloads and exports use a separate, human-readable filename
derived from `(candidate, company, job title, run created date)` so a
folder of generated resumes is distinguishable, e.g.
`Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx`.
The mapping lives in `backend/app/resume_export.py`
(`build_resume_export_filename`); the candidate name is a best-effort read
of `candidate_context/candidate_profile.md` and falls back to `Resume`
when absent.

Surfaces:

- `GET /runs/{run_id}/artifacts/{artifact_name}/download` and
  `GET /runs/{run_id}/download-resume` stream an artifact as an attachment
  with the readable filename. Only the allow-listed names
  (`tailored_resume.docx`, `tailored_resume.md`, `claim_audit.md`,
  `ats_audit.md`, `recruiter_review.md`, `template_fidelity_audit.md`,
  `change_log.md`) are served; any other name or a traversal attempt is a
  400, a missing-but-allowed artifact is a 404.
- `POST /runs/{run_id}/export` copies the available artifacts into a managed
  per-run subfolder under `candidate_context/exports/`
  (`<date>__<company>__<job>__<short_run_id>/`), renaming the DOCX to the
  readable filename and keeping the audit/markdown files under their stable
  names. Existing export folders are never overwritten — a collision gets a
  `-2`, `-3`, … suffix. The exports root is overridable via
  `JOBAPPLY_EXPORTS_ROOT`.

Exports are **copies** — the internal run artifacts are left untouched.
