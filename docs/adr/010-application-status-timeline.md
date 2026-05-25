# ADR-010: Application Status Timeline and Gmail Integration Boundary

## Status

Accepted

## Context

The MVP tracks one row per application in the `applications` table, with
a coarse `status` field (`draft`, `generated`, `approved`, `submitted`,
`response_received`, `rejected`, `interview`, `offer`, `withdrawn`) and
an optional `submitted_at` timestamp. The frontend currently surfaces
`submitted` prominently and treats every later state as a generic
label, which under-uses the information already in the schema.

A second table — `email_links` — already exists alongside
`applications`. It has columns for `gmail_message_id`,
`gmail_thread_id`, `subject`, `sender`, `received_at`,
`classified_status`, and `confidence`, plus an `application_id`
foreign key. Today no router writes to it, no schema covers it, and
the UI never reads it. Its shape clearly anticipates a future Gmail
integration: a classifier will inspect incoming mail and label each
message as confirmation / rejection / interview-invite / offer / other,
with a confidence score.

Two things constrain how we move forward:

- **Gmail is out of scope for the first MVP.** The product
  requirements list "No Gmail integration in the first MVP" as a
  non-goal. We do not have Gmail credentials, a polling mechanism, a
  classifier, or thread-to-application matching today, and we do not
  intend to build them as part of this ADR.
- **ADR-003 (Human-in-the-Loop Submission)** keeps the user in control
  of submission. Any timeline mechanism we introduce must not become a
  pathway to automated sends, automated reply, or any other behavior
  that erodes the human-in-the-loop rule.

At the same time, users do see employer mail today — confirmations
land in their inbox the moment they submit, and rejection or
next-step mail follows over days or weeks. Recording that evidence
against the application is independently useful even without a Gmail
integration: a user can paste a subject and sender by hand and have
the timeline reflect it.

This ADR locks in the user-facing model and the data surface so that
follow-up backend, contract, and frontend tasks can be built against a
stable target, and so that a later Gmail-integration ADR can plug in
without redesign.

## Decision

### Timeline as a derivation

An application's user-visible lifecycle is a **timeline** of stages,
*derived* from existing data — not a new column. The inputs to the
derivation are:

