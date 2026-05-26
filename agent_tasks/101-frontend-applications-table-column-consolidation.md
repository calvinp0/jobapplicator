# 101 — Consolidate Applications table columns

## Goal

Even after task 100 widens the Applications page and trims redundant
cell prefixes, the table still carries eight columns (Job, Status,
Submission, Email, Latest run, Updated, Next action, Actions). Several
of these duplicate information already visible elsewhere in the row:
"Submission" mostly restates the stage badge, "Latest run" is rarely
the user's primary concern from the list view, and "Updated" overlaps
with the Gmail-checked subtle line inside the Email cell.

This task consolidates the table down to a smaller set of columns that
fits comfortably without horizontal scroll while keeping the same
underlying information available to the user (either inline in a denser
cell, or one click away on the application detail page).

## Background

Read first:

- `docs/product_requirements.md` — Application Tracking section.
- `agent_tasks/100-frontend-applications-table-full-width.md` —
  predecessor task; this task assumes its layout/prefix changes have
  landed.
- `agent_tasks/095-redesign-applications-page-as-table.md` — original
  rationale for each column.
- `frontend/src/pages/ApplicationsPage.tsx` — current table markup.
- `frontend/src/lib/workflow.ts` — `submissionStatusLabel`,
  `runStatusLabel`, `applicationUpdatedLabel`, `lastEmailSummary`,
  `timelineStageLabel`, `timelineStageVariant`, `emailStatusLabel`.
- `frontend/src/test/applicationsPage.test.tsx` — existing tests; update
  them in lockstep.

## Scope

Reduce the Applications table to the following five columns, in order:

1. **Job** — title + company link (unchanged).
2. **Status** — stage badge plus a small inline submission line
   underneath when relevant. For `submission_status === "submitted"`
   show e.g. `Submitted 2026-05-21`. For `not_submitted` show
   `Not submitted yet`. This absorbs the old "Submission" column.
3. **Email** — `emailStatusLabel` + `lastEmailSummary` + email count +
   `Gmail checked …` subtitle (unchanged from today, but this column
   also absorbs the old "Updated" column by appending an "Updated …"
   subtle line at the bottom of the cell). The old "Latest run" column
   is dropped from the list view — users can see the latest run on the
   application detail page.
4. **Next action** — unchanged (still the primary call-to-action text).
5. **Actions** — unchanged (Open / Mark submitted / Mark interview /
   Mark rejected).

Other requirements:

- Update the `<th>` row and `data-label` attributes on each `<td>` to
  match the new five-column layout.
- Sort behavior (`attentionScore`, then `updated_at` desc) must remain
  the same.
- Filter chips (`All`, `Drafts`, `Ready`, `Submitted`, `Needs review`,
  `Interviews`, `Rejected`) must remain unchanged in behavior.
- The mobile stacked fallback (`@media (max-width: 760px)`) must still
  render each row as a card with `data-label` headings.
- Update `frontend/src/test/applicationsPage.test.tsx`:
  - Drop or rewrite assertions that target the removed "Submission",
    "Latest run", and "Updated" *columns*.
  - Add at least one assertion that confirms submission text now
    appears inside the Status cell.
  - Add at least one assertion that confirms an "Updated …" line now
    appears inside the Email cell.
  - Keep existing assertions for filter chips, attention sorting,
    Mark-submitted / Mark-interview / Mark-rejected actions, and the
    Open link.

CSS adjustments:

- Add minimal styling so the inline "submission line under stage badge"
  and "updated line at end of email cell" render as small, muted text
  consistent with the existing `.applications-cell-subtle` style.
- Keep the rest of the `.applications-table*` rules as-is.

## Allowed files

- `frontend/src/pages/ApplicationsPage.tsx`
- `frontend/src/styles.css`
- `frontend/src/test/applicationsPage.test.tsx`
- `agent_tasks/101-frontend-applications-table-column-consolidation.md`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `extension/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- any frontend page other than `ApplicationsPage.tsx`
- `frontend/src/lib/workflow.ts` (consume its helpers, do not rewrite)
- frontend tests other than `applicationsPage.test.tsx`

## Out of scope

- Adding new sort or filter capabilities.
- Changing the application detail page.
- Changing the sync-Gmail toolbar or its sub-summary.
- Backend schema or API changes.
- A column-picker / user-configurable column UI — that is a separate
  feature, not in this task's scope.

## Acceptance criteria

- The Applications table has exactly five `<th>` columns: Job, Status,
  Email, Next action, Actions (in that order).
- The Submission text is rendered inside the Status cell, beneath the
  stage badge.
- The Updated text is rendered inside the Email cell, beneath the
  Gmail-checked subtitle.
- The "Latest run" column header and cell are removed entirely from
  the table; no `<th>` and no `<td>` reference "Latest run".
- The page renders all five columns and their content without
  horizontal scroll on a 1280 px viewport.
- Mobile fallback (`@media (max-width: 760px)`) continues to render
  each row as a stacked card with `data-label` headings.
- `cd frontend && npm test -- --run` passes.
- `cd frontend && npm run build` passes.

## Verification

```
cd frontend && npm test -- --run
cd frontend && npm run build
```

## Git instructions

Commit message:

```
Consolidate Applications table to five columns
```

Do not push.
