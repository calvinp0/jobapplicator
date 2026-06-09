# Task 120: Redesign Applications Table Actions and Status UI

## Goal

Polish the Applications page table so it feels like a professional application tracker.

Current problems:
- Pipeline/status badges use awkward pill/oval shapes.
- Some status text wraps badly inside green shapes.
- Next Action column has too many buttons.
- Buttons are not consistently aligned across rows.
- Rows feel visually noisy.
- User cannot immediately tell the one next action for each application.

Do not change Gmail behavior.
Do not change browser extension behavior.
Do not remove application status functionality.
Do not remove existing routes.
Do not change backend behavior unless needed to expose cleaner status/next-action data.

## Current UI Problems

The Applications page currently has columns like:

```text
Application | Pipeline | Email | Activity | Next Action
```

This is good, but the row UI is cluttered.

Examples of current Next Action clutter:

```text
Open
Mark submitted
Mark interview
Mark rejected
```

This creates:
- inconsistent row heights
- inconsistent button alignment
- too much decision burden
- poor scanability

The Pipeline column also uses visual badges that look like PowerPoint shapes rather than polished product UI.

## Product Direction

The Applications table should answer:

```text
What application is this?
Where is it in the pipeline?
What email evidence exists?
What happened recently?
What is the next best action?
```

Each row should have:
- compact application metadata
- compact pipeline status
- compact email status
- compact recent activity
- one primary next action
- secondary actions in a menu

## Desired Row Layout

Suggested structure:

```text
Application                       Pipeline            Email                    Activity                 Next
Scientific Machine Learning       ● Draft             Not watching             Updated 5/24/2026         Ready to submit
Example Aero Labs                                      Gmail checked 14d ago    Latest: imported          [Continue] ⋯
LinkedIn
```

For confirmation received:

```text
AI and Machine Learning Engineer  ● Confirmation      Confirmation received    Updated 5/26/2026         Waiting for response
InfinityLabs R&D                    Submitted 5/25     From Infinity Labs       Gmail checked 14d ago      [Open] ⋯
```

## Pipeline Status Requirements

Replace large pill/oval badges with compact status indicators.

Preferred display:

```text
● Draft
● Submitted
● Confirmation received
● Interview
● Rejected
● Needs review
```

Rules:
- Use a small dot + label or compact rectangular badge.
- Do not use large rounded pills.
- Do not let status text wrap awkwardly.
- Keep the label one line where possible.
- If text is long, use a shorter label plus detail underneath.

Example:

```text
● Confirmation
Submitted 5/25/2026
```

instead of:

```text
[ Confirmation received ]  ← huge green oval
```

## Next Action Requirements

Each row should show exactly one primary action button.

Examples:

```text
[Continue]
[Review draft]
[View progress]
[Open]
[Review failure]
[Check Gmail]
```

Use a deterministic mapping based on application status.

Suggested mapping:

```text
draft_ready_to_review:
  label: Review draft
  href/action: open resume review

approved_ready_to_send:
  label: Continue
  href/action: continue application

submitted_waiting:
  label: Open
  href/action: open application detail

confirmation_received:
  label: Open
  href/action: open application detail

needs_review:
  label: Review
  href/action: open application detail or email evidence

tailoring_running:
  label: View progress
  href/action: latest run detail

tailoring_failed:
  label: Review failure
  href/action: latest run detail

no_resume:
  label: Generate draft
  href/action: start tailoring or open application detail
```

Use actual statuses from the project.

The Next Action column should show:

```text
Ready to submit
[Continue] ⋯
```

or:

```text
Waiting for response
[Open] ⋯
```

## Secondary Actions Menu

Move secondary actions into a compact menu.

Use `⋯`, `More`, or existing menu component.

Menu items may include:

```text
Open application
Open resume
Open draft
View latest run
Mark submitted
Mark interview
Mark rejected
Sync Gmail
Archive
```

Only show actions that make sense for the row.

Do not show all actions as buttons in the row.

If a menu component does not exist, implement a simple accessible menu/dropdown.

Requirements:
- opens on click
- closes on outside click or Escape if project patterns exist
- keyboard accessible enough for first implementation
- does not break table layout
- does not expand row height awkwardly

## Alignment Requirements

The Next Action column must align cleanly across rows.

Requirements:
- consistent button width or consistent alignment
- no wrapping action buttons into multiple lines
- no uneven vertical button stacks
- row height should be mostly consistent
- action block should align to the top or center consistently

Suggested CSS:

```css
.application-next-action {
  display: grid;
  gap: 8px;
  align-content: start;
}

.application-row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
```

## Table Visual Requirements

Keep the table direction, but polish it:

- reduce badge visual weight
- improve row spacing
- align columns consistently
- keep metadata muted
- use clear typography hierarchy
- make rows scannable
- avoid huge blank spaces
- avoid PowerPoint-style shapes

## Tabs / Filters

The top filters are okay directionally, but should also avoid oversized pill styling.

Requirements:
- keep filter tabs compact
- count bubbles should not look like random pills
- active state should be clear but subtle
- text should not jump/wrap

## Email Column

Keep email evidence useful but compact.

Examples:

```text
Not watching yet
Gmail checked: 14d ago
```

or:

```text
Confirmation received
From Infinity Labs R&D
```

Do not expand row height with too much email content.

## Activity Column

Keep activity compact:

```text
Updated 5/26/2026
Latest run: imported
```

For failed/running latest run:

```text
Running · 4m elapsed
```

or:

```text
Failed · missing tailored_resume.json
```

## Tests

Add/update frontend tests if infrastructure exists:

1. Applications page renders table.
2. Pipeline status renders compact indicator.
3. Large pill status class is no longer used for pipeline if testable.
4. Each row has exactly one primary action button in the Next Action column.
5. Secondary actions are accessible from a menu.
6. Draft row primary action is Review draft or Open depending current state.
7. Ready-to-submit row primary action is Continue.
8. Submitted/confirmation row primary action is Open.
9. Mark submitted/interview/rejected actions appear in secondary menu.
10. Next Action column does not render multiple stacked buttons.

## Acceptance Criteria

- Applications table no longer uses ugly large pipeline pills.
- Next Action column no longer shows many competing buttons.
- Each row has one clear primary action.
- Secondary actions are available in a compact menu.
- Row actions are aligned consistently.
- Table feels more polished and scannable.
- Existing application actions still work.
- Frontend builds and tests pass.

## Verification

Run:

```bash
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Start the app.
2. Open Applications page.
3. Confirm pipeline/status indicators are compact and professional.
4. Confirm no large green oval status shapes remain.
5. Confirm each row has one primary next-action button.
6. Confirm Mark submitted / Mark interview / Mark rejected are in a secondary menu.
7. Confirm action alignment is consistent across rows.
8. Confirm filter tabs still work.
9. Confirm Sync Gmail still works.
10. Confirm opening an application still works.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Redesign applications table actions
```

Do not push.

