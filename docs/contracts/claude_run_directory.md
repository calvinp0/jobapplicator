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
│   ├── master_resume.docx        # optional source DOCX (any accepted name)
│   ├── master_resume_extracted.md           # written by the backend when a DOCX is present
│   └── master_resume_extraction_error.md    # written instead if extraction fails
├── output/
│   ├── tailored_resume.docx
│   ├── tailored_resume.md
│   ├── change_log.md
│   ├── claim_audit.md
│   └── ats_audit.md
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
├── 03_job_description.txt           # the captured job description text
└── 04_instructions.md               # manual steps for the operator
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
input/master_resume.docx
input/master_resume_extracted.md
input/master_resume_extraction_error.md
```

`input/revision_feedback.md` is only present on follow-up tailoring runs (see ADR-008); when absent, the worker must treat the run as a first-draft tailoring run.

## Claude Code Write Boundary

Claude Code may write:

```text
output/tailored_resume.docx
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
output/ats_audit.md
progress/progress.log
```

`output/ats_audit.md` is the structured ATS audit emitted by the
tailoring worker. It records the keywords extracted from the job
description, their classification (required / preferred / industry /
role), how each keyword was covered by the tailored resume (or why it
was not used), and an ATS-formatting check. The audit is mandatory:
runs missing this file are marked failed by the same output validation
that gates the other required outputs.

Claude Code must not write outside the run directory.

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
