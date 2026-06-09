# Task 114: Build Word-Like Resume Review Workspace

## Goal

Replace the current rough resume tailoring/review UI with a professional Word-like resume review workspace.

The current UI feels like an internal prototype:
- poor text and line alignment
- oversized text
- awkward pill badges
- inconsistent spacing
- weak user flow
- no real document preview
- no side-by-side review/track-changes style interaction

Build a polished interface where the user can review a tailored resume like a document editor:

```text
left: workflow navigation
center: live resume document preview
right: AI change review panel
```

Do not change Gmail behavior.
Do not change browser extension behavior.
Do not change backend tailoring logic unless needed to display existing artifacts.
Do not remove existing pages unless replacing them cleanly.
Do not make this a generic dashboard redesign.
This task is specifically about the resume tailoring/review workspace.

## Product Target

The review page should feel closer to:
- Microsoft Word review mode
- Google Docs document preview
- Rezi-style resume section suggestions
- Linear/Notion-level spacing and typography

It should not look like:
- Bootstrap admin panel
- oversized cards
- random colored pill dashboard
- PowerPoint shapes
- raw JSON/debug output
- a toy school project

## Required Layout

Implement a three-panel workspace.

### Left Panel: Workflow

A narrow left rail showing the user’s progress:

```text
1. Job
2. Evidence
3. Tailoring
4. Review
5. Export
```

Each step should have:
- clear label
- status: complete / active / blocked / failed
- subtle icon or number
- no oversized badges

The active step should be visually clear.

### Center Panel: Resume Document Preview

The center of the page must render the resume as a document page.

Requirements:
- white page on neutral background
- realistic page width
- A4/Letter-like aspect ratio
- subtle border/shadow
- proper padding/margins
- resume font size around 10–12px equivalent
- centered header
- section headings aligned cleanly
- bullets aligned properly
- dates aligned consistently where possible
- page should not look like random web cards

The preview may be rendered from:
- `tailored_resume.json`
- `tailored_resume.md`
- current resume state
- existing artifact content

Use whichever is available now, but structure the component so it can later use deterministic resume JSON.

Suggested components:

```text
ResumeReviewWorkspace
ResumeDocumentPreview
ResumePage
ResumeHeaderPreview
ResumeSectionPreview
ResumeExperienceEntryPreview
ResumeBulletList
```

### Right Panel: AI Review / Track Changes

The right panel should show the AI suggestions/change details for the currently selected section.

For each selected section, show:

```text
Section: Professional Summary

Previous
<old text>

Suggested
<new text>

Why this change
<short reason>

Evidence
- source name / short quote

ATS keywords
- keyword
- keyword

Risk
low / medium / high

Actions
[Accept] [Ask to revise] [Reject]
```

Use professional styling:
- no huge colored pills
- no text overflowing badges
- compact metadata rows
- clear buttons
- aligned labels
- readable hierarchy

If no suggestions exist yet, show a useful empty state:

```text
No AI suggestions available for this section yet.
Run tailoring or open an existing tailored draft.
```

### Track-Changes Behavior

At minimum, show previous vs suggested text clearly.

Preferred:
- highlight changed text in the document preview
- clicking a highlighted section opens its suggestion in the right panel
- accepted changes update the preview state
- rejected changes restore previous text
- revised changes show pending revision status

If full inline diff is too much, implement section-level diff first.

## Visual Design Requirements

Create or update a real design system.

Requirements:
- consistent spacing scale
- consistent font sizes
- consistent button styles
- consistent panel borders
- consistent page background
- no giant badges
- no pill text overflow
- no random green oval/circle labels
- no oversized body text
- no uncontrolled card widths
- no misaligned table/header text

Suggested tokens:

```text
--space-1: 4px
--space-2: 8px
--space-3: 12px
--space-4: 16px
--space-6: 24px
--space-8: 32px

--font-xs: 12px
--font-sm: 13px
--font-md: 14px
--font-lg: 16px
--font-xl: 20px
```

Resume preview font should be smaller and document-like, not dashboard-like.

## Interaction Requirements

The user should be able to flow through the screen intuitively:

1. See which job/resume is being reviewed.
2. See tailoring status.
3. See the resume document in the center.
4. Click a resume section.
5. See AI suggestion on the right.
6. Accept/reject/request revision.
7. See the document preview update.
8. Export final DOCX/PDF when ready.

## Data Requirements

Use available artifacts where possible:

```text
tailored_resume.json
resume_suggestions.json
tailored_resume.md
change_log.md
claim_audit.md
ats_audit.md
recruiter_review.md
```

If `resume_suggestions.json` does not exist yet, derive a temporary review panel from:
- change_log.md
- claim_audit.md
- ats_audit.md
- tailored_resume.md

Do not block the UI on perfect backend support.

## Routing Requirements

Add or update a route such as:

```text
/applications/:applicationId/review
/runs/:runId/review
/resume-versions/:resumeVersionId/review
```

Use existing routing conventions.

The review workspace should be easy to access from:
- application detail page
- tailoring run result page
- resume version page if one exists

## Empty/Error States

Must include polished states for:

```text
No tailored resume yet
Tailoring running
Tailoring failed
Suggestions missing
Artifacts missing
DOCX not rendered yet
```

No raw stack traces or ugly debug boxes in the main UI.

## Responsiveness

Desktop-first is acceptable.

Minimum:
- works well at 1440px width
- works acceptably at 1280px
- at narrower widths, right panel may collapse below or into a drawer

## Tests

Add/update frontend tests where infrastructure exists:

1. Review workspace renders.
2. Resume document preview renders.
3. Workflow rail renders.
4. Right AI review panel renders.
5. Empty state appears when no suggestions exist.
6. Suggestion card shows previous text.
7. Suggestion card shows suggested text.
8. Accept button updates suggestion status or calls API.
9. Reject button updates suggestion status or calls API.
10. Long status text does not overflow pill/badge containers.

Add backend tests only if new endpoints are added.

## Acceptance Criteria

- The review page visually looks like a professional document editing workspace.
- There is a live resume document preview in the center.
- There is an AI review/change panel on the right.
- Previous and suggested text are visible for a selected section.
- User can accept/reject/request revision at section/suggestion level, even if first implementation is local state or calls existing endpoints.
- Badges/pills do not overflow.
- Text alignment and spacing are consistent.
- The workflow through tailoring review is intuitive.
- Existing app still builds.
- Tests pass.

## Verification

Run:

```bash
cd frontend && npm run build
cd frontend && npm test -- --run
```

If backend changed:

```bash
pytest
```

Manual verification:

1. Start backend and frontend.
2. Open an application with a tailoring run.
3. Open the review workspace.
4. Confirm there is:
   - left workflow rail
   - center Word-like resume page
   - right AI review panel
5. Confirm typography is not oversized.
6. Confirm badges/pills do not overflow.
7. Confirm clicking a section opens corresponding suggestion.
8. Confirm previous/suggested text can be compared.
9. Confirm Accept/Reject controls are visible and aligned.
10. Confirm the page looks substantially different from the old dashboard/card UI.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Build Word-like resume review workspace
```

Do not push.
