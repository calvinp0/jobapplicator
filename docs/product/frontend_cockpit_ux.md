# Frontend Cockpit UX Specification

## Purpose

This document defines how the job-apply frontend should present itself to a single end user
who is using the app to tailor resumes and manually submit job applications.

The app is technically backed by jobs, runs, resume versions, and applications. The UI must
not expose that vocabulary. Instead, the UI must feel like a guided **application cockpit**:
a workspace per job that walks the user from "I just captured this job" to "I sent the
application."

This spec is the canonical reference for:

- the workflow the UI guides the user through,
- the user-facing language the UI must use,
- the backend/provenance terms the UI must hide by default,
- the run/draft status mapping the UI must use,
- behavior rules for each major page,
- and the manual smoke checklist for verifying the cockpit feel end-to-end.

Tasks 033–039 implement this spec. Future UX work in this area should update this spec first.

## Current problems

These are observed pain points in the current frontend. The redesign must explicitly fix
them.

1. **`JobDetailPage` is a flat stack of sections.** It currently renders sections such as
   "Tailored resumes", "In-flight runs", "Submit this job", and "Tailor a new resume" as
   independent H3 blocks. There is no sense of "step 1, step 2, step 3"; the user has to
   infer the workflow from layout order. The page must instead present an explicit five-step
   workspace.

2. **In-flight run status uses an invented status value.** The page renders a status of
   `completed-not-imported`, but the backend never writes that value. The backend writes
   `completed` and then, after import, `imported`. A run that is `completed` but has no
   imported `ResumeVersion` must be detected by a frontend helper, not pulled from the
   backend status enum.

3. **`RunDetailPage` exposes raw backend verbs.** The page surfaces operator actions named
   `Invoke` and `Import outputs` directly to the user. These verbs are implementation
   language. The default UI must use `Start tailoring` and `Retry import`, and only inside
   Advanced details.

4. **`RunDetailPage` does not poll.** A user who starts tailoring has to refresh the page to
   see whether the run finished. The page must poll while the run is active or needs import
   and stop polling on terminal states.

5. **Import failures show raw request/status strings.** Errors like
   `Request to /runs/.../import failed with status 400` reach the UI. The UI must extract
   `detail` from the response body and render a human message instead.

6. **The job description is hidden behind a bare disclosure that looks like a text field.**
   Users do not realize they can click it. It must be a clearly clickable button/section
   toggle.

7. **Resume versions are labeled `Version 1`, `Version 2`.** "Version" is backend language.
   The user-facing label is `Draft N`, with the latest approved draft called out by name.

8. **`SettingsPage` looks like a raw admin form.** Both master resumes and evidence banks
   render as inline forms over a list. They should appear as cards with the add forms
   collapsed by default.

9. **Dashboard labels are vague.** Tiles named `Ready to apply` and `Resumes ready` do not
   tell the user what they actually represent. The dashboard must use workflow-language
   labels like `Approved — ready to send` and `Drafts approved`.

## Core user workflow

The cockpit is organized around one job at a time. The user moves through these steps:

```text
Open job
→ read job description
→ choose master resume and evidence bank
→ generate tailored resume draft
→ see tailoring progress
→ review draft
→ approve draft or generate another draft
→ start application from approved draft
→ manually send application
→ mark application as sent
→ track activity
```

This is the workflow language the entire UI must speak.

The user-facing surfaces map to this workflow as follows:

- **Home / dashboard** — what to do next across all jobs.
- **Job workspace (`JobDetailPage`)** — the five guided steps for a single job.
- **Resume draft pages (`ResumeVersionDetailPage`)** — review and approve a generated draft.
- **Application pages (`ApplicationDetailPage`, `ApplicationsPage`)** — manual send tracking.
- **Settings** — manage master resumes and evidence banks.
- **Advanced details** (per page) — provenance and operator controls, collapsed by default.

## User-facing language rules

Default UI must use this workflow vocabulary:

```text
Application cockpit
Read job description
Choose resume source
Generate draft
Tailoring in progress
Draft ready to review
Approve draft
Approved — ready to send
Start application
I've sent it
Sent
```

