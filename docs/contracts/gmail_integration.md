# Gmail Integration Contract

This document pins the **data shape, vocabulary, and safety rules** for a
future Gmail-driven application-tracking flow. It is a design-only
contract: this task does not connect to Gmail, does not read mail, does
not send mail, and does not modify any Gmail-side state.

It expands the manual-entry `EmailLink` surface defined in
[`application_status.md`](application_status.md) and prepares the
backend model so that subsequent tasks can plug a real Gmail reader in
without further schema migrations or contract changes.

Where this contract overlaps
[ADR-010](../adr/010-application-status-timeline.md), ADR-010 supplies
the *why* and this document supplies the *exact names and shapes* a
future implementation must use.

## Goals

- Give each `Application` an explicit, finite `email_status` that the
  dashboard can render in one line ("waiting for confirmation",
  "confirmed by email", "rejection detected", etc.) instead of relying
  on the generic `Application.status` alone.
- Pin the persisted fields that a future Gmail reader will populate
  (`gmail_query`, `last_gmail_check_at`, classification metadata) so
  the read-side contract is stable before any network code exists.
- Pin the vocabulary of automated `classified_status` labels so the
  manual-entry path (today) and the automated path (later) speak the
  same language.
- Make the user the final reviewer for every uncertain match.

## Non-Goals

- **No Gmail OAuth in this task.** No client secret, no credential
  store, no consent screen, no token refresh.
- **No reading real emails in this task.** No IMAP, no Gmail API
  call, no message fetch.
- **No outbound mail.** The Gmail tracking flow never sends, replies,
  or forwards.
- **No Gmail-side mutation.** Never archive, delete, mark read,
  apply labels, star, snooze, or change filters in the user's
  mailbox.
- **No LinkedIn or other ATS automation.**
- **No change to Claude tailoring behavior.**
- **No automatic submission.** ADR-003 (Human-in-the-Loop Submission)
  still applies; this contract records inbound evidence only.

## Email Status Lifecycle

`email_status` is the per-application Gmail-tracking state surfaced on
`ApplicationRead`. It is **derived** server-side from the application's
submission state and attached `EmailLink` rows (plus, in the future,
Gmail-poll results). Clients must not re-derive it.

### Vocabulary

The canonical values are pinned by `EMAIL_STATUSES` in
`backend/app/models.py`:

```
not_watching
watching
confirmation_found
email_received
needs_review
classified_rejection
classified_interview
classified_assessment
classified_offer
classified_neutral
no_match
error
```

Meanings:

| State | Meaning |
|---|---|
| `not_watching` | Gmail tracking is not enabled for this application (e.g. it has not been submitted yet, or the user has not opted in). Default for every new application. |
| `watching` | Gmail tracking is enabled and the system is waiting for a matching email. |
| `confirmation_found` | A submission-confirmation email was found. |
| `email_received` | A potentially related email was found but has not been classified yet. |
| `needs_review` | A related email was found but the classifier's confidence is low and the user must review it. |
| `classified_rejection` | A rejection email was detected. |
| `classified_interview` | An interview invite or recruiter follow-up was detected. |
| `classified_assessment` | An assessment / coding challenge / take-home or other action-required email was detected. |
| `classified_offer` | A positive offer / approval email was detected. |
| `classified_neutral` | A related but non-decisive update was detected. |
| `no_match` | Gmail was checked and no related email was found. |
| `error` | The Gmail search or classifier failed. |

The set is closed: any value not in `EMAIL_STATUSES` is rejected by the
backend (see *Validation* below).

### Derivation rules (today)

In the current implementation only a subset of these states is emitted
because no Gmail poll exists yet. The derivation order is:

1. If at least one `EmailLink` is attached, use the latest one (per
   the ordering rule in `application_status.md`):
   - `classified_status == "confirmation"` →
     `confirmation_found`
   - `classified_status == "rejection"` →
     `classified_rejection`
   - `classified_status == "next_step"` →
     `classified_interview`
   - `classified_status == "offer"` → `classified_offer`
   - `classified_status == "other"` → `classified_neutral`
   - `classified_status is None` → `needs_review`
2. Else if `Application.submitted_at is not None` or
   `Application.status == "submitted"` → `watching`.
3. Else → `not_watching`.

`no_match` and `error` are reserved for the future Gmail poll path and
are not produced by the manual-entry flow.

### Validation

`EMAIL_STATUSES` is exposed as a tuple constant and as
`EMAIL_STATUS_SET` (a frozen lookup set) so any persisted or accepted
`email_status` value can be validated in one call. The helper
`is_valid_email_status(value)` returns `True` for any member of the
canonical set and `False` otherwise.

## Classification Labels

The future classifier categorizes each matching email into one of the
following labels. These are the **inputs** to `email_status`
derivation, not user-visible states.

```
submission_confirmation
rejection
interview_request
recruiter_followup
assessment
offer
application_update
newsletter_or_unrelated
unknown
```

These map onto the existing `EmailLink.classified_status` vocabulary
(which is the smaller, contract-frozen set):

