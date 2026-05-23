# 029 — Hide provenance behind an Advanced details disclosure

## Goal

Move raw provenance — content/prompt/input/output hashes, raw run
directory paths, DOCX/PDF filesystem paths, raw entity IDs — out of the
default view on `RunDetailPage`, `ResumeVersionDetailPage`, and
`ApplicationDetailPage`. These fields are essential for debugging and
auditing, but they clutter the default workflow view. The default UI
should show "what the user needs to act"; advanced details belong
behind an `<details>` disclosure so they remain one click away without
dominating the page.

This task is the "Default UI = user workflow / Advanced UI =
provenance/debug" rule applied to the three detail pages.

## Background

Read first:

- `docs/product_requirements.md` — the cockpit framing.
- `docs/adr/004-evidence-constrained-resume-tailoring.md` — why hashes
  exist and must remain inspectable (audit trail).
- `docs/adr/002-claude-code-worker-boundary.md` — why run directories
  exist; they remain visible behind the disclosure for debugging.
- `agent_tasks/016-frontend-runs-list-and-detail.md`,
  `agent_tasks/017-frontend-resume-version-approval-and-open-file.md`,
  `agent_tasks/018-frontend-applications-and-submit-flow.md` — the
  pages this task adjusts.
- `agent_tasks/027-frontend-dashboard-home.md` and
  `agent_tasks/028-frontend-job-detail-hub.md` — the design direction
  this task continues.
- Current page sources:
  `frontend/src/pages/RunDetailPage.tsx`,
  `frontend/src/pages/ResumeVersionDetailPage.tsx`,
  `frontend/src/pages/ApplicationDetailPage.tsx`.

## Scope

For each of the three detail pages, split the existing summary
`<dl class="run-meta">` into two blocks:

1. A "Summary" block (default-visible) showing only fields the user
   typically needs to act:
   - **RunDetailPage**: status, created/started/completed timestamps,
     any `error_message`, and the linked resume version link if one
     exists. Keep the existing Invoke and Import buttons inline as
     before.
   - **ResumeVersionDetailPage**: version number, linked job, source,
     created/approved timestamps, the Open DOCX / Approve buttons.
   - **ApplicationDetailPage**: status, submitted-at, linked job,
     linked resume version (with its approval state), Mark Submitted
     button, gating reason, the timeline, and the Record-event form.
2. An "Advanced details" block wrapped in `<details>` with
   `<summary>Advanced details</summary>`. This block contains the
   provenance fields removed from the summary:
   - **RunDetailPage**: run id, `run_dir`, prompt/input/output hashes.
   - **ResumeVersionDetailPage**: resume version id, claude run id
     (raw, in addition to any linked navigation), content hash,
     prompt hash, DOCX path, PDF path.
   - **ApplicationDetailPage**: application id, raw job id when no
     job has loaded, raw resume version id when no version has
     loaded, application created_at/updated_at.

Implementation notes:

- Render the `<details>` block as closed by default.
- Do not remove any data from the page. Every field that exists today
  must still be visible — either in the summary or inside the
  disclosure.
- Keep accessible labels: each provenance field should still be
  reachable via a `<dt>` / `<dd>` (or equivalent semantic) pair inside
  the disclosure, so screen readers can describe it.
- Continue to use the existing `truncateHash` / `formatTimestamp`
  helpers for consistent rendering. Do not duplicate them across
  files; if it makes sense, extract a single shared helper into one
  of the three page files and import it, **but only if that helper
  file is already in this task's allowed paths**. Otherwise leave
  the helpers in place.

Update `frontend/src/styles.css`:

- Add styles scoped to the disclosure block (e.g. `.advanced-details`,
  `.advanced-details > summary`) so the disclosure visually
  de-emphasizes itself relative to the summary.

Update the three corresponding tests:

- `frontend/src/test/runDetailPage.test.tsx`
- `frontend/src/test/resumeVersionDetailPage.test.tsx`
- `frontend/src/test/applicationDetailPage.test.tsx`

Each test must assert:

- The summary fields are visible without expanding the disclosure.
- The disclosure renders with the heading "Advanced details" and is
  closed by default.
- The provenance fields that moved into the disclosure are still
  reachable when the disclosure is expanded.

## Allowed files

- `frontend/src/pages/RunDetailPage.tsx`
- `frontend/src/pages/ResumeVersionDetailPage.tsx`
- `frontend/src/pages/ApplicationDetailPage.tsx`
- `frontend/src/test/runDetailPage.test.tsx`
- `frontend/src/test/resumeVersionDetailPage.test.tsx`
- `frontend/src/test/applicationDetailPage.test.tsx`
- `frontend/src/styles.css`
- `agent_tasks/queue.yaml`

## Forbidden files

- `backend/**`
- `extension/**`
- `runtime_prompts/**`
- `candidate_context/**`
- `runs/**`
- `docs/adr/**`
- `docs/product_requirements.md`
- `docs/architecture.md`
- `frontend/src/api/**`
- `frontend/src/pages/JobDetailPage.tsx`,
  `frontend/src/pages/DashboardPage.tsx`,
  `frontend/src/pages/JobsPage.tsx`,
  `frontend/src/pages/RunsPage.tsx`,
  `frontend/src/pages/ApplicationsPage.tsx`,
  `frontend/src/App.tsx`,
  `frontend/src/layout/Layout.tsx` — not in scope.

## Out of scope

- Renaming entity-style headings like "Resume version 1" — task 030.
- Adding status badges — task 030.
- Refactoring the shared timestamp/hash helpers into a new utility
  module — leave the helpers inline unless a single page can own a
  shared helper inside the files this task already touches.
- Any backend or API change.

## Acceptance criteria

- Each of the three detail pages renders an Advanced details
  `<details>` block containing the provenance fields enumerated above,
  closed by default.
- No data that was visible before is missing after this change.
- Existing user-facing actions (Invoke, Import, Open DOCX, Approve,
  Mark Submitted, Add event) continue to work and remain in the
  summary block, not behind the disclosure.
- `cd frontend && npm test` passes.
- `cd frontend && npm run build` succeeds.

## Verification

- `cd frontend && npm test`
- `cd frontend && npm run build`

## Git instructions

Commit locally with the message:

```
Hide provenance behind Advanced details disclosure on detail pages
```

Do not push.