The replacement terminology table is canonical. Where the left column currently appears in
the UI, the UI must use the right column:

| Old (backend-leaking)        | New (user-facing)                                     |
| ---------------------------- | ----------------------------------------------------- |
| Invoke                       | Start tailoring                                       |
| Import outputs               | Retry import / Load generated draft (advanced only)   |
| Tailored resumes             | Resume drafts                                         |
| Tailor a new resume          | Generate another draft                                |
| Submit this job              | Send your application                                 |
| Version 1                    | Draft 1                                               |
| Pending                      | Awaiting review                                       |
| Approved                     | Approved                                              |
| Ready to apply               | Approved — ready to send                              |
| Resumes ready                | Drafts approved                                       |
| Mark Submitted               | I've sent it                                          |

## Backend/provenance terms hidden by default

The following terms must not appear in default UI. They may only appear inside an
`Advanced details` disclosure block on a detail page, or in operator-facing surfaces:

```text
invoke
import outputs
Claude run
run id
version id
application id
content hash
prompt hash
run directory
DOCX path
raw backend status enum
raw API request path
```

If a value of one of these types is shown (for example a run ID for support purposes), it
must be inside `Advanced details` and never inside the main step body.

## Shared workflow/status model

All UI surfaces must use a single shared module (`frontend/src/lib/workflow.ts`) for
status-to-label mapping. No page may inline its own status labels.

The run status mapping is canonical:

```text
created   → Queued
running   → Tailoring in progress
completed → Draft ready to review
imported  → Draft imported
failed    → Tailoring failed
```

The frontend may compute a derived "needs import" state. This is not a backend status:

```text
completed-not-imported is not a backend status.
It is computed in the frontend as:
run.status === "completed" && no ResumeVersion references this run.
```

Helpers exported from `workflow.ts`:

- `runStatusLabel(status)` — user-facing label for a backend run status.
- `runIsActive(status)` — true when `created` or `running`.
- `runIsComplete(status)` — true when `completed` or `imported`.
- `runNeedsImport(run, versions)` — true when the run is `completed` and no `ResumeVersion`
  references it.
- `draftLabel(versionIndex)` — returns `Draft N`, where N is 1-based ordering by creation.
- `draftStatusLabel(approval)` — `Awaiting review` for pending, `Approved` for approved.
- `jobStageLabel(stage)` — workflow stage label used on the dashboard.
- `computeJobStage(job, runs, versions, application)` — returns the workflow stage a job is
  currently in (e.g. `captured`, `tailoring`, `draft_ready`, `approved`, `sent`).

There is also a shared API error helper (`frontend/src/lib/api-errors.ts`):

- `extractApiDetail(err: unknown): string` — pulls a useful message out of an error. If the
  underlying response has a JSON `detail` field, return that. Otherwise return a clean
  fallback message; never return raw `Request to /...` strings.

## Home/dashboard behavior

The dashboard is the entry point. It must:

- Display the page title `Application cockpit`.
- Show summary tiles using the new labels:
  - `Active jobs`
  - `Drafts approved` (replaces `Resumes ready`)
  - `Approved — ready to send` (replaces `Ready to apply`)
  - `Applications sent`
- Show a `Next action` panel for the user's current best next step, derived from
  `computeJobStage`.
- Show recent activity using workflow language ("Draft ready to review", not "run completed").

The dashboard must never expose run IDs, prompt hashes, content hashes, or DOCX paths.

## Job detail page as central workspace

`JobDetailPage` is the cockpit's main workspace. It must be organized as five explicit
workflow step cards, in this order:

```text
1. Read the job description
2. Choose resume source
3. Generate a draft
4. Review and approve drafts
5. Send your application
```

### Step 1 — Read the job description

- **Purpose:** make the user confident they understand the role before they tailor.
- **Visible status:** none required; the step is informational.
- **Primary action:** clearly clickable `Read job description` button/toggle that expands
  the captured text.
- **Default UI:** title, company, location, expandable description.
- **Advanced details:** capture source URL, capture timestamp, capture ID.

### Step 2 — Choose resume source

- **Purpose:** select the master resume and (optionally) evidence bank the tailoring pass
  will use.