| Classifier label | `EmailLink.classified_status` | Resulting `email_status` |
|---|---|---|
| `submission_confirmation` | `confirmation` | `confirmation_found` |
| `rejection` | `rejection` | `classified_rejection` |
| `interview_request` | `next_step` | `classified_interview` |
| `recruiter_followup` | `next_step` | `classified_interview` |
| `assessment` | `next_step` | `classified_interview` *(today)* — a follow-up task may split `assessment` into its own `EmailLink.classified_status` once ApplicationStatus.next_action grows an assessment lane. |
| `offer` | `offer` | `classified_offer` |
| `application_update` | `other` | `classified_neutral` |
| `newsletter_or_unrelated` | *(skipped — no row written)* | unchanged |
| `unknown` | `other` *(low confidence)* | `needs_review` |

Future task: lift `assessment` and `recruiter_followup` into their own
`EmailLink.classified_status` values once the manual-entry UI grows
matching choices. Doing it before then would create a label the manual
flow cannot produce.

## Matching Signals

When the Gmail poll fires, it builds a Gmail-search query from these
signals (in priority order):

1. **Company name** (exact phrase).
2. **Job title** (exact phrase).
3. **ATS sender domain** when known
   (`*@greenhouse.io`, `*@lever.co`, `*@workday.com`, `*@myworkdayjobs.com`,
   `*@ashbyhq.com`, etc.).
4. **Submitted-at timestamp** → `newer_than:` cutoff
   (default 90 days when submitted, 30 days otherwise).
