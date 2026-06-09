# Task 119: Redesign Dashboard Active Jobs UI

## Goal

Redesign the Dashboard “Active Jobs” section so it feels like a polished job application cockpit, not a rough card prototype.

Current problems:
- Status pills look like awkward PowerPoint shapes.
- Status text wraps badly inside green ovals.
- Too many equal-weight buttons: Review job, Open draft, Open resume, Continue application, View run.
- User cannot easily tell the next best action.
- Cards have weak hierarchy and poor spacing.
- Dashboard does not feel intuitive.

Do not change Gmail behavior.
Do not change browser extension behavior.
Do not remove application/run functionality.
Do not break existing application routes.
Do not replace the whole dashboard with unrelated UI.
Focus on Dashboard Active Jobs and related shared card/status components.

## Product Direction

The dashboard should answer:

```text
What applications are active?
What is the status of each one?
What should I do next?
What changed recently?
```

Each job/application card should have:
- clear job title
- company/location metadata
- compact status indicator
- one obvious primary next action
- secondary actions hidden behind a menu or shown as subtle text links
- recent activity/run information if available

It should not have:
- giant green oval pills
- multiple competing primary buttons
- button clutter
- wrapped status labels
- chunky inconsistent cards

## Inspect

Inspect:

```text
frontend/src/pages/Dashboard*
frontend/src/components/
frontend/src/api/
frontend/src/routes/
frontend/src/styles*
```

Search:

```bash
rg "Active Jobs|Review job|Open draft|Open resume|Continue application|View run|Draft ready|Approved|ready to send|status|dashboard" frontend/src
```

Use existing project conventions.

## Desired Card Layout

Replace the current card layout with a cleaner application card.

Suggested card structure:

```text
┌──────────────────────────────────────────────┐
│ Scientific Machine Learning Engineer          │
│ Example Aero Labs · Remote                    │
│                                               │
│ ● Approved                                    │
│ Next: Continue application                    │
│                                               │
│ [Continue application]                  ⋯     │
│                                               │
│ Last run: 2h ago · Resume ready               │
└──────────────────────────────────────────────┘
```

For draft states:

```text
┌──────────────────────────────────────────────┐
│ Staff Software Engineer                       │
│ Appfigures · Israel                           │
│                                               │
│ ● Draft ready                                 │
│ Next: Review resume changes                   │
│                                               │
│ [Review draft]                          ⋯     │
│                                               │
│ Last run failed? show small warning if needed │
└──────────────────────────────────────────────┘
```

## Status Display Requirements

Remove the large green pill/oval status design.

Use compact status treatment:

Preferred:

```text
● Draft ready
● Approved
● Running
● Failed
● Needs review
```

The dot can be colored, but:
- keep it small
- text must not wrap awkwardly
- no giant pill background
- no oversized rounded capsule
- no status occupying a huge chunk of the card

If a badge is used:
- compact height
- max one line
- no wrapping
- subtle background
- professional spacing

## Next Action Logic

Each card should choose one primary action based on application/run state.

Suggested mapping:

```text
tailoring_running:
  primary: View progress

draft_ready_to_review:
  primary: Review draft

approved_ready_to_send:
  primary: Continue application

failed:
  primary: View failure

no_draft:
  primary: Generate draft or Review job

submitted:
  primary: View application

email_received / needs_followup:
  primary: View emails or Open application
```

Use actual status values in the app.

The card should show:

```text
Next: Review draft
```

or:

```text
Next: Continue application
```

This makes the user flow clear.

## Secondary Actions

Move secondary actions out of the main button row.

Current clutter:

```text
Review job
Open draft
Open resume
Continue application
View run
```

Replace with:
- one primary button
- optional overflow menu `⋯`
- or subtle inline links

Suggested overflow menu items:
- Review job
- Open resume
- Open draft
- View latest run
- View application
- Archive / hide if supported

If an overflow menu component does not exist, use a compact “More” button.

Do not show five buttons on every card.

## Dashboard Layout Requirements

Improve the overall Active Jobs layout:

- Reduce card height.
- Align cards consistently.
- Use a cleaner grid.
- Avoid huge blank regions.
- Make cards visually scan-friendly.
- Avoid all-caps labels unless subtle section headers.
- Use consistent spacing and font sizes.
- Cards should look like product UI, not PowerPoint slides.

Suggested:
- use 3-column grid on wide screens if cards fit
- 2-column grid on medium screens
- 1-column on small screens
- keep content aligned

## Recent Activity Line

If available, show one compact line at the bottom:

```text
Latest: Tailoring completed 12m ago
```

or:

```text
Latest: Resume approved · Gmail checked
```

or:

```text
Latest: Tailoring failed — missing tailored_resume.json
```

This should be muted and compact.

Do not show huge logs inside dashboard cards.

## Running State

If a tailoring run is active, card should show:

```text
● Running
Next: View progress
[View progress]
```

Optionally show:

```text
Tailoring resume · 3m elapsed
```

## Failed State

If latest run failed, card should show:

```text
● Failed
Next: Review failure
[View failure]
```

And a concise error:

```text
Missing tailored_resume.json
```

Do not bury failures behind generic “View run”.

## Empty State

If no active jobs exist, show a polished empty state:

```text
No active applications yet.
Capture a job or add one manually to start tailoring.
[Add job] [Open captures]
```

Use actual route conventions.

## Component Structure

Create/update reusable components if useful:

```text
DashboardActiveJobs
ApplicationCard
ApplicationStatus
ApplicationNextAction
ApplicationActionsMenu
```

Keep styling local or in shared design system according to current project patterns.

## Visual Design Rules

Do not use:
- oversized pills
- green oval capsules with wrapped text
- random button clusters
- unaligned button rows
- excessive card padding
- giant status blobs

Use:
- small status dot + label
- one primary action
- one secondary menu
- clean typography
- compact metadata
- consistent spacing
- subtle borders/shadows

## Tests

Add/update frontend tests if infrastructure exists:

1. Dashboard renders active jobs.
2. Status is rendered as compact status indicator, not large pill if testable.
3. Each active job card has only one primary action button.
4. Secondary actions are in a menu or compact secondary area.
5. Draft-ready application primary action is Review draft.
6. Approved application primary action is Continue application.
7. Running application primary action is View progress.
8. Failed application primary action is View failure.
9. Latest run/failure summary appears when data exists.
10. Empty state appears when no active jobs exist.

## Acceptance Criteria

- Active Jobs no longer uses ugly large status pills.
- Cards have one clear primary next action.
- Secondary actions are no longer cluttered as many equal buttons.
- Dashboard is easier to scan.
- User can immediately understand what to do next for each job.
- Running/failed states are clear.
- Existing navigation still works.
- Frontend builds and tests pass.

## Verification

Run:

```bash
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Start app.
2. Open Dashboard.
3. Confirm Active Jobs cards look polished and compact.
4. Confirm status labels are small and professional.
5. Confirm no green oval/pill status wraps text.
6. Confirm each card has one primary action.
7. Confirm secondary actions are accessible but not cluttering the card.
8. Confirm approved jobs say Continue application as the primary action.
9. Confirm draft-ready jobs say Review draft as the primary action.
10. Confirm running/failed states are clear if present.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Redesign dashboard active jobs
```

Do not push.
