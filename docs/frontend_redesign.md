# Frontend redesign (task 106)

Notes on the bold visual redesign that landed in task 106. Task 103 added
the reusable shell components (PageHeader, SectionCard, SettingsGroup,
EmptyState, StatusBadge); this pass turned those into a noticeably
different UI rather than a thin wrapper around the previous layout.

## What changed visually

- **Sidebar**: darker (`#0b0d18`) navigation rail with a soft accent
  gradient overlay, a square gradient brand mark, larger title, and a
  bottom-left activity center (task 117 — see below). Active routes are
  highlighted with an accent left-bar and a tinted background instead of
  a flat solid fill.
- **Grouped nav**: the rail is split into `Track` (Dashboard, Jobs,
  Applications), `Create` (Runs), and `Configure` (Prompts, Settings).
  Only routes that actually exist in `App.tsx` are linked. Captures are
  no longer a primary surface (task 117): the route stays live for the
  browser-extension intake, but the nav link is demoted to an `Inbox`
  group that only appears when there are pending captures to review.
- **Activity center** (task 117): the old "Local backend / N pending
  captures" footer is replaced by a compact, clickable activity center.
  Collapsed it shows a status dot plus `All clear` / `N running` /
  `N need attention`; clicking opens a grouped popover (Running / Needs
  attention / Recent) whose items link straight to the relevant run or
  capture. It polls `GET /activity` every 15s. The endpoint is a
  domain-agnostic projection so the component never imports run/capture
  models.
- **Page headers**: heavier 26 px display-style headings with a thin
  bottom border, so each page reads as a real surface and not a stack
  of cards floating on the body.
- **Buttons**: introduced a single button hierarchy via the new
  `Button` component with four variants (`primary` / `secondary` /
  `ghost` / `danger`) and an `sm` size. Legacy `.button` rules pick up
  the same polish so older call-sites benefit without an audit.
- **Applications table**: redesigned columns are now
  `Application` / `Pipeline` / `Email` / `Activity` / `Next action`, a
  shared `Toolbar` houses the filter chips plus the `Sync Gmail`
  primary action, and row actions sit inline at the foot of the
  Next-action cell. Hover background is a subtle blue tint.
- **Settings**: full settings hub with grouped panels — Gmail
  integration, Document tooling, Claude / LLM, Browser extension,
  Prompt harnesses, Danger zone — each rendered through `SectionCard`
  with rounded corners and a status pill style available for future
  panels.
- **Job Detail**: now a two-column workspace. The 5-step wizard lives
  in the main column; the right aside is a sticky `Tailoring setup`
  summary that surfaces the selected resume, evidence sources count,
  tailoring method, and the latest-run link. A `Workspace summary`
  card underneath gives at-a-glance counts for drafts / runs /
  applications.
- **Runs / Captures / Jobs**: standardised on `PageHeader` +
  `EmptyState` + `StatusBadge`, so the secondary pages match the
  redesigned shell instead of clashing with bare `<h2>`s.

## Design principles

- **Single hierarchy**: every action funnels through `Button` /
  `ButtonLink` so a "primary" anywhere in the app reads the same way.
- **Dense but readable**: the table reduces padding without sacrificing
  the readable 14 px body size; sub-text drops to 12 px in a muted
  colour rather than shrinking the primary text.
- **Surfaces over outlines**: cards lean on `--card-shadow` for
  separation; borders are intentionally light (`--border-soft`).
- **Accent restraint**: the brand accent (`#4f6bff`) is reserved for
  primary calls-to-action, the active nav indicator, focus rings, and
  the tailoring-setup highlight. Status uses semantic colours.

## Key components

- `frontend/src/components/ui/Button.tsx` — primary/secondary/ghost/
  danger, with a small `sm` variant and an `<a>` counterpart
  `ButtonLink`.
- `frontend/src/components/ui/Toolbar.tsx` — `Toolbar`, `ToolbarGroup`,
  and a reusable `FilterChips<T>` used by the Applications page.
- `frontend/src/components/ui/PageHeader.tsx`,
  `SectionCard.tsx`, `EmptyState.tsx`, `SettingsGroup.tsx`,
  `StatusBadge.tsx` — carried over from task 103, now restyled.
- `frontend/src/layout/Layout.tsx` — sticky sidebar with grouped nav,
  active-route highlight, and the bottom-left activity center.
- `frontend/src/components/activity/` — `SidebarActivityCenter`,
  `ActivityPopover`, and `ActivityItem` (task 117), backed by
  `GET /activity`.

## Pages redesigned

- App shell (`layout/Layout.tsx`).
- Applications (`pages/ApplicationsPage.tsx`).
- Settings (`pages/SettingsPage.tsx`).
- Job Detail (`pages/JobDetailPage.tsx`) — new workspace layout.
- Dashboard (`pages/DashboardPage.tsx`) — picks up the new header /
  card / next-action polish from CSS, no structural changes.
- Runs / Captures / Jobs — adopted `PageHeader` + `EmptyState`.

## Known remaining rough edges

- The Job Detail workspace tabs (Runs / Drafts / Artifacts) referenced
  in the redesign brief did not land. The aside summarises counts
  instead; promoting them to a real tabbed view is a follow-up.