5. **Known confirmation phrases** ("thank you for applying", "we have
   received your application", "your application to", etc.) — used as
   secondary boost, not as a sole match.
6. **User-provided search terms** — optional free-text override stored
   in `Application.gmail_query`. When set, this overrides the
   auto-built query.

Example auto-built query for `Company = "Example Aero Labs"`,
`Title = "Scientific Machine Learning Engineer"`:

```
("Example Aero Labs" OR "Scientific Machine Learning Engineer") newer_than:90d
```

Example user override stored verbatim:

```
from:talent@exampleaero.com OR "Aero Labs application"
```

A future ADR will pin the exact query-builder rules; this contract
only pins the inputs and the stored override field.

## Application Status Interaction

When a classification is recorded against an `EmailLink`, the existing
side-effect rules in `application_status.md` continue to apply:

| Classifier label | `Application.status` (post-side-effect) | `application.next_action` hint | `email_status` |
|---|---|---|---|
| `submission_confirmation` | unchanged (stays `submitted`) | "Waiting for response" | `confirmation_found` |
| `rejection` | `rejected` *(unless `withdrawn`)* | "Rejected" | `classified_rejection` |
| `interview_request` / `recruiter_followup` | `interview` *(unless `rejected`/`withdrawn`/`offer`)* | "Interview response needed" | `classified_interview` |
| `assessment` | `interview` *(today; future: keep `pending` + assessment lane)* | "Complete assessment" | `classified_interview` *(today)* / `classified_assessment` *(future)* |
| `offer` | `offer` *(unless `withdrawn`)* | "Respond to offer" | `classified_offer` |
| `application_update` | unchanged | unchanged | `classified_neutral` |
| `unknown` | unchanged | "Review detected email" | `needs_review` |

The status precedence rules in `application_status.md` (withdrawn is
sticky, terminal statuses block downgrades, etc.) are unchanged.

This task does **not** alter the side-effect mapping; it only
documents how a future expansion will plug in. Adding a real
`classified_assessment` route is a future task.

## Persisted Gmail-Tracking Fields

These columns live on `applications` so a future Gmail reader can be
swapped in without a schema change:

| Column | Type | Default | Purpose |
|---|---|---|---|
| `gmail_query` | `TEXT NULL` | `NULL` | User-provided Gmail search override. `NULL` means "use the auto-built query". |
| `last_gmail_check_at` | `DATETIME NULL` | `NULL` | Wall-clock of the last successful Gmail-poll attempt for this application. Used to throttle re-checks and to show "checked X minutes ago" in the UI. |

`matched_email_count` and `last_matched_email_at` are **derived** from
attached `EmailLink` rows, not stored. Storing them would require keeping
two sources of truth in sync.

Existing rows backfill to the defaults above via
`ensure_runtime_columns()`; existing application data without these
fields continues to load.

## ApplicationRead Surface

`ApplicationRead` exposes the Gmail tracking state with these fields
(in addition to the existing `timeline_stage`, `last_email_link`,
`email_link_count`, `status`, `submission_status`, `email_status`,
`next_action`, etc.):

| Field | Type | Description |
|---|---|---|
| `gmail_query` | `string \| null` | The user-provided override, mirrored from the column. |
| `last_gmail_check_at` | ISO-8601 datetime \| null | The column value. |
| `last_matched_email_at` | ISO-8601 datetime \| null | `received_at` (or `created_at` fallback) of the most recent attached `EmailLink`. `null` when no links exist. |
| `matched_email_count` | integer | Same value as `email_link_count` today; kept as a separate name so the dashboard can rename the column without breaking the older field. |
| `latest_email_subject` | `string \| null` | Mirror of the latest link's `subject`. |
| `latest_email_from` | `string \| null` | Mirror of the latest link's `sender`. |
| `latest_email_snippet` | `string \| null` | Reserved. `null` today; will hold a short body excerpt once the Gmail reader exists. |
| `latest_email_classification` | `string \| null` | Mirror of the latest link's `classified_status`. |
| `latest_email_confidence` | `float \| null` | Mirror of the latest link's `confidence`. |
| `latest_email_evidence` | `string \| null` | Reserved. `null` today; will hold a short evidence quote (the matched phrase) once classification runs. |

The reserved fields (`latest_email_snippet`, `latest_email_evidence`)
exist now so the wire format does not change when the Gmail reader
ships.

## Backend Helpers

These helpers live in `backend/app/routers/applications.py` and are
the single source of truth for derivation. They are documented here so
downstream tasks (and tests) can refer to them by name.

```
derive_email_status(application, sorted_links) -> str
    Pure function. Returns one of EMAIL_STATUSES.

derive_next_action(application, sorted_links) -> str
    Returns the dashboard "next action" string. Includes Gmail-aware
    wording such as "Waiting for email" when email_status == watching
    and "Review detected email" when email_status == needs_review.

build_default_gmail_tracking_state() -> dict
    Returns the default-shaped dict for a brand-new application:
        {
          "email_status": "not_watching",
          "gmail_query": None,
          "last_gmail_check_at": None,
          "last_matched_email_at": None,
          "matched_email_count": 0,
          "latest_email_subject": None,
          "latest_email_from": None,
          "latest_email_snippet": None,
          "latest_email_classification": None,
          "latest_email_confidence": None,
          "latest_email_evidence": None,
        }

is_valid_email_status(value) -> bool
    Membership test against EMAIL_STATUS_SET. Used by validators and
    tests.
```

A `set_email_status(...)` helper is intentionally **not** provided:
`email_status` is derived, not stored. The way to change it is to
attach a new `EmailLink` (or, in the future, to record a Gmail-poll
result).

## Privacy and Safety Rules

Every Gmail-related component the project ships **must** follow these
rules:

1. **Read-only access first.** The first Gmail implementation requests
   the minimum read scope; no write scope is ever requested at this
   stage.
2. **Never send.** The Gmail tracking flow never sends, replies to, or
   forwards mail.
3. **Never mutate the mailbox.** No archive, delete, mark-read, label
   apply, star, snooze, or filter changes on the user's behalf.
4. **Minimum metadata.** Store only the fields needed to track an
   application: `gmail_message_id`, `gmail_thread_id`, `subject`,
   `sender`, `received_at`, `classified_status`, `confidence`, and a
   short evidence snippet. Do **not** persist full email bodies.
5. **Evidence, not bulk.** When the classifier flags a message, the
   stored "evidence" is the short phrase that matched, not the entire
   message.
6. **User reviews uncertain matches.** Any classification below a
   confidence threshold lands in `email_status = needs_review` and
   does **not** transition `Application.status`.
7. **Every automatic status change is auditable.** The
   `ApplicationEvent` log records the email that triggered each
   transition (already enforced by the side-effect rules in
   `application_status.md`).
8. **Local-first.** Per ADR-001 every persisted byte stays on the
   user's machine. No remote sync of mailbox content.

## Validation

The contract defines two membership sets that the backend exposes for
the rest of the app and the tests:

- `EMAIL_STATUSES` (tuple) — full canonical vocabulary, suitable for
  human-readable listings.
- `EMAIL_STATUS_SET` (frozenset) — fast membership lookup, suitable
  for validators.

Any caller that wants to persist or accept an `email_status` value
checks `value in EMAIL_STATUS_SET`. Invalid values are rejected at
the boundary; downstream code may assume the value is canonical.

## Future Task Breakdown

This contract is the design surface. The work that builds on it is
intentionally split across small, reviewable tasks:

1. **Gmail OAuth + credential store.** A separate ADR plus a task to
   stand up the OAuth flow, the token store, and a "Gmail connected"
   surface on the settings page. Read-only scope.
2. **Gmail poll + classifier MVP.** A periodic background task that
   builds the query from the matching signals above, fetches matching
   messages, classifies them (heuristics first, model later), writes
   `EmailLink` rows, and updates `last_gmail_check_at` /
   `last_matched_email_at`.
3. **`classified_assessment` split.** Add `assessment` to
   `EmailLink.classified_status` and the manual-entry UI; route it to
   `email_status = classified_assessment` and `next_action = "Complete
   assessment"`.
4. **`needs_review` UI.** Surface the uncertain matches in the
   Applications dashboard with a "confirm match / dismiss" affordance.
5. **`no_match` and `error` surfacing.** Show the timestamp of the
   last failed poll and a retry button.
6. **Frontend label refresh.** Add labels for the new `email_status`
   values (`confirmation_found`, `classified_interview`,
   `classified_offer`, `classified_assessment`, `no_match`, `error`)
   in `frontend/src/lib/workflow.ts`.
7. **Gmail-side write capabilities (if ever).** A separate ADR
   required before any write scope is requested.

Each task is gated on this contract; none of them require changes to
this document so long as the wire shape and vocabulary above hold.
