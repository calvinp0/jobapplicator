# Frontend redesign (task 106)

Notes on the bold visual redesign that landed in task 106. Task 103 added
the reusable shell components (PageHeader, SectionCard, SettingsGroup,
EmptyState, StatusBadge); this pass turned those into a noticeably
different UI rather than a thin wrapper around the previous layout.

## What changed visually

- **Sidebar**: darker (`#0b0d18`) navigation rail with a soft accent
  gradient overlay, a square gradient brand mark, larger title, and a
  local-backend status footer. Active routes are highlighted with an
  accent left-bar and a tinted background instead of a flat solid fill.
- **Grouped nav**: the rail is split into `Track` (Dashboard, Jobs,
  Applications), `Create` (Captures, Runs), and `Configure` (Prompts,
  Settings). Only routes that actually exist in `App.tsx` are linked.
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
  active-route highlight, and a status footer.

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
