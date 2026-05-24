# ADR-008: Revision Feedback Flow

## Status

Accepted

## Context

After a tailoring run produces a `ResumeVersion`, the user may not want
to approve the draft as-is. They want to describe what to change and
have a follow-up tailoring run produce a revised draft, with the prior
draft and the user's feedback as input. The frontend placeholder for
this flow is tracked in `agent_tasks/039-revision-feedback-flow.md` and
is blocked on this design.

The flow has to reconcile several existing constraints:

- A previous draft (`ResumeVersion`) already exists in the DB, produced
  by an earlier `ClaudeRun`.
- A new tailoring `Run` must be created that the worker can execute
  with knowledge of (a) the prior draft and (b) the user's feedback.
- The same draft may receive several rounds of feedback over time, and
  not every feedback submission will succeed on the first attempt — the
  follow-up run may fail and be retried, or be replaced by newer
  feedback before any draft is imported.
- Evidence-constraint rules from ADR-004 must still hold. Feedback may
  not be used to bypass the rule that concrete claims need supporting
  source material.
- Per ADR-002, Claude Code may not mutate the database. The backend
  writes input files into `runs/<run_id>/input/` and imports validated
  outputs after the run completes.

## Decision

### Storage

Revision feedback is persisted in a dedicated `revision_feedbacks`
table. Feedback is not stored as columns on `Run` or `ResumeVersion`.

The table has at least the following columns:

```
RevisionFeedback
  id
  job_id
  source_resume_version_id   FK -> resume_versions.id
  followup_claude_run_id     FK -> claude_runs.id, nullable
  feedback_markdown          text
  status                     enum (created | used | superseded)
  created_at                 timestamp
```

Exact column names and types are finalized by task 044 (the migration
task), but the relationships above are fixed by this ADR.

### Linking

The link from a prior draft to its follow-up tailoring run lives on the
`revision_feedbacks` row, via `source_resume_version_id` and
`followup_claude_run_id`. There is no `runs.parent_resume_version_id`
column and no `resume_versions.parent_resume_version_id` column for
this purpose.

The `ClaudeRun` itself stays unaware of why it was created; it only
knows it is a tailoring run. The "this run was triggered by feedback on
draft X" relationship is reconstructed by joining through
`revision_feedbacks`.

When the imported follow-up `ResumeVersion` needs to display "revises
Draft N" in the UI, the frontend resolves that relationship by looking
up the `revision_feedbacks` row whose `followup_claude_run_id` matches
the new draft's originating run.

### Run input surface

When the backend creates the follow-up `ClaudeRun`, it writes the
feedback into the run directory as a discrete input file at:

```
runs/<run_id>/input/revision_feedback.md
```

The feedback is not spliced inline into `tailoring_prompt.md` or any
other generated prompt blob. The runtime prompt instructs the worker to
read `revision_feedback.md` as a separate input, alongside the prior
draft's `tailored_resume.md` (also surfaced as an input file in the new
run directory; the exact filename for the prior draft is finalized by
task 043, which updates the run directory contract).

`revision_feedback.md` carries:

- the user's free-text feedback (markdown body),
- an identifier for the source `ResumeVersion` it targets,
- optionally, structured feedback flags (e.g., common-asks checkboxes
  from the frontend) rendered as a small frontmatter or list at the top
  of the file.

### Status lifecycle

`revision_feedbacks.status` follows this lifecycle:

- `created` — feedback was submitted by the user. The status remains
  `created` while the follow-up run is queued, running, has failed, or
  has completed but its outputs have not yet been imported into a
  `ResumeVersion`.
- `used` — the follow-up run completed *and* its outputs were
  successfully imported into a new `ResumeVersion`. `used` means the
  feedback actually produced a draft; it is not set merely because a
  run was attempted.
- `superseded` — newer feedback for the same
  `source_resume_version_id` was submitted before this feedback row
  reached `used`. The superseded row is retained for audit but is no
  longer a candidate for re-run.

Explicit non-rules:

- A failed or aborted follow-up `ClaudeRun` does NOT flip the feedback
  to a failure state. Run-level failure is represented on
  `ClaudeRun.status` and `ClaudeRun.error_message`. Duplicating that
  failure state onto `RevisionFeedback` would create two sources of
  truth for the same event.
- A feedback row may be retried by creating a new follow-up
  `ClaudeRun` and updating `followup_claude_run_id` to point at the
  new run, as long as no successful import has yet promoted the row
  to `used`. The status stays `created` across retries.

### Evidence preservation

Feedback cannot override ADR-004. The worker must still refuse to add
unsupported claims even when the user's feedback explicitly asks for
them. The runtime prompt for revision runs must reassert the
evidence-constraint rule and the claim audit must continue to flag any
gap between requested changes and available evidence. If the user's
feedback asks for an unsupported claim, the revised draft must either
omit it or surface it as a gap in the claim audit — never silently
insert it.

