# Task 072: Frontend applications list with timeline stage badges

Task ID: `072-frontend-applications-list-timeline`

## Goal

Refresh `ApplicationsPage` so each row presents the application's
timeline stage clearly — submitted, awaiting confirmation, confirmation
received, response received, rejected, interview, offer — using the
server-derived `timeline_stage` from task 071. Also surface the latest
email evidence summary (sender + subject + received_at) when present.

## Background

Read first:

- `docs/adr/010-application-status-timeline.md`
- `docs/contracts/application_status.md`
- `frontend/src/pages/ApplicationsPage.tsx` (current implementation)
- `frontend/src/pages/DashboardPage.tsx` (existing job-stage badge
  pattern; mirror its variant naming where it overlaps)
- `frontend/src/lib/workflow.ts` (shared workflow language helpers)
- `frontend/src/api/types.ts`, `frontend/src/api/index.ts`
- `frontend/src/styles.css` (existing `status-badge-*` variants)
- `frontend/src/test/applicationsPage.test.tsx`
- `frontend/src/test/workflow.test.ts`

The backend task (071) will add `timeline_stage`, `last_email_link`,
and `email_link_count` to the `ApplicationRead` shape. This task wires
the frontend types and renders the new fields.

## Scope

- **API types**: extend the `Application` type in
  `frontend/src/api/types.ts` to include the new fields:
  `timeline_stage`, `last_email_link`, `email_link_count`. Add a new
  `EmailLink` type matching the contract's `EmailLinkRead` shape.
  Export both. Update `frontend/src/api/index.ts` only if needed to
  re-export the new type — do not add new API call functions in this
  task (task 073 owns the email-link create/list calls).

- **Shared labels and helpers** in `frontend/src/lib/workflow.ts`:
  - Add a `timelineStageLabel(stage: string): string` helper that
    maps each contract stage to a human label (e.g.
    `confirmation_received` → "Confirmation received",
    `response_received` → "Response received",
    `interview` → "Interview", etc.).
  - Add a `timelineStageVariant(stage: string): string` helper that
    maps each stage to an existing or new `status-badge-*` variant
    class for color coding. Reuse `pending`, `running`, `completed`,
    `approved`, `submitted` where they fit; add a small number of new
    variants only if existing ones cannot represent the new stages
    (e.g. `rejected`, `interview`, `offer`).
  - Add a `lastEmailSummary(app: Application): string | null` helper
    that returns a short one-line summary for the row
    (`"Confirmation from acme@example.com · 2h ago"`, etc.) or null.

- **ApplicationsPage** rendering:
  - Replace the current single-badge display with a row layout that
    shows: job title — company on the left, the timeline-stage badge,
    submitted-at when present, and the last-email summary when
    present.
  - When `email_link_count > 1`, append " · N emails" so users see at
    a glance how rich the timeline is.
  - Keep the existing "no applications yet" empty state.

- **Styles**: add any new badge variants used by
  `timelineStageVariant` to `frontend/src/styles.css`. Keep the new
  styles minimal and consistent with existing `status-badge-*` rules.

- **Tests** in `frontend/src/test/`:
  - Update `applicationsPage.test.tsx` to cover the new fields:
    render a list including a `draft`, a `sent`, a
    `confirmation_received`, a `rejected`, an `interview`, and an
    `offer` row, and assert the visible label for each.
  - Cover the `email_link_count > 1` " · N emails" decoration.
  - Cover the empty `last_email_link` case (no summary shown).
  - Add or extend `frontend/src/test/workflow.test.ts` to cover
    `timelineStageLabel` and `timelineStageVariant` for every stage.

## Allowed files

```
frontend/src/pages/ApplicationsPage.tsx
frontend/src/lib/workflow.ts
frontend/src/api/types.ts
frontend/src/api/index.ts
frontend/src/styles.css
frontend/src/test/applicationsPage.test.tsx
frontend/src/test/workflow.test.ts
agent_tasks/072-frontend-applications-list-timeline.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/**
frontend/src/pages/ApplicationDetailPage.tsx
frontend/src/pages/DashboardPage.tsx
frontend/src/pages/JobDetailPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/RunsPage.tsx
frontend/src/pages/JobsPage.tsx
frontend/src/pages/CapturesPage.tsx
frontend/src/pages/CaptureDetailPage.tsx
frontend/src/pages/ResumeVersionDetailPage.tsx
frontend/src/App.tsx
frontend/src/layout/**
```

Do not touch any other page in this task — `ApplicationDetailPage` is
the next task's responsibility, and the dashboard already derives its
job stage from local rules. Re-deriving timeline stage there is out
of scope.

## Out of scope

- The detail page email-links section (task 073).
- Calling the new EmailLink create/list endpoints (task 073).
- Dashboard changes.
- Backend changes.

## Acceptance criteria

- `frontend/src/api/types.ts` exports the extended `Application`
  shape and a new `EmailLink` type matching the contract.
- `frontend/src/lib/workflow.ts` exports
  `timelineStageLabel`, `timelineStageVariant`, and
  `lastEmailSummary`.
- `ApplicationsPage` renders the timeline-stage badge for every row
  using `timelineStageVariant` and `timelineStageLabel`.
- Rows with a `last_email_link` show the summary; rows without it
  do not.
- Rows with `email_link_count > 1` show " · N emails".
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` passes.
- No file outside `Allowed files` is modified.

## Verification

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit locally on the task branch with the message:

```
Add timeline stage badges to applications list
```

Do not push.