- **Visible status:** which master resume / evidence bank is currently selected.
- **Primary action:** select master resume; select evidence bank; link to Settings to add
  more.
- **Default UI:** two labeled selectors.
- **Advanced details:** content hashes of the chosen master resume and evidence bank.

### Step 3 — Generate a draft

- **Purpose:** turn the chosen resume + evidence into a tailored draft.
- **Visible status:** `Idle`, `Tailoring in progress`, `Draft ready to review`, or
  `Tailoring failed`. Status comes from `runStatusLabel` and the `runNeedsImport` helper.
- **Primary action:** `Generate draft` (first time) or `Generate another draft`
  (subsequent).
- **Default UI:** big primary button, a short explanation of what generating does, and the
  most recent run's user-facing status.
- **Advanced details:** run ID, prompt hash, run directory, raw status enum.

When a user clicks `Generate draft`, the frontend must create the run and invoke it as a
single user action.

### Step 4 — Review and approve drafts

- **Purpose:** let the user evaluate drafts and approve one.
- **Visible status:** per-draft `Awaiting review` or `Approved`.
- **Primary action:** `Open draft` (links to `ResumeVersionDetailPage`), `Approve draft`.
- **Default UI:** list of `Draft N` rows with status badges and the action buttons.
- **Advanced details:** resume version ID, DOCX path, source run ID.

### Step 5 — Send your application

- **Purpose:** kick off the manual send and let the user mark it as sent.
- **Visible status:** `No approved draft yet` / `Approved — ready to send` / `Sent`.
- **Primary action:** `Start application` (creates the application from the approved draft),
  then `I've sent it` after the user manually sends it externally.
- **Default UI:** which draft is approved, the start/send buttons, and the sent timestamp
  once sent.
- **Advanced details:** application ID, raw application status enum.

## Tailoring progress behavior

The tailoring progress experience spans `JobDetailPage` step 3 and `RunDetailPage`:

- The UI must **poll** `getRun(runId)` every five seconds while the run is active
  (`runIsActive`) or needs import (`runNeedsImport`).
- Polling must stop on terminal states (`imported` or `failed`).
- On transition from `running` to `completed`, the UI must call `importRun(runId)` once
  automatically. The user must not be required to know that import is a separate step.
- If `importRun` fails, the error message shown to the user must come from
  `extractApiDetail(err)`, not from the raw request URL/status.
- The default `RunDetailPage` must not surface `Invoke` or `Import outputs`. Operator
  controls live inside `Advanced details` with labels `Start tailoring` and `Retry import`.

## Resume draft/review/approval behavior

`ResumeVersionDetailPage` and the application pages that reference resume versions must use
draft language exclusively:

- Page heading: `Draft N for <job title> — <company>`.
- Status label: `Awaiting review` or `Approved`.
- Action button: `Approve draft`. Once approved, the active button is replaced with a
  read-only `Approved ✓` indicator.
- Open-file action: `Open draft file` (or similar workflow-language label).
- All error messages on approve/open-file actions go through `extractApiDetail`.

Application pages that reference the underlying resume version must also call it `Draft N`,
not `Version N`.

## Application creation/submission behavior

Manual send is a two-step flow inside the cockpit:

1. From `JobDetailPage` step 5, the user clicks `Start application`. This creates the
   application record from the approved draft.
2. The user manually submits the application using whatever external system the job uses
   (the app does not do this for them).
3. The user clicks `I've sent it` on `ApplicationDetailPage` (or directly in step 5) to
   record that the application was sent. The recorded backend `submitted` status maps to
   `Sent` in the UI.

Gating messages must use workflow language:

- Replace `Link an approved resume version first` with
  `Pick an approved draft on the job page first.`
- Replace `Linked resume version is not yet approved` with
  `This draft has not been approved yet. Approve it on the job page first.`

`ApplicationsPage` must use the new status labels (`Sent`, etc.) and avoid backend status
enums in default UI.

## Settings page behavior

`SettingsPage` must be a card-based admin surface, not a flat form:

- Master resumes appear as a card. Existing entries are list rows inside the card.
- Evidence banks appear as a separate card. Existing entries are list rows inside the card.
- The add form for each card is hidden by default.
- Each card has a `+ Add master resume` / `+ Add evidence bank` button that reveals the form.
- The form has a `Cancel` button that collapses it.
- A successful submit collapses the form and updates the list.

