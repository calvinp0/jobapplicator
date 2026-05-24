# Task 039: Revision feedback flow

Task ID: `039-revision-feedback-flow`

## Goal

Add the frontend revision-feedback flow on `ResumeVersionDetailPage`,
wiring it to the backend endpoint introduced by task 045 and surfacing
the resulting follow-up tailoring run in the job workspace.

## Background

The design for this flow is fixed by
[`docs/adr/008-revision-feedback-flow.md`](../docs/adr/008-revision-feedback-flow.md).
The backend endpoint, schemas, and run-directory wiring have all
landed:

- Endpoint: `POST /resume-versions/{version_id}/revision-feedback`
  (see `backend/app/routers/resume_versions.py`).
- Request body: `{ "feedback_markdown": string, "structured_flags"?: object }`
  (see `RevisionFeedbackCreate` in `backend/app/schemas.py`).
  `feedback_markdown` must be non-empty.
- Response (201 Created): `RevisionFeedbackRead`, including
  `id`, `job_id`, `source_resume_version_id`,
  `followup_claude_run_id`, `feedback_markdown`, `status`,
  `created_at`. The follow-up `ClaudeRun` is created server-side and
  its id is returned on the response.
- The runtime tailoring prompt already consumes
  `runs/<run_id>/input/revision_feedback.md` (task 046) and reasserts
  the ADR-004 evidence-constraint rule.

The UX spec
([`docs/product/frontend_cockpit_ux.md`](../docs/product/frontend_cockpit_ux.md))
describes a "Request revisions" action on
`ResumeVersionDetailPage` alongside `Approve draft`. The intended
behavior is:

1. The user has a generated draft they don't want to approve as-is.
2. They click `Request revisions`, describe what to change, optionally
   tick common-asks checkboxes, and submit.
3. The frontend posts to the endpoint above, receives the new
   `followup_claude_run_id`, and navigates the user to the follow-up
   run's status view (which already polls via task 035).
4. When that run imports a new `ResumeVersion`, it appears in the job
   workspace step 4 as the next `Draft N`, with a visible "revises
   Draft N" pointer resolved via the `revision_feedbacks` join (see
   ADR-008 "Linking").

## Scope

Frontend-only. Add the `Request revisions` action and form on
`ResumeVersionDetailPage`, the API client function, the response
routing, and the "revises Draft N" pointer on `JobDetailPage` step 4.
Backend, runtime prompts, and ADRs are out of scope; they already
exist.

### Allowed files

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

### Forbidden files

```text
backend/**
extension/**
runtime_prompts/**
candidate_context/**
docs/**
scripts/**
```

### Out of scope

- Any backend, runtime-prompt, or ADR change. Those are tasks
  042–046 and have already landed.
- Changes to draft approval language covered by task 036.
- Changes to application submit wording covered by task 037.
- Re-opening ADR-008 decisions (endpoint shape, status lifecycle,
  evidence-constraint rule).

## Required behavior

On `ResumeVersionDetailPage`:

- Add a `Request revisions` action next to `Approve draft`.
- Reveal a structured feedback form when clicked: a required
  `feedback_markdown` textarea and optional common-asks checkboxes
  (e.g., "Shorten", "Reorder sections", "Emphasize X over Y"). The
  checkbox set is collected into a `structured_flags` object on
  submit; if no checkboxes are ticked, omit `structured_flags` from
  the request body.
- Submit via a new `submitRevisionFeedback(versionId, body)` client in
  `frontend/src/api/index.ts` that calls
  `POST /resume-versions/{versionId}/revision-feedback`. The TypeScript
  types for the request and response go in
  `frontend/src/api/types.ts` and must match
  `RevisionFeedbackCreate` / `RevisionFeedbackRead` from
  `backend/app/schemas.py`.
- On success, navigate the user to the follow-up run's detail view
  using `followup_claude_run_id` from the response (the existing
  tailoring-progress polling from task 035 then takes over).
- On failure, render the error message through `extractApiDetail`
  from `frontend/src/lib/api-errors.ts` (the shared helper from
  task 033). Do not invent ad-hoc error formatting.
- Disable the submit control while the request is in flight and
  while `feedback_markdown` is empty.

On `JobDetailPage` step 4:

- When a `ResumeVersion` was produced by a revision run, display a
  visible "revises Draft N" pointer next to that draft entry. The
  pointer is resolved by matching the draft's originating
  `claude_run_id` to a `revision_feedbacks` row's
  `followup_claude_run_id`; the prior draft is then looked up by
  `source_resume_version_id`. The existing `revisionFeedbacks` list
  endpoint (or the per-version data already loaded for step 4) is
  the data source — do not add new backend endpoints for this.

## Acceptance criteria

- `ResumeVersionDetailPage` exposes a `Request revisions` action that
  reveals a feedback form with a required free-text field and
  optional common-asks checkboxes.
- Submitting the form calls
  `POST /resume-versions/{versionId}/revision-feedback` with body
  shape `{ feedback_markdown, structured_flags? }` and, on success,
  navigates the user to the follow-up run identified by
  `followup_claude_run_id` from the response.
- API errors are surfaced via `extractApiDetail`.
- `JobDetailPage` step 4 shows a "revises Draft N" pointer for any
  draft that resolves to a `revision_feedbacks` row via its
  originating `claude_run_id`.
- Type definitions for the request and response in
  `frontend/src/api/types.ts` match `RevisionFeedbackCreate` and
  `RevisionFeedbackRead` in `backend/app/schemas.py`.
- All frontend tests pass; `npm run build` succeeds.
- No file outside the `Allowed files` list is modified.

## Verification

```bash
cd frontend && npm test
cd frontend && npm run build
```

## Git instructions

Commit locally on the task branch with the message:

```text
Add revision feedback flow for drafts
```

Do not push.
Do not implement unrelated product features.
Do not edit backend, runtime prompts, or extension files.
