# 100 — Let the Applications table use the full content width

## Goal

The Applications page renders a table inside the standard `.content-inner`
container, which is clamped to `max-width: 1080px`. With eight columns
(Job, Status, Submission, Email, Latest run, Updated, Next action,
Actions) and `white-space: nowrap` cells, the table overflows horizontally
inside that container, forcing the user to scroll right-to-left to see
columns. This task widens the available canvas so the Applications page
can use the full content area, and removes the redundant inline cell
prefixes (`Submission:`, `Email:`, `Updated:`, `Next:`) that duplicate the
column headers and inflate each cell's intrinsic width.

The aim is purely visual fit; no columns are removed or merged here.
Column consolidation is handled in task `101-frontend-applications-table-column-consolidation`.

## Background

Read first:

- `docs/product_requirements.md` — Application Tracking section.
- `docs/architecture.md` — Frontend component overview.
- `agent_tasks/095-redesign-applications-page-as-table.md` — original
  table design rationale.
- `frontend/src/pages/ApplicationsPage.tsx` — current table markup.
- `frontend/src/styles.css` — `.content-inner` clamp at ~line 226, and the
  `.applications-table*` block starting at ~line 1771.
- `frontend/src/layout/Layout.tsx` — `.content` / `.content-inner` shell.
- `frontend/src/test/applicationsPage.test.tsx` — existing tests for this
  page; keep them green.

## Scope

- Allow the Applications page (and only the Applications page) to use a
  wider container than the default 1080px clamp. Pick whichever of these
  is least invasive:
  - add a page-specific class (e.g. `content-inner-wide`) on the
    Applications route's outermost element, OR
  - widen `.applications-page` itself with a negative margin / wider
    `max-width` override that breaks out of `.content-inner`.
- Either way, do not change the global `.content-inner` width — other
  pages (Dashboard, Settings, Jobs, etc.) must keep their existing width.
- In `ApplicationsPage.tsx`, remove the redundant inline prefixes inside
  table cells: `Submission: …`, `Email: …`, `Updated: …`, `Next: …`.
  The column headers already convey what each cell means; the prefixes
  inflate cell width and force `white-space: nowrap` overflow.
  The mobile fallback at `@media (max-width: 760px)` uses
  `td::before { content: attr(data-label) ... }` — the `data-label`
  attributes already provide the label for the stacked layout, so the
  inline text prefixes are pure duplication.
- Reduce `.applications-table td` horizontal padding modestly
  (e.g. from `12px 14px` to `8px 10px`) so the table fits naturally
  on a 1280–1440 px laptop screen with no horizontal scroll.
- Update `frontend/src/test/applicationsPage.test.tsx` for any assertions
  that match the removed inline prefix strings (e.g. `Submission:`,
  `Next:`). Test intent (what the row shows) must not weaken — assertions
  should target the underlying values via `data-testid` or the `data-label`
  attribute, not the removed inline label.

## Allowed files

- `frontend/src/pages/ApplicationsPage.tsx`
- `frontend/src/styles.css`
- `frontend/src/layout/Layout.tsx`
- `frontend/src/test/applicationsPage.test.tsx`
- `agent_tasks/100-frontend-applications-table-full-width.md`
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
- frontend tests other than `applicationsPage.test.tsx`

## Out of scope

- Removing or merging columns. That happens in task `101-...`.
- Reordering columns.
- Visual redesign of badges, buttons, or row hover styles.
- Changing the filter chip row above the table.
- Backend changes or schema changes.
- Mobile-layout redesign — keep the existing `@media (max-width: 760px)`
  stacked card fallback working.

## Acceptance criteria

- On a standard 1366×768 or 1440×900 laptop viewport, the Applications
  table renders all eight column headers and their cell content
  without triggering horizontal scroll on `.applications-table-wrapper`.
- The cells no longer contain the inline prefixes `Submission:`,
  `Email:`, `Updated:`, or `Next:` (the values are shown without the
  duplicated label).
- The page-specific wider container does not affect the width of the
  Dashboard, Settings, Jobs, Captures, Runs, or Prompts pages.
- The mobile fallback (`@media (max-width: 760px)`) still renders each
  row as a stacked card with the `data-label` headings shown via
  `td::before`.
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
Let Applications table use full content width and remove redundant cell prefixes
```

Do not push.
