# Task 117: Replace Captures Nav Emphasis with Bottom-Left Activity Center

## Goal

Clean up the app navigation and replace the old bottom-left “LOCAL BACKEND / pending capture” status with a useful activity center.

Current issue:
- The left nav still emphasizes `Captures`, but captures are no longer a primary workflow page.
- Bottom-left currently says something like:

```text
LOCAL BACKEND
1 pending capture
```

This is not very useful.

Desired behavior:
- Hide, demote, or clean up the Capture section if it is not actively used.
- Add a bottom-left activity/notification/status area.
- Show running work there, such as tailoring runs.
- Make it clickable.
- Clicking opens a popover/list of running/recent activities.
- Clicking an activity navigates to the relevant run/application/page.

Do not change Gmail behavior.
Do not change browser extension capture ingestion unless needed to preserve existing routes.
Do not delete capture functionality if backend still depends on it.
Do not remove access to captures entirely unless confirmed unused.
Do not break existing application/job workflows.

## Background

The app is evolving from a capture-focused prototype into a job application cockpit.

The main left nav should emphasize:

```text
Dashboard
Jobs
Applications
Runs / Activity
Settings
```

Captures may still exist as an intake mechanism from the browser extension, but it should not dominate the user-facing workflow if the user no longer works there directly.

The bottom-left status area should become a compact “Activity Center” that answers:

```text
What is currently running?
What needs my attention?
Where do I click to inspect it?
```

## Inspect

Inspect:

```text
frontend/src/components/
frontend/src/pages/
frontend/src/api/
frontend/src/routes/
backend/app/routers/
backend/app/models.py
backend/app/schemas.py
backend/tests/
```

Search:

```bash
rg "LOCAL BACKEND|pending capture|Captures|captures|capture|runs|tailoring|activity|status|sidebar|nav" frontend/src backend/app backend/tests
```

Use existing project conventions.

## Navigation Requirements

### Captures

Determine how `Captures` is currently used.

If captures are still needed for browser extension review:
- Keep the route/page available.
- Move it lower in the nav or under a secondary section.
- Rename it if clearer, e.g. `Inbox` or `Capture Inbox`.
- Do not show it as a primary workflow item unless there are pending captures.

If captures are effectively unused:
- Remove it from primary nav.
- Keep direct route working if simple.
- Ensure browser extension still submits captures without breaking.

Preferred behavior:

```text
Captures only appears prominently when there are pending captures.
Otherwise it is secondary or hidden under Activity/Inbox.
```

## Bottom-Left Activity Center

Replace the bottom-left backend/capture badge with an activity center.

### Collapsed state

Show compact text such as:

```text
Activity
1 running
```

or:

```text
Activity
All clear
```

or:

```text
Activity
2 need review
```

Use polished styling:
- no ugly oversized pill
- no text overflow
- compact status dot/icon
- aligned text
- readable but subtle

### Running state

If something is running, show:

```text
Activity
1 running
```

or the specific task if space allows:

```text
Running
Tailoring resume…
```

### Attention state

If there are pending captures, failed runs, or review-needed items:

```text
Activity
2 need attention
```

## Activity Popover

Clicking the bottom-left activity center should open a popover or small panel.

The popover should show grouped items:

```text
Running
- Tailoring resume — Example Aero Labs
  Started 3m ago
  [Open]

Needs attention
- Tailoring failed — Amazon
  Missing tailored_resume.json
  [Open]

Recent
- Gmail sync completed
- Capture imported from LinkedIn
```

Do not overbuild. First version can show:
- running runs
- failed recent runs
- pending captures if they still exist

## Activity Sources

Use available backend data.

Possible sources:
- tailoring runs
- agent/runs page data
- pending captures count
- application statuses
- Gmail sync activity if already exposed

Minimum required first version:
- running tailoring runs
- failed tailoring runs
- pending captures count if existing endpoint supports it

If no unified backend endpoint exists, create one.

Suggested endpoint:

```text
GET /api/activity
```

Suggested response:

```json
{
  "summary": {
    "running_count": 1,
    "attention_count": 2,
    "pending_capture_count": 1
  },
  "items": [
    {
      "id": "run_d6df714b",
      "type": "tailoring_run",
      "status": "running",
      "title": "Tailoring resume",
      "subtitle": "Scientific Machine Learning Engineer — Example Aero Labs",
      "started_at": "2026-05-27T15:04:08Z",
      "href": "/runs/d6df714b-86a8-4c85-ae97-0c37fceaeeb7"
    }
  ]
}
```

Use actual route conventions.

If creating a backend endpoint is too much for the first pass, build the frontend from existing run/capture endpoints. But prefer a unified `/api/activity` endpoint because the bottom-left component should not know every domain model.

## Running Items

A tailoring run should appear as running when status is one of:

```text
running
in_progress
queued
started
```

Use actual backend statuses.

Display:
- title
- company/job if available
- elapsed time if easy
- status
- link to run detail

## Failed Items

A run should appear as attention-needed when status is:

```text
failed
error
blocked
```

Show:
- title
- short error
- link to run detail

## Pending Captures

If pending captures still exist:
- show them as attention-needed
- link to capture review/inbox page

Example:

```text
Capture needs review
LinkedIn job capture pending
[Open]
```

## Sidebar UI Requirements

Add/update components such as:

```text
SidebarActivityCenter
ActivityPopover
ActivityItem
```

The bottom-left area should be visually integrated with the app sidebar.

Requirements:
- compact
- clickable
- accessible button semantics
- keyboard dismiss if popover exists
- closes on outside click or Escape if existing pattern supports it
- does not cover important nav items awkwardly

## Routing Requirements

Clicking an activity should navigate to the relevant page.

Examples:

```text
tailoring_run -> /runs/:runId or existing run detail route
pending_capture -> /captures or capture review route
application -> /applications/:id
```

Use actual route conventions.

## Polling / Refresh

The activity center should refresh periodically while app is open.

Minimum:
- fetch on mount
- refetch every 10–30 seconds
- refetch after opening popover if simple

Do not create excessive polling.

Suggested:

```text
15 second interval
```

## Visual Design Requirements

Avoid the current rough status look.

Do not use:
- giant green pills
- overflowing badge text
- PowerPoint oval/circle labels
- raw debug labels like `LOCAL BACKEND`

Use:
- small status dot
- concise text
- muted secondary label
- clean popover
- consistent spacing with the redesigned sidebar

## Tests

Add/update backend tests if `/api/activity` is added:

1. Activity endpoint returns running runs.
2. Activity endpoint returns failed runs as attention items.
3. Activity endpoint includes pending captures count if captures exist.
4. Activity endpoint includes valid hrefs.

Add/update frontend tests if infrastructure exists:

1. Sidebar activity center renders.
2. Shows `All clear` when no activity.
3. Shows running count when running activity exists.
4. Shows attention count when failed/pending items exist.
5. Clicking activity center opens popover.
6. Popover lists running item.
7. Clicking running item navigates to run detail.
8. Captures nav is hidden/demoted when no pending captures.
9. Pending capture appears in activity center when present.

## Acceptance Criteria

- Bottom-left no longer says `LOCAL BACKEND`.
- Bottom-left no longer only shows pending captures.
- Activity center shows running tailoring jobs.
- Activity center is clickable.
- Popover lists running/failed/pending items.
- Activity item links to relevant page.
- Captures are cleaned up/demoted from primary nav unless they need attention.
- Existing capture ingestion still works.
- Existing application/runs pages still work.
- Frontend builds and tests pass.
- Backend tests pass if backend changed.

## Verification

Run:

```bash
pytest
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Start backend and frontend.
2. With no running work, confirm bottom-left says something like:

```text
Activity
All clear
```

3. Start a tailoring run.
4. Confirm bottom-left changes to:

```text
Activity
1 running
```

5. Click activity center.
6. Confirm popover shows the tailoring run.
7. Click the run.
8. Confirm it opens the run detail page.
9. Create or simulate a failed run.
10. Confirm failed run appears under attention-needed.
11. Confirm capture route still works if pending captures exist.
12. Confirm `LOCAL BACKEND` text is gone.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add sidebar activity center
```

Do not push.
