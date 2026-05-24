# Task 042: ADR for revision feedback flow

Task ID: `042-adr-revision-feedback`

## Goal

Write a new ADR (ADR-008) that records the decision for how revision
feedback on a generated resume draft is stored, how it links back to the
prior draft, and how it parameterizes a follow-up tailoring run. This ADR
is the source the downstream contract, backend, and runtime-prompt tasks
will reference.

## Background

Read first:

- `docs/product_requirements.md` (resume tailoring + versioning sections)
- `docs/architecture.md` (Claude Code Worker Boundary, Human-in-the-Loop Rule)
- `docs/adr/000-template.md`
- `docs/adr/002-claude-code-worker-boundary.md`
- `docs/adr/004-evidence-constrained-resume-tailoring.md`
- `docs/adr/006-candidate-context-as-source-material.md`
- `docs/contracts/claude_run_directory.md`
- `agent_tasks/039-revision-feedback-flow.md` (the frontend placeholder this design unblocks)

Context the ADR must reconcile:

- A previous draft (`ResumeVersion`) exists in the DB, produced by a Run.
- The user wants to request revisions on that draft.
- A new tailoring `Run` must be created that the worker can execute with
  knowledge of (a) the prior draft and (b) the user's feedback.
- Evidence-constraint rules (ADR-004) must still hold; feedback may not
  cause the worker to invent unsupported claims.
- Claude Code may not mutate the database (ADR-002); the backend writes
  input files into `runs/<run_id>/input/` and imports outputs.

## Scope

Add `docs/adr/008-revision-feedback-flow.md` following the structure of
`docs/adr/000-template.md`. The ADR must take a concrete position on, at
minimum:

- **Storage**: revision feedback MUST be persisted in a new
  `revision_feedbacks` table. Do not put it on `Run` or `ResumeVersion`
  columns. Rationale to record in the ADR: feedback is its own
  event/object — one draft can receive multiple feedback attempts over
  time, and each feedback item links cleanly to a source draft, the
  feedback text, and the follow-up run it parameterizes. The ADR must
  name the table and its columns. Suggested shape (the ADR may refine
  names but must preserve the relationships):

  ```
  RevisionFeedback
    id
    job_id
    source_resume_version_id
    followup_claude_run_id   (nullable until the follow-up run is created)
    feedback_markdown
    status                   (created | used | superseded)
    created_at
  ```

- **Linking**: the follow-up `Run` MUST be linked to the prior draft
  *through* the `revision_feedbacks` row, via
  `revision_feedbacks.source_resume_version_id` and
  `revision_feedbacks.followup_claude_run_id`. The ADR must state this
  explicitly and explain why a dedicated join row is preferred over a
  direct `runs.parent_resume_version_id` column (the feedback object is
  the thing being acted on; the link belongs on it).
- **Run input surface**: the backend MUST write the feedback into the
  run directory as a separate input file at
  `runs/<run_id>/input/revision_feedback.md`. Do not splice the feedback
  inline into a generated prompt blob. Rationale to record in the ADR:
  the run directory is already evidence/provenance oriented, so keeping
  user feedback as a discrete, hashable input file preserves auditability
  and keeps user input distinct from machine-generated prompt material.
  The ADR must describe the structure the file carries.
- **Status lifecycle**: the ADR MUST commit to the following lifecycle
  for `revision_feedbacks.status` so task 044 does not invent it while
  writing the model:

  - `created`: feedback has been submitted by the user but has not yet
    produced an imported follow-up draft. Status remains `created`
    while the follow-up run is queued, running, failed, or
    completed-but-not-yet-imported.
  - `used`: the follow-up run completed *and* its outputs were
    successfully imported into a new `ResumeVersion`. `used` means the
    feedback actually produced a draft — not merely that a run was
    attempted.
  - `superseded`: newer feedback for the same `source_resume_version_id`
    replaced this row before it reached `used`.

  Explicit non-rules the ADR must state:

  - Failed or aborted follow-up runs do NOT flip the feedback to a
    failure state. Run-level failure is represented on
    `ClaudeRun.status` / `ClaudeRun.error_message`. This avoids
    duplicating failure state between `RevisionFeedback` and
    `ClaudeRun`.
  - A feedback row may be retried by creating a new follow-up run
    without changing its status, as long as no successful import has
    occurred.

- **Evidence preservation**: the explicit invariant that feedback cannot
  override ADR-004. Spell out that the worker must still refuse to add
  unsupported claims even when the user asks for them in feedback, and
  that the claim audit must reflect this.
- **API surface (sketch)**: a short description of the new
  backend endpoint shape (URL, method, request body, response). The
  full contract is up to task 045, but the ADR must commit to the
  high-level shape so 044 and 045 do not contradict each other.

## Allowed files

```
docs/adr/008-revision-feedback-flow.md
agent_tasks/042-adr-revision-feedback.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/**
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/contracts/**
docs/product_requirements.md
docs/architecture.md
docs/adr/000-template.md
docs/adr/001-local-first-mvp.md
docs/adr/002-claude-code-worker-boundary.md
docs/adr/003-human-in-the-loop-submission.md
docs/adr/004-evidence-constrained-resume-tailoring.md
docs/adr/005-browser-assisted-current-page-capture.md
docs/adr/006-candidate-context-as-source-material.md
docs/adr/007-capture-provider-architecture.md
```

Existing ADRs are immutable. Only ADR-008 may be added.

## Out of scope

- Backend schema or migration code (task 044).
- Backend API endpoints (task 045).
- Contract update for the run directory (task 043).
- Runtime prompt changes (task 046).
- Frontend changes (task 039 / future).

## Acceptance criteria

- `docs/adr/008-revision-feedback-flow.md` exists and follows the
  ADR template structure (Status, Context, Decision, Rationale,
  Consequences, Alternatives Considered, Notes).
- Status is `Accepted`.
- The ADR explicitly names:
  - the `revision_feedbacks` table as the storage location, with its
    columns (including `source_resume_version_id`,
    `followup_claude_run_id`, `feedback_markdown`, `status`),
  - that the prior draft → follow-up run link lives on the
    `revision_feedbacks` row (via `source_resume_version_id` and
    `followup_claude_run_id`), not on `runs` or `resume_versions`
    directly,
  - the input filename `runs/<run_id>/input/revision_feedback.md` and
    the rule that feedback is a discrete input file, not inlined into a
    prompt,
  - the `status` lifecycle (`created` → `used`, optional `superseded`),
    including the explicit rule that run-level failure is represented on
    `ClaudeRun` and does not flip the feedback to a failure state,
  - the evidence-preservation invariant,
  - and a one-paragraph API-shape sketch.
- The ADR references ADR-002 and ADR-004 by id.
- No file under `docs/adr/` other than `008-revision-feedback-flow.md`
  is modified.
- No file outside `docs/adr/` or the listed agent_tasks files is
  modified.

## Verification

```bash
ls docs/adr/
test -f docs/adr/008-revision-feedback-flow.md
```

## Git instructions

Commit locally on the task branch with the message:

```
Add ADR-008 for revision feedback flow
```

Do not push.