- `Application.status` (authoritative coarse state),
- `Application.submitted_at` (the moment the user pressed "Mark
  Submitted"),
- the set of `EmailLink` rows attached to the application, with their
  `classified_status` and `received_at` values.

The stages the UI surfaces, in chronological order:

- `draft` — the application row exists but no `submitted_at` has been
  set yet. Maps to `Application.status in {"draft", "generated",
  "approved"}` with `submitted_at is null`.
- `sent` — `submitted_at` is set and no `EmailLink` rows are attached
  yet. Maps to `Application.status == "submitted"` with no email
  evidence.
- `confirmation_received` — `submitted_at` is set and at least one
  attached `EmailLink` has `classified_status == "confirmation"`, but
  no further employer signal has arrived. `Application.status` remains
  `submitted` in this stage (see "Status transitions" below).
- `response_received` — a non-confirmation `EmailLink` is attached, or
  the user has manually advanced `Application.status` to
  `response_received`. This stage is the "something happened but it
  is not yet a terminal outcome" bucket.
- `interview` — the application has advanced to an interview / phone
  screen / take-home / recruiter screen. Maps to
  `Application.status == "interview"`.
- `rejected` — explicit "no" from the employer. Maps to
  `Application.status == "rejected"`.
- `offer` — formal offer received. Maps to
  `Application.status == "offer"`.
- `withdrawn` — the user withdrew. Maps to
  `Application.status == "withdrawn"`. Withdrawal is sticky: see
  "Status transitions" below.

The timeline is **a view, not a column.** `Application.status` and
`EmailLink` rows are the persistent inputs; the stages above are
computed in the backend response (or in the frontend, where the same
evidence is available) and do not require a schema change.

### `EmailLink.classified_status` canonical values

The canonical values for `EmailLink.classified_status` are:

- `confirmation` — the recipient acknowledged that the application
  was received. ATS auto-replies ("We've received your application
  for…") fall here.
- `rejection` — explicit "no" from the employer.
- `next_step` — interview invite, take-home assignment, recruiter
  screen, hiring-manager intro, or any other forward-progress
  signal that is not a formal offer.
- `offer` — formal offer.
- `other` — fallback for mail that does not clearly fit the categories
  above. Used when the user wants to record evidence (e.g. a thank-you
  note) without forcing it into a category.

These values are stable strings. The database stores them as TEXT,
following the existing convention in `backend/app/models.py` (see
`APPLICATION_STATUSES`, `CLAUDE_RUN_STATUSES`,
`REVISION_FEEDBACK_STATUSES`). The follow-up contract/router task may
pin them to a module-level tuple
(`EMAIL_LINK_CLASSIFIED_STATUSES = ("confirmation", "rejection", "next_step", "offer", "other")`)
mirroring that pattern. `classified_status` remains nullable so a
recorded email without a label is still a valid row.

The `confidence` column is reserved for a future classifier and is
unused by this ADR. Manual entries leave it null.

### Manual EmailLink entry is allowed today

Until Gmail integration lands, the user may record an `EmailLink`
**manually**, via a new endpoint and UI control introduced by the
follow-up tasks. For manual entries:

- `gmail_message_id` may carry a placeholder of the form
  `manual:<uuid>`. The column remains non-null (as the schema
  requires), but its value is a stable, unique placeholder rather
  than a real Gmail message id.
- `gmail_thread_id` may be null.
- `subject`, `sender`, and `received_at` are user-supplied.
- `classified_status` is user-chosen from the canonical values above.
- `confidence` stays null.

A future Gmail-integration ADR will tighten the contract — for
example, by reserving real Gmail ids and forbidding overlap between
the `manual:` namespace and real Gmail message ids. Until then, the
`manual:` prefix is the agreed convention so the two populations
remain distinguishable.

### Status transitions driven by email evidence

When the backend records a new `EmailLink` against an `Application`,
it applies a small, deterministic rule set to `Application.status`
and appends an `ApplicationEvent` for each transition it makes:

- If `classified_status == "confirmation"`: do **not** change
  `Application.status`. A confirmation only acknowledges that the
  employer's intake system received the submission; it does not
  reflect any decision from the employer's side. The confirmation
  is visible in the timeline as the `confirmation_received` stage,
  but it does not progress the application.
- If `classified_status == "rejection"` and
  `Application.status not in {"withdrawn", "offer"}`:
  set `Application.status = "rejected"` and append an
  `ApplicationEvent` of type `email_rejection`.
- If `classified_status == "next_step"` and
  `Application.status not in {"rejected", "withdrawn", "offer"}`:
  set `Application.status = "interview"` and append an
  `ApplicationEvent` of type `email_next_step`. The ADR chooses
  `interview` (rather than leaving the row at `response_received`)
  because the existing `APPLICATION_STATUSES` enum already includes
  `interview` as the coarse forward-progress value, and collapsing
  every non-confirmation signal into `response_received` would
  discard information the schema is already able to carry. The user
  can always override manually if the email was, say, a recruiter
  intro that they do not want to count as an interview yet.
- If `classified_status == "offer"` and
  `Application.status != "withdrawn"`: set
  `Application.status = "offer"` and append an `ApplicationEvent`
  of type `email_offer`.
- If `classified_status == "other"` or is null: do not change
  `Application.status`. The row is still attached and visible in the
  timeline; the user may advance status manually if they choose.

`withdrawn` is sticky: an email landing after the user has withdrawn
never reopens the application's status. The email row is still
recorded so the user can see it, but `Application.status` stays
`withdrawn`.

`offer` is treated as terminal for purposes of these rules: a later
`rejection` or `next_step` email does not overwrite an existing
`offer` status. The user may still manually change status if they
need to.

A manual override by the user (changing `Application.status`
directly through the existing applications router) always wins. The
email-driven rule fires only when a new `EmailLink` is recorded, not
on a periodic re-derivation.

### Gmail integration is out of scope

This ADR explicitly defers, and does **not** decide:

- the Gmail credential model (OAuth flow, token storage, refresh,
  revocation);
- polling cadence, batch size, or backoff behavior;
- dedupe rules for incoming Gmail messages (e.g. how to avoid
  re-inserting the same message id);
- server-side classification — the `EmailLink.confidence` column is
  reserved for this but unused for now, and the canonical
  `classified_status` values above are filled in manually today;
- automatic resolution of `Application` ↔ `gmail_thread_id` (matching
  inbound mail to the right application);
- any Gmail-side write actions (replies, labels, archival). None are
  introduced here.

A future ADR will cover those decisions. This ADR only locks in the
user-facing timeline and the data surface (`EmailLink`'s shape and
classified-status vocabulary) that a Gmail integration will later
populate.

### Human-in-the-loop preservation

Per ADR-003, the user remains in control of submission. This ADR
adds **no outbound mail, no auto-reply, no auto-submission, and no
automated next-action triggers.** The only writes this ADR enables
are recording inbound evidence (manually today, machine-classified
later) and the small `Application.status` adjustments listed above
in response to that evidence. Every transition leaves an
`ApplicationEvent` so the user can audit what changed and why.

## Rationale

**Why a derived timeline rather than a new column.** The schema
already carries enough information to render a richer lifecycle —
`Application.status`, `submitted_at`, and `EmailLink` rows together
describe the state. Adding a `timeline_stage` column would introduce a
second source of truth that must be kept in sync with `status` and
the email rows, and would invite drift. A derivation has a single
source of truth per input and can be computed identically by backend
and frontend.

**Why pin the `classified_status` vocabulary now.** Without a fixed
vocabulary the manual entry path would invent labels ("Auto-reply",
"Acknowledged", "Reject letter", "Recruiter ping") that the future
Gmail classifier would then have to reconcile. Pinning the five
canonical values up front — `confirmation`, `rejection`, `next_step`,
`offer`, `other` — gives the manual path and the future automated
path one shared label set. `other` is the safety valve that prevents
users from forcing mail into a category just to record it.

**Why `confirmation` does not advance status.** Confirmations are a
signal that the *send* worked, not that the *employer* has acted.
Treating a confirmation as forward progress would inflate the
apparent funnel: every submitted application would advance to
`response_received` within minutes, drowning the signal of an actual
human response. Holding `confirmation` to a timeline-only stage
keeps `Application.status` meaningful as a measure of employer-side
progress.

**Why `next_step` maps to `interview`.** The existing
`APPLICATION_STATUSES` enum already has `interview` as the natural
coarse value for "the employer wants to talk to me." Mapping
`next_step` emails to `interview` uses the schema we have rather
than introducing a parallel "next_step" status that would duplicate
it. The trade-off is that a recruiter ping is bucketed alongside a
formal interview invite; the timeline view can still differentiate
them by surfacing the underlying email, and the user can override
manually if they want a stricter definition of "interview".

**Why allow manual EmailLink entry now.** Even without Gmail
polling, a user who pastes the subject line of a rejection email
turns three otherwise-invisible facts (the rejection happened, when,
and from whom) into structured data that the timeline can show. The
cost is one endpoint and one UI control; the benefit is that the
feature is useful from day one and the future Gmail integration is
purely additive rather than gated on a new data model.

**Why `manual:<uuid>` for `gmail_message_id`.** The column is
non-null in the existing schema and we are deliberately not
migrating it. A namespaced placeholder is the cheapest way to
satisfy the non-null constraint and to keep manual entries
distinguishable from real Gmail ids without a schema change.

**Why reassert ADR-003 explicitly.** A status-tracking surface that
*looks* like a control panel for outbound mail is the most natural
place to accidentally erode the human-in-the-loop rule. Naming the
boundary here, alongside the email semantics, keeps the constraint
load-bearing for downstream tasks.

## Consequences

- A follow-up contract task (071's prerequisite) extends the API
  surface to expose `EmailLink` rows under their `Application`, define
  the manual-entry endpoint shape, and document the
  `classified_status` vocabulary and the `manual:<uuid>` placeholder
  convention.
- A follow-up backend task adds the `EmailLink` router, persists
  manual entries with the placeholder `gmail_message_id`, applies
  the status-transition rules above, and writes `ApplicationEvent`
  rows for each rule firing.
- Follow-up frontend tasks render the derived timeline on the
  applications list and the application detail page, and add the
  manual-entry UI for recording an email.
- The schema does not change. `Application`, `ApplicationEvent`, and
  `EmailLink` retain their current shape. No migration is required
  for this ADR.
- `runtime_prompts/` and the Claude Code worker are unaffected.
  Resume tailoring (ADR-004) and the worker boundary (ADR-002) are
  not touched by this decision.
- ADR-001 (local-first MVP) is preserved: manual EmailLink entries
  live in the local SQLite database alongside the rest of the
  application state. Nothing in this ADR introduces a hosted
  dependency.
- A future Gmail-integration ADR will plug into the same
  `EmailLink` shape and the same `classified_status` vocabulary, and
  will need to address only the topics deferred above (credentials,
  polling, dedupe, classification, thread matching).

## Alternatives Considered

- **Add a `timeline_stage` column to `Application`.** Rejected.
  Introduces a second source of truth that must be kept in sync with
  `status` and email evidence. A derivation off existing data is
  cheaper, harder to desync, and identically computable on backend
  and frontend.
- **Wait for Gmail integration before designing the timeline.**
  Rejected. Gmail integration is deferred for good reasons (scope,
  credentials, classification quality), but the UI gap exists today.
  Manual entry gives the timeline real evidence to render now and
  defines the data surface a future Gmail integration will populate.
- **Use a free-form string for `classified_status`.** Rejected.
  Without a fixed vocabulary the manual path and the future
  automated path would diverge in labeling, and the UI would have to
  reconcile arbitrary strings. Pinning five canonical values up
  front is a small constraint that prevents a large compatibility
  problem later.
- **Treat `confirmation` as forward progress (advance status to
  `response_received`).** Rejected. Inflates the funnel and dilutes
  `Application.status` as a measure of employer-side progress.
  Confirmations are timeline-only.
- **Map `next_step` to `response_received` rather than `interview`.**
  Considered. It is the more conservative mapping — a recruiter
  ping is not literally an interview. Rejected because the existing
  enum already has `interview` and using it captures more
  information; the user can manually downgrade if needed. The
  reverse — using only `response_received` — discards a distinction
  the schema is already willing to carry.
- **Skip a manual-entry path and ship Gmail integration directly.**
  Rejected. Gmail integration is a multi-axis decision (credentials,
  polling, classification, matching) and is explicitly deferred. A
  manual entry path is a small surface that unlocks the UI today and
  imposes no constraint on the future automated path.
- **Add an automatic-send capability alongside email tracking.**
  Rejected outright. Out of scope and contrary to ADR-003. This ADR
  records inbound evidence only.

## Notes

- This ADR refers to and is bounded by ADR-001 (Local-First MVP) and
  ADR-003 (Human-in-the-Loop Submission). Both invariants are
  preserved: state lives locally, and the user remains in control of
  submission.
- The downstream tasks that depend on this ADR are the contract
  update (task 070), the backend router and transition rules (task
  071), and the frontend timeline plus manual-entry UI (tasks 072
  and 073). This ADR locks the model; those tasks implement it.
- A separate, future ADR will cover the Gmail integration itself:
  credential model, polling, dedupe, server-side classification,
  thread-to-application matching, and any Gmail-side writes.