Empty-state copy is canonical:

```text
No master resumes yet — add one to enable tailoring.
No evidence banks yet — optional, but useful for grounded tailoring.
```

All error rendering on the settings page must go through `extractApiDetail`.

## Advanced details rules

Every detail page (`JobDetailPage`, `RunDetailPage`, `ResumeVersionDetailPage`,
`ApplicationDetailPage`) must have an `Advanced details` disclosure section. Inside it:

- IDs (run, version, application, capture), hashes (prompt, content), paths (run dir,
  DOCX), and raw backend status enums may appear.
- Operator-only controls (`Start tailoring`, `Retry import`) live here.

The disclosure must be **collapsed by default**, with a clear toggle. Default page content
must never depend on the user expanding it.

## Error-message principles

- Never render a raw `Request to /... failed with status N` string to a default user.
- All error rendering goes through `extractApiDetail(err)`.
- If the backend returns `{ detail: "..." }`, render `detail`.
- Otherwise render a short, friendly message such as `Something went wrong. Try again.`.
- Operator/debug details (request path, status code) may appear inside `Advanced details`,
  but never inline in the workflow.

## Future revision feedback flow

A future workflow lets the user request a revision of a generated draft — e.g. "rewrite the
summary to emphasize X" — without manually editing the file. This is **out of scope for the
033–038 task pack** because the backend does not yet model revision feedback.

When unblocked, the flow should look roughly like:

- On `ResumeVersionDetailPage`, alongside `Approve draft`, expose `Request revisions`.
- Clicking it opens a structured feedback form (free-text + optional checkboxes).
- Submitting the form triggers a new tailoring run, parameterized by the prior draft and
  the feedback.
- The new run shows up under step 4 as the next `Draft N`, with a visible link back to the
  draft it revises.

Task `039-revision-feedback-flow` tracks this work and is blocked on a backend schema/API
decision (likely an ADR update).

## Manual end-to-end smoke checklist

Run the local app and confirm:

- [ ] Home page shows `Application cockpit` title and the new summary tiles
      (`Active jobs`, `Drafts approved`, `Approved — ready to send`, `Applications sent`).
- [ ] No raw `Resumes ready` or `Ready to apply` strings appear anywhere in default UI.
- [ ] Opening a job shows the five-step workspace in order.
- [ ] Step 1 has a clearly clickable `Read job description` toggle (not a bare disclosure).
- [ ] Step 2 lets you pick a master resume and evidence bank, with a link to Settings if
      none exist.
- [ ] Step 3 has a single `Generate draft` button that creates and starts a run in one click.
- [ ] While tailoring, the UI shows `Tailoring in progress` and updates within ~5s without a
      manual refresh.
- [ ] When tailoring finishes, the UI shows `Draft ready to review` and a `Draft N` row
      appears under step 4 automatically.
- [ ] Step 4 rows use `Draft N` and `Awaiting review` / `Approved`, never `Version N` or
      `Pending`.
- [ ] Opening a draft shows `Draft N for <job title> — <company>` and an `Approve draft`
      button. After approving, the button is replaced by `Approved ✓`.
- [ ] Step 5 only enables `Start application` once there is an approved draft. Gating copy
      uses workflow language.
- [ ] After clicking `I've sent it`, the application status is `Sent` everywhere.
- [ ] No `Invoke` or `Import outputs` text appears in default UI. They only appear inside
      `Advanced details` as `Start tailoring` / `Retry import`.
- [ ] Triggering a bad import (e.g. against a broken run) shows a parsed message, not
      `Request to /runs/... failed with status 400`.
- [ ] Settings page shows master resumes and evidence banks as cards with collapsed add
      forms. `+ Add master resume` reveals the form; `Cancel` collapses it; submitting
      collapses it and updates the list.
- [ ] Empty Settings cards show the canonical empty-state copy.
- [ ] No run IDs, version IDs, application IDs, content/prompt hashes, run directories, or
      DOCX paths appear outside an expanded `Advanced details` block.
