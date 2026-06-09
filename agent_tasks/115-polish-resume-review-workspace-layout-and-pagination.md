# Task 115: Polish Resume Review Workspace Layout, Pagination, Sticky Review Panel, and Duplicate Sections

## Goal

Improve the Word-like resume review workspace from prototype to usable editor.

Current review workspace is directionally much better, but there are several UX/layout bugs:

1. Too much empty horizontal space.
2. Resume document preview is too narrow.
3. No visible Page 1 / Page 2 document split.
4. `WORK EXPERIENCE` appears multiple times at the bottom, likely because suggestions are being rendered as additional resume sections.
5. Right-side AI Review panel scrolls away or does not remain usable while reviewing the resume.
6. Right-side panel should stay in view and scroll internally.

Do not change Gmail.
Do not change browser extension.
Do not change backend tailoring behavior unless needed for suggestion/document rendering.
Do not remove the review workspace.
Do not revert to the old dashboard/card layout.

## Observed Problems

From the current UI:

- The centered resume preview is visually too narrow because the layout reserves too much unused side whitespace.
- The document continues as one long continuous page, so the user cannot see where page 1 ends and page 2 begins.
- Extra `WORK EXPERIENCE` blocks appear after Publications, apparently representing suggestions incorrectly rendered as resume content.
- AI Review panel should remain sticky/fixed relative to the viewport while the center document scrolls.
- AI Review panel can have its own internal scroll for long suggestions/evidence.

## Desired Layout

Use a three-column workspace, but allocate space better:

```text
sidebar/app nav      fixed
workflow rail        compact
document preview     main/wide
AI review panel      sticky right
```

Suggested dimensions:

```text
app nav: existing width
workflow rail: 180-220px max
document preview: flexible, takes most available space
AI review panel: 340-420px
```

The resume page should be wider than it is now and should approximate a real document.

Suggested CSS behavior:

```css
.review-workspace {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(720px, 900px) minmax(340px, 420px);
  gap: 24px;
  align-items: start;
}

.resume-preview-column {
  display: flex;
  justify-content: center;
}

.ai-review-panel {
  position: sticky;
  top: 24px;
  max-height: calc(100vh - 48px);
  overflow: auto;
}
```

Use actual class names/project conventions.

## Page Preview Requirements

The document preview should show page boundaries.

Implement page rendering with visible page containers:

```text
Page 1
[white document page]

Page 2
[white document page]
```

At minimum:
- split long rendered resume content into separate visual pages
- show page labels
- add margin/gap between pages
- each page has a fixed-ish document aspect ratio or minimum height
- the page break should be visually obvious

A first implementation may use estimated pagination rather than perfect Word pagination.

Acceptable first version:

```text
- group sections into page containers using simple section/bullet count estimation
- show Page 1, Page 2 labels
- keep content readable
```

Better version if easy:

```text
- measure rendered height and paginate based on page height
```

Do not block on perfect Word-compatible pagination. The goal is visual page awareness.

## Resume Width Requirements

The resume preview should not be overly narrow.

Use a realistic page width such as:

```css
.resume-page {
  width: min(850px, 100%);
  min-height: 1100px;
}
```

or another proportional value that works well in the app.

Resume text should remain document-like:
- not giant
- not tiny
- readable
- line lengths not cramped
- bullets aligned

## Duplicate Section Bug

Fix the bug where `WORK EXPERIENCE` appears multiple times near the bottom.

Important rule:

```text
Suggestions must not be rendered as additional resume sections.
```

The document preview should render the resume once.

Suggestions should appear as:
- section highlights
- badges like "Suggested edit"
- right-panel details
- inline/section-level comparison

But suggestions must not append duplicate resume sections to the document body.

Investigate components likely doing this:

```text
ResumeDocumentPreview
ResumeSectionPreview
ResumeReviewWorkspace
suggestion mapping/rendering logic
tailored_resume.json parsing
resume_suggestions.json parsing
fallback change_log parsing
```

Search:

```bash
rg "WORK EXPERIENCE|suggested edit|resume_suggestions|suggestions.map|sections.map|ResumeDocumentPreview|ResumeSectionPreview" frontend/src
```

Likely bug patterns:
- suggestions converted into fake sections and appended to resume sections
- fallback parser treating suggestions as resume content
- flattened sections array includes both resume sections and suggestion sections
- change_log entries rendered as resume sections

Expected behavior:
- render canonical resume sections only
- attach suggestions by `section_id` or heading
- show suggestion count badge on existing section
- clicking existing section updates right panel

## Sticky AI Review Panel Requirements

The AI Review panel must remain visible while scrolling through the resume.

Implement:

```css
.ai-review-panel-shell {
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 32px);
  overflow-y: auto;
}
```

If the whole app has a nested scroll container, make the sticky positioning work inside the correct scroll parent.

Do not put sticky panel inside an overflowing parent that prevents sticky behavior.

If necessary:
- make the workspace page scroll as a whole
- keep right panel sticky within that scroll
- give the panel internal scrolling for long evidence lists

## AI Review Panel Internal Scroll

Long evidence/suggestion content should scroll inside the panel.

Requirements:
- panel header remains visible if easy
- action buttons should remain visible or be easy to reach
- long evidence lists do not push the entire workspace into awkward layout
- no content overflow outside panel

## Workflow Rail Width

The workflow rail currently contributes to wasted space.

Make it compact:
- reduce width
- reduce card padding
- use smaller status text
- no huge empty card
- align with document top

It can be visually present but should not dominate the page.

## Header Bar

The top header should remain compact.

Show:
- back link
- page title
- job/company subtitle
- accepted suggestions count
- apply accepted suggestions button

Keep header height small.

## Tests

Add/update frontend tests if infrastructure exists:

1. Resume review workspace renders.
2. AI review panel has sticky class/style or expected wrapper.
3. Resume preview renders page labels.
4. Resume preview renders at least Page 1.
5. Long resume renders Page 2 or equivalent page break.
6. Suggestions are not rendered as duplicate resume sections.
7. Existing resume sections render only once.
8. Suggestion badges attach to existing sections.
9. Clicking a section changes selected suggestion.
10. Long AI review content remains inside scrollable panel.

Add a regression test using sample data where:
- canonical resume has one `WORK EXPERIENCE` section
- suggestions include multiple work experience edits
- rendered preview still contains only one visible `WORK EXPERIENCE` section heading

## Acceptance Criteria

- Resume page is wider and uses available space better.
- There is less empty horizontal whitespace.
- Page 1 / Page 2 boundaries are visible.
- `WORK EXPERIENCE` is not duplicated as separate appended sections.
- Suggestions attach to existing resume sections instead of becoming document content.
- AI Review panel remains visible while scrolling the resume.
- AI Review panel scrolls internally when content is long.
- Layout looks substantially more like a document editor.
- Frontend builds and tests pass.

## Verification

Run:

```bash
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Start frontend/backend.
2. Open the resume review workspace.
3. Confirm the resume document is wider and easier to read.
4. Confirm page labels or page boundaries are visible.
5. Scroll down through the resume.
6. Confirm the AI Review panel remains visible.
7. Confirm the AI Review panel scrolls internally if content is long.
8. Confirm `WORK EXPERIENCE` appears only once as a resume section heading unless the actual resume intentionally has multiple differently named work sections.
9. Confirm suggested edits appear as badges/highlights attached to existing sections.
10. Confirm suggestions are not appended after Publications as fake resume sections.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Polish resume review workspace layout
```

Do not push.
