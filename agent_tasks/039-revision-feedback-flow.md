# Task 039: Revision feedback flow (BLOCKED — design first)

Task ID: `039-revision-feedback-flow`

Status: **blocked**

## Goal

Document the future revision-feedback flow needed to let users request changes to
generated drafts, and stage the frontend work so it can begin once the backend is
designed.

## Background

The UX spec ([`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md))
describes a "Future revision feedback flow" alongside `Approve draft` on
`ResumeVersionDetailPage`. The intended user behavior is:

1. The user has a generated draft they don't want to approve as-is.
2. They click `Request revisions`, describe what to change, and submit.
3. A new tailoring run is created, parameterized by the prior draft and the feedback.
4. The new draft appears in the job workspace as the next `Draft N`, with a visible link
   back to the draft it revises.

This task is a placeholder so the work is tracked. It must not be run yet.

## Blocker

```text
Backend does not yet model revision feedback. Implementing this requires a schema/API
decision and likely an ADR update before frontend work begins.
```

**Do not run until unblocked by a backend/API design task.** Specifically, the following
must exist first:

- A schema decision for revision feedback (where feedback is stored, how it links to the
  prior draft and the new run).
- An API contract for creating a revision-feedback-driven tailoring run.
- An ADR update under `docs/adr/` capturing the decision.

A blocker-resolution task should land before this one is moved to `ready` in the queue.

## Scope (preliminary, to be refined when unblocked)

When unblocked, this task will touch frontend draft review and job workspace surfaces, plus
new tests:

### Allowed files (preliminary)

```text
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/pages/JobDetailPage.tsx
frontend/src/api/index.ts
frontend/src/api/types.ts
frontend/src/styles.css
frontend/src/test/**
agent_tasks/039-revision-feedback-flow.md
agent_tasks/queue.yaml
```

The final allowed file list must be tightened when this task is moved out of `blocked`.

### Forbidden files

```text
backend/**
extension/**
runtime_prompts/**
candidate_context/**
```

(Backend work belongs to the unblock task, not this one. This task remains
frontend-only when it runs.)

### Out of scope

- Implementing the backend revision-feedback schema/API. That is the unblocking task.
- Any change to draft approval language already covered by task 036.
- Any change to application submit wording already covered by task 037.

## Required behavior (preliminary)

When unblocked, the frontend must:

- Add a `Request revisions` action on `ResumeVersionDetailPage` next to `Approve draft`.
- Provide a structured feedback form (free-text plus optional checkboxes for common asks).
- Submit feedback via the new API and create the follow-up tailoring run.
- Show the new draft in `JobDetailPage` step 4 as the next `Draft N`, with a visible
  pointer to the draft it revises.
- Surface error messages via `extractApiDetail`.

## Acceptance criteria (preliminary)

To be finalized when unblocked. At minimum:

- Submitting feedback creates a new run linked to the prior draft.
- The new draft is visibly labeled as a revision of the prior draft.
- All frontend tests pass.

## Verification

```bash
cd frontend && npm test
cd frontend && npm run build
```

## Git instructions

Do not run this task yet. Do not push.
Do not implement unrelated product features.
Do not edit backend unless explicitly listed.
Do not edit extension files.

When this task is eventually executed, commit locally with message:

```text
Add revision feedback flow for drafts
```