### API surface (sketch)

The backend exposes a single endpoint to submit feedback and create the
follow-up run in one call:

- `POST /api/resume-versions/{resume_version_id}/revision-feedback`
- Request body: `{ "feedback_markdown": "...", "structured_flags": {...} }`
  (structured flags optional).
- Response: the new `RevisionFeedback` record, including
  `followup_claude_run_id`, so the frontend can navigate to the
  follow-up run's status view.

The endpoint performs three actions atomically from the caller's
perspective: insert the `revision_feedbacks` row, create the
`ClaudeRun`, and stage `runs/<run_id>/input/revision_feedback.md`. The
full request/response contract is finalized in task 045.

## Rationale

A dedicated `revision_feedbacks` table is preferred over columns on
`Run` or `ResumeVersion` because feedback is its own event. One draft
can receive multiple feedback attempts over time, and each attempt has
its own text, its own follow-up run, and its own lifecycle. Modeling it
as a join row means the prior-draft → follow-up-run link lives on the
row that represents the feedback itself, which is the thing being acted
on.

Putting the link on `runs.parent_resume_version_id` instead would
collapse the feedback into a run attribute and lose the ability to
represent multiple feedback rounds and retries cleanly. It would also
force the backend to write user-authored text into a column whose only
purpose is to point at a draft.

Writing the feedback as a discrete file at
`runs/<run_id>/input/revision_feedback.md` keeps user input distinct
from machine-generated prompt material. The run directory is already
the provenance surface for a tailoring run (per ADR-002 and the
`docs/contracts/claude_run_directory.md` contract); a separate hashable
file is auditable on its own, and re-renders of `tailoring_prompt.md`
do not affect or obscure what the user actually said.

The status lifecycle treats `used` as "produced an imported draft"
rather than "a run was attempted" so that retries and transient run
failures do not consume the feedback. Keeping run-level failure on
`ClaudeRun` avoids a class of bugs where `RevisionFeedback.status` and
`ClaudeRun.status` drift out of sync.

The evidence-preservation invariant prevents the revision flow from
becoming a backdoor around ADR-004. Without it, users could ask for
claims they cannot support and receive them, which would defeat the
purpose of evidence-constrained tailoring.

## Consequences

- Task 044 introduces a `revision_feedbacks` table and migration.
- Task 043 updates `docs/contracts/claude_run_directory.md` to include
  `input/revision_feedback.md` as a valid input file for revision runs
  and to specify how the prior draft is surfaced as an input.
- Task 045 implements the
  `POST /api/resume-versions/{id}/revision-feedback` endpoint, which
  inserts the feedback row, creates the follow-up `ClaudeRun`, and
  stages the run directory.
- Task 046 updates runtime prompts so the revision tailoring prompt
  reads `revision_feedback.md`, reasserts the evidence-constraint rule
  from ADR-004, and requires the claim audit to flag user-requested
  changes that lack supporting evidence.
- Task 039 (frontend) can now describe its API call concretely: submit
  feedback to the new endpoint and navigate to the returned follow-up
  run.
- `ClaudeRun` does not gain new columns for revision context. The
  follow-up run is a normal tailoring run that happens to have an
  extra input file and is referenced by a `revision_feedbacks` row.

## Alternatives Considered

- **Store feedback as a column on `Run` (e.g., `runs.feedback_markdown`
  + `runs.parent_resume_version_id`)**: rejected. Collapses multiple
  feedback events into run attributes, loses the ability to model
  retries and supersession, and mixes user-authored text into the
  run-tracking table.
- **Store feedback as a column on `ResumeVersion`**: rejected. A draft
  can receive multiple rounds of feedback over time; a single text
  column on the draft cannot represent that, and it conflates the
  draft (an artifact) with the user's feedback (an event acting on
  the artifact).
- **Inline feedback into `tailoring_prompt.md`**: rejected. Mixes
  user-authored input with machine-generated prompt material, loses
  per-input hashability, and makes it harder for the worker prompt to
  cite "the user said X" distinctly from "the system instructed Y".
- **Represent feedback failure on `RevisionFeedback.status` (e.g.,
  add a `failed` state)**: rejected. Duplicates `ClaudeRun.status` /
  `ClaudeRun.error_message` and creates two sources of truth for the
  same event.
- **Allow feedback to override evidence constraints when the user
  explicitly asks**: rejected. Would silently undo ADR-004; the
  revision flow must remain a positioning/wording lever, not an
  evidence escape hatch.

## Notes

- This ADR refers to and is bounded by ADR-002 (Claude Code Worker
  Boundary) and ADR-004 (Evidence-Constrained Resume Tailoring).
- Downstream work: task 043 (contract update), task 044 (schema /
  migration), task 045 (API endpoint), task 046 (runtime prompt),
  task 039 (frontend, previously blocked).