- Run Detail and Capture Detail received only the inherited shell
  polish (PageHeader from the parent pages); a dedicated layout pass
  per the brief is still outstanding.
- The Settings "Danger zone" and "Browser extension" panels are
  informational placeholders — there is no in-app reset / extension
  install action yet.
- The Applications table's row actions still use the small
  secondary/ghost button set; a single overflow menu (`ActionMenu`)
  would be tidier on very narrow screens.

## Resume Review page (task 113)

The interactive resume suggestion review surface lives at
`pages/ResumeReviewPage.tsx`, routed at
`/resume-versions/:versionId/review` and reachable from the draft detail
page via the "Review AI suggestions" link.

- **Layout**: a `PageHeader` (target role + company, an "Apply accepted
  suggestions" primary action, and an accepted/total summary) over a
  stack of `SectionCard`s — one per resume section. Suggestions are
  grouped by `section_id`/`section_heading`, so the page reads as a
  section-by-section resume preview with the AI suggestions for each
  section inline beneath it.
- **Suggestion cards** (`components/SuggestionCard.tsx`): each card shows
  the section, operation, current vs. suggested text, the reason,
  compact evidence references, the ATS keywords addressed, and
  confidence/risk badges. Actions are `Accept`, `Reject`, and
  `Ask to revise` (which reveals an inline textarea that stores a
  revision instruction). Accepted cards are visually marked (green
  surface) so the preview reflects the working state; rejected cards
  dim.
- **Data flow**: the page calls `getResumeSuggestions`, then
  `acceptSuggestion` / `rejectSuggestion` / `reviseSuggestion` per card,
  and `applyResumeSuggestions` to rebuild the working structured resume
  from the accepted set. Statuses come back from the API and update the
  card in place. See `docs/contracts/claude_run_directory.md`
  ("Structured Resume Suggestions") for the schema, statuses, and the
  relationship to the deterministic DOCX renderer.

The preview is intentionally structural, not a pixel-faithful DOCX
render — the deterministic renderer (task 111) owns the final document;
this page owns the accept/reject/revise decisions that feed it.

## Word-like review workspace (task 114)

Task 114 replaced the task-113 card stack at
`/resume-versions/:versionId/review` with a three-panel, document-editor
workspace. The route, data flow, and accept/reject/revise endpoints are
unchanged; the layout and presentation are new.

- **Layout** (`components/review/ResumeReviewWorkspace.tsx`): a slim top
  bar (back link, document title + target role/company, accepted/total
  progress, and the `Apply accepted suggestions` action) over a CSS-grid
  three-panel body — left workflow rail, center document preview, right
  AI review panel. The shell uses the wide content container
  (`Layout.isWidePath` now treats any `…/review` path as wide).
- **Left — workflow rail** (`WorkflowRail.tsx`): the five-step pipeline
  (Job · Evidence · Tailoring · Review · Export) with per-step status
  (`complete` / `active` / `blocked` / `failed`). Numbered markers turn
  into ticks once complete; the active step gets the accent bar. Export
  flips to `complete` once suggestions have been applied.
- **Center — document preview** (`ResumeDocumentPreview.tsx` +
  `ResumePage` / `ResumeHeaderPreview` / `ResumeSectionPreview` /
  `ResumeExperienceEntryPreview` / `ResumeBulletList`): renders the
  structured resume as a white, Letter-proportioned page on a neutral
  background with a soft shadow, document-sized (12px) type, a centered
  header, uppercase accent section headings, right-aligned dates, and
  real bullet lists. Each section is a click target; sections carrying
  suggestions get a subtle track-changes flag and left accent bar.
- **Right — AI review panel** (`ReviewPanel.tsx`): shows the selected
  section's suggestions via the existing `SuggestionCard` (previous vs.
  suggested text, reason, evidence, ATS keywords, risk, and
  accept/reject/revise). A section with no suggestions shows a useful
  empty state; a draft with no suggestions at all shows a page-level
  empty state.
- **Document model** (`lib/reviewModel.ts`): `buildPreviewDocument`
  prefers the applied `working_resume` over the `base_resume`, maps each
  suggestion onto its section by normalized heading/id, and appends any
  unmatched suggestions (or all suggestions, when no structured resume is
  present) as derived sections so nothing is lost. Section-level diff:
  an accepted `replace_section_text` is reflected live in the preview.
- **Backend** (`routers/resume_versions.py`, `schemas.py`): the
  `GET /resume-versions/{id}/suggestions` response now includes the
  structured `base_resume` and `working_resume` (read from
  `suggestion_review_state`) so the frontend can render a real document
  preview rather than reconstructing one. The fields are optional, so
  pre-task-114 drafts still load.

Design tokens: a `--font-xs … --font-xl` scale was added to `:root`
alongside the existing `--space-*` scale; the document page deliberately
uses smaller, document-like type instead of the dashboard body size, and
badges/pills in the narrow review panel are overflow-guarded (clamped
with ellipsis) so long status/risk/keyword text never spills its
container.

Entry points: `Open review workspace` links were added to the
application detail page (resume-version row) and the run detail page
(resume-version line), complementing the existing link from the draft
detail page.
