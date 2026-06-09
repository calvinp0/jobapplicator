# Task 116: Tighten Resume Review Layout, Add Flow Pagination, and Fix Sticky AI Review Panel

## Goal

Further polish the resume review workspace so it behaves more like a real document editor.

The current workspace is much better, but still has several major issues:

1. There is still too much empty horizontal space.
2. The resume document preview is still narrower than it should be.
3. Pagination is too coarse: sections such as WORK EXPERIENCE should begin on page 1 and continue naturally onto page 2, like a real Word document.
4. The AI Review column is still not staying visible while the overall page scrolls.
5. The AI Review column should remain sticky relative to the viewport/page scroll, while also allowing internal scroll for long content.

Do not revert the review workspace.
Do not reintroduce the old card/dashboard-style review UI.
Do not change Gmail behavior.
Do not change browser extension behavior.

## Background

The current implementation already:
- renders visual pages
- shows a much better document-like preview
- shows an AI review panel
- shows workflow steps

However, remaining UX issues are harming the “real document editor” feel.

### Current problems

#### 1. Too much empty space
The layout still leaves excessive whitespace around the document preview, making the resume feel too narrow.

#### 2. Section-level pagination instead of flow pagination
Right now pagination appears to be section-grouped or block-grouped. This causes:
- Page 1 to end with a large blank area
- WORK EXPERIENCE to start only on page 2
- Pages to feel artificial

What should happen instead:
- Page 1 should fill more naturally
- WORK EXPERIENCE may begin near the end of page 1
- The remaining bullets/entries should overflow onto page 2

That is how a real Word/Docs resume behaves.

#### 3. Sticky AI Review panel still not behaving correctly
The right panel still does not follow the user while the whole review page scrolls.
It should:
- stay visible while the document scrolls
- remain pinned near the top of the viewport
- have its own internal scroll if content is long

## Desired Behavior

## A. Tighter Workspace Layout

Reduce wasted space and allow the document preview to use more of the available width.

Preferred direction:
- compact workflow rail
- wider center document column
- right panel still readable, but not overly wide
- reduced outer horizontal padding

Suggested layout target:

```css
.review-workspace {
  display: grid;
  grid-template-columns:
    minmax(150px, 190px)
    minmax(820px, 980px)
    minmax(320px, 380px);
  gap: 20px;
  align-items: start;
}
```

Use actual project conventions and adjust as needed, but the intent is:

- smaller workflow column
- larger document area
- slightly tighter right panel
- less dead space

Also reduce any excessive container max-width or centering wrappers that unnecessarily narrow the whole workspace.

## B. Flow Pagination Instead of Section Pagination

Implement a more document-like pagination strategy.

Important requirement:

```text
Do not force each resume section to stay entirely on one page.
```

Instead:
- sections should be allowed to split across pages
- entries may continue onto the next page
- bullet lists may continue onto the next page
- page 1 should fill as much as possible before page 2 begins

### Expected example
If the page still has space after SKILLS, then WORK EXPERIENCE should begin on page 1.
If the full work content does not fit, it should continue onto page 2.

### First implementation guidance
A perfect Word-style layout engine is not required.
But the current “whole chunk per page” behavior should be replaced with a more granular flow model.

Preferred strategies:
1. Render the resume into smaller flow blocks:
   - header block
   - section heading
   - paragraph
   - skills row/group
   - experience entry heading
   - bullet item
   - education entry
   - publication bullet

2. Paginate at the block level, not just section level.

3. Allow overflow by moving the next block to the next page when the page height estimate is reached.

Pseudo approach:

```text
resume → flattened render blocks → accumulate into page until max page height → overflow remaining blocks to next page
```

This is much better than:
```text
one whole section = one page chunk
```

### Section heading behavior
When a section continues across pages:
- keep the section heading only once if possible
- optional: repeat a subtle continuation heading if needed, but do not duplicate the whole section unnaturally

Do not create fake duplicate section content.

## C. Page Rendering Requirements

Pages should continue to look like separate pages:

- Page 1 / Page 2 / Page 3 labels
- white paper cards
- clear vertical spacing between pages
- consistent page width and min height
- realistic document feel

But the content placement inside pages should feel more natural and dense.

## D. Sticky AI Review Panel

Fix the AI Review column so it stays visible while the main page scrolls.

Desired behavior:
- the whole review page scrolls normally
- the AI Review panel remains sticky in the viewport
- the AI Review panel does not disappear when the user scrolls down the resume
- the AI Review panel can scroll internally if its own content is long

Likely issue:
- sticky is being applied inside the wrong scroll container
- a parent has `overflow` set in a way that breaks `position: sticky`

Investigate:
- page-level scroll container
- workspace container overflow
- panel wrapper overflow
- sticky `top` offset

Preferred behavior:

```css
.ai-review-column {
  position: sticky;
  top: 16px;
  align-self: start;
}

.ai-review-panel {
  max-height: calc(100vh - 32px);
  overflow-y: auto;
}
```

Use actual component structure, but preserve this behavior.

Important:
- sticky should apply to the column/wrapper
- internal scroll should apply to the panel body
- do not wrap the sticky element in a parent that clips it

## E. Workflow Rail Compaction

The workflow rail can still be compacted slightly.

Requirements:
- narrower width
- reduced padding
- smaller vertical gaps
- clearer status styling
- do not let it consume space needed by the document preview

## F. Keep the Centerpiece as the Document

The document preview should remain the visual focus of the page.

It should feel like:
- the main object the user is reviewing
- not a small centered card floating in a large sea of whitespace

## Implementation Notes

Inspect likely components:

```text
frontend/src/pages/ResumeReviewPage.tsx
frontend/src/components/resume-review/**
frontend/src/components/ResumeDocumentPreview*
frontend/src/components/ResumePage*
frontend/src/components/AIReviewPanel*
frontend/src/styles.css
frontend/src/**/*.css
```

Search:

```bash
rg "sticky|ResumeReview|ResumeDocument|page 1|PAGE 1|workflow|AI review|overflow|position: sticky" frontend/src
```

For pagination, look for current page grouping logic and replace any section-level page grouping with block-level flow pagination.

## Tests

Add/update frontend tests if infrastructure exists:

1. Review workspace renders with three columns.
2. Document preview renders multiple pages.
3. Flow pagination allows a section to continue onto a later page.
4. WORK EXPERIENCE does not have to start only on page 2 if page 1 has room.
5. Page 1 contains content after SKILLS when resume data is long enough.
6. Sticky AI review wrapper has expected class/style.
7. AI review panel has internal scroll behavior.
8. Layout uses widened center column / reduced outer whitespace assumptions where testable.
9. No duplicated fake resume content is introduced by pagination.

If DOM layout is hard to test exactly, at least test the flow paginator logic with block-level input and page splits.

## Acceptance Criteria

- The review workspace uses available width better and has less empty horizontal space.
- The document preview is visibly wider and more central.
- Pagination is more natural and block-level, not coarse section-level.
- WORK EXPERIENCE can begin on page 1 and continue onto page 2.
- Pages remain visually separated and labeled.
- The AI Review column remains visible while scrolling the resume.
- The AI Review panel scrolls internally when content is long.
- Frontend builds and tests pass.

## Verification

Run:

```bash
cd frontend && npm run build
cd frontend && npm test -- --run
```

Manual verification:

1. Start the app.
2. Open the Resume Review workspace.
3. Confirm the center document is wider and there is less dead horizontal space.
4. Confirm page 1 fills more naturally before page 2 begins.
5. Confirm WORK EXPERIENCE begins on page 1 if there is room.
6. Confirm remaining work content overflows to page 2 naturally.
7. Scroll the whole page downward.
8. Confirm the AI Review panel remains visible.
9. Confirm the AI Review panel can scroll internally if its content is long.
10. Confirm the page feels closer to a real Word/Docs document flow.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Tighten review layout and add flow pagination
```

Do not push.
