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

## Read-Only OAuth Connection (task 082)

Task 082 lands the first piece of the future-task list above: the
Gmail read-only OAuth flow and a safe test-search surface. It adds
**no** classification, matching, polling, archiving, sending, or
mailbox mutation; all of those remain future work.

### Scope

The OAuth flow requests exactly one scope:

```
https://www.googleapis.com/auth/gmail.readonly
```

`backend/app/gmail_client.py` exposes `GMAIL_SCOPES = (GMAIL_READONLY_SCOPE,)`
and a `FORBIDDEN_SCOPES` frozenset that includes `gmail.send`,
`gmail.modify`, `gmail.compose`, `gmail.labels`, `mail.google.com`,
etc. The helper `assert_readonly_scope(scopes)` is called whenever the
backend builds an auth URL or loads a stored token; any forbidden
scope raises `GmailScopeError` and the token is treated as
disconnected.

### Configuration

The Gmail integration reads four environment variables:

```
GOOGLE_CLIENT_ID        OAuth client id from Google Cloud.
GOOGLE_CLIENT_SECRET    OAuth client secret from Google Cloud.
GOOGLE_REDIRECT_URI     Redirect URI registered with Google.
                        Default: http://localhost:8000/gmail/oauth/callback
GMAIL_TOKEN_PATH        Local path for the stored token blob.
                        Default: candidate_context/gmail/token.json
```

`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` are required for any OAuth
operation; if either is missing the `/gmail/auth-url` endpoint returns a
structured `400` (see *Configuration error reporting* below) and
`/gmail/status` reports `connected: false`, `configured: false`, and the
list of unset env var names in `missing_config`. The other two
variables have sensible local-dev defaults.

### Token storage

Tokens live in a single JSON file at the configured `GMAIL_TOKEN_PATH`.
The file is created on first successful OAuth exchange and contains:

```
token, refresh_token, token_uri, client_id, client_secret,
scopes (must include only gmail.readonly), expiry, saved_at, email
```

`email` is captured opportunistically via `users.getProfile` (allowed
by `gmail.readonly`) so the dashboard can render the connected
mailbox without an extra round trip. If the profile call fails the
field is `null`.

This is **development-grade** storage. The file holds a refresh token
in plain text and is excluded from git via `.gitignore`:

```
candidate_context/gmail/token.json
candidate_context/gmail/*.json
```

Production-grade secret management (OS keychain, encrypted store) is
out of scope.

### Backend endpoints

All four routes live in `backend/app/routers/gmail.py` and follow the
existing router convention (no `/api` prefix; same style as
`/applications`, `/jobs`, `/settings`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/gmail/status` | Connection state + connected email. |
| GET | `/gmail/auth-url` | Returns the Google consent URL + scope. |
| GET | `/gmail/oauth/callback` | Handles the OAuth redirect. |
| POST | `/gmail/test-search` | Runs a read-only Gmail query (capped). |

Response shapes:

```jsonc
// GET /gmail/status (not configured — env vars missing)
{
  "connected": false,
  "configured": false,
  "missing_config": [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI"
  ],
  "email": null,
  "scopes": [],
  "token_path_configured": true,
  "last_checked_at": null
}

// GET /gmail/status (configured but no token)
{
  "connected": false,
  "configured": true,
  "missing_config": [],
  "email": null,
  "scopes": [],
  "token_path_configured": true,
  "last_checked_at": null
}

// GET /gmail/status (connected)
{
  "connected": true,
  "configured": true,
  "missing_config": [],
  "email": "user@example.com",
  "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "token_path_configured": true,
  "last_checked_at": "2026-05-25T12:00:00+00:00"
}

// GET /gmail/auth-url
{
  "auth_url": "https://accounts.google.com/o/oauth2/auth?...",
  "scope": "https://www.googleapis.com/auth/gmail.readonly"
}

// POST /gmail/test-search request
{ "query": "newer_than:7d", "max_results": 5 }

// POST /gmail/test-search response
{
  "connected": true,
  "query": "newer_than:7d",
  "count": 1,
  "messages": [
    {
      "id": "<gmail-message-id>",
      "thread_id": "<gmail-thread-id>",
      "subject": "Thanks for applying",
      "from": "talent@example.com",
      "date": "Mon, 25 May 2026 12:00:00 +0000",
      "snippet": "We received your application..."
    }
  ]
}
```

`max_results` is clamped to `MAX_TEST_SEARCH_RESULTS = 10`. Only
metadata + Gmail's own snippet is returned; **no body, no html, no
attachments**. Returned messages are not persisted to the database in
this task.

### Manual verification

1. Create an OAuth 2.0 "Web application" client in Google Cloud
   Console. Add the redirect URI that matches `GOOGLE_REDIRECT_URI`
   (default `http://localhost:8000/gmail/oauth/callback`).
2. Export the four env vars above.
3. Install the optional gmail extras:

   ```bash
   cd backend && pip install -e .[gmail]
   ```

4. Start the backend (`uvicorn app.main:app --reload`).
5. `GET http://localhost:8000/gmail/status` — confirm `connected: false`.
6. `GET http://localhost:8000/gmail/auth-url` — open the returned
   `auth_url` in a browser.
7. Complete Google consent. The browser will redirect to
   `/gmail/oauth/callback` and a token file will be written.
8. `GET /gmail/status` should now show `connected: true` and the
   connected email.
9. Run a test search:

   ```bash
   curl -X POST http://localhost:8000/gmail/test-search \
     -H 'Content-Type: application/json' \
     -d '{"query":"newer_than:7d","max_results":5}'
   ```

   The response must include only metadata + snippets — no body.

### Known limitations

- The token file holds a refresh token in plain text. Use a dedicated
  Google account for local development if you are concerned.
- There is no automatic background poll yet. Future tasks (poll +
  classifier) will use the same `GmailClient` plumbing.
- No frontend UI is shipped in this task; verification is via
  `curl`/the FastAPI docs page. A future settings-page card is
  on the roadmap.
- The connection is single-account. Multi-account is not modeled.

## Application Email Search (task 083)

Task 083 adds an application-aware Gmail search endpoint on top of the
read-only client from task 082. It **finds and scores** candidate
emails that may relate to a specific application; it **does not**
classify them, mutate the mailbox, or change the application's main
outcome status.

### Scope

- Read-only Gmail use only (still under `gmail.readonly`).
- User-triggered search only. No background polling.
- No send, archive, delete, label, modify, or full-body access.
- No classification of rejections / interviews / offers / etc. — the
  user remains the final reviewer (per ADR-010).
- `Application.status` is never moved to `rejected` / `interview` /
  `offer` / etc. by this endpoint.

### Query builder rules

`backend/app/gmail_application_search.py::build_application_query`
produces the Gmail-search string deterministically from an
``ApplicationQueryInputs`` dataclass. The shape is::

    (<phrase> OR <phrase> ...) <date-clause> [<ats-from-clause>]

Rules (in order):

1. Each of `company`, `job_title`, and any `extra_terms` is wrapped as
   a quoted phrase (`"Example Aero Labs"`). Embedded double quotes are
   stripped because Gmail's parser does not support escaping inside
   quoted phrases.
2. Terms are joined with `OR` so a message matching *any* of them is
   returned. A single term yields no `(...)` wrapper.
3. When `submitted_at` is set the date clause is
   `after:YYYY/M/D`, applied with a one-day pre-submission buffer
   (`SUBMITTED_BUFFER_DAYS = 1`).
4. When `submitted_at` is `None` the date clause falls back to
   `newer_than:180d` (`DEFAULT_NEWER_THAN_DAYS = 180`).
5. When `include_ats_terms` is true, an `OR`-joined `from:` clause for
   the known ATS domain list (`greenhouse.io`, `lever.co`,
   `workday.com`, `myworkdayjobs.com`, `ashbyhq.com`,
   `smartrecruiters.com`, `icims.com`, `bamboohr.com`, `jobvite.com`,
   `recruitee.com`, `successfactors.com`) is appended.
6. The builder never emits stray `()` or trailing `OR` — even when
   every input is null it returns a valid Gmail filter (just the date
   clause + ATS senders).

Example for `Company = "Example Aero Labs"`,
`Title = "Scientific Machine Learning Engineer"`,
`submitted_at = 2026-05-25T03:00:00Z`:

```text
("Example Aero Labs" OR "Scientific Machine Learning Engineer") after:2026/5/24 (from:greenhouse.io OR from:lever.co OR ...)
```

### Matching signals and scoring

`score_candidate(message, MatchInputs)` returns
`(score: float, matched_signals: list[str])`. The match is purely a
substring / domain check on the safe metadata fields — no model is
invoked. Signals (and their additive weights) are:

| Signal | Weight | Triggered when |
|---|---|---|
| `company_name` | 0.45 | company appears in subject / snippet / from |
| `job_title` | 0.35 | job title appears in subject / snippet |
| `company_sender_domain` | 0.20 | sender domain matches the company slug |
| `ats_sender_domain` | 0.15 | sender domain is one of `ATS_DOMAINS` |
| `after_submitted_at` | 0.10 | message date ≥ `submitted_at - 1d` |
| `manual_term` | 0.15 | any `extra_terms` value matches; credited once |

`score` is clamped to `[0.0, 1.0]`. The weights are deliberately
deterministic and explainable; tests pin them so re-tuning is a
contract-visible change.

Candidates are returned newest-best-first (sorted by `match_score`
descending; Python's stable sort preserves Gmail's own newest-first
order on ties).

### API endpoint

```
POST /applications/{application_id}/gmail/search
```

Request body (all fields optional):

```jsonc
{
  "max_results": 10,
  "extra_terms": ["optional phrase"],
  "include_ats_terms": true
}
```

`max_results` is clamped to the smaller of
`MAX_APPLICATION_SEARCH_RESULTS = 25` and
`gmail_client.MAX_TEST_SEARCH_RESULTS = 10` (effective ceiling: 10).

Connected response:

```jsonc
{
  "application_id": "...",
  "gmail_connected": true,
  "gmail_query": "(\"Example Aero Labs\" OR \"Scientific Machine Learning Engineer\") after:2026/5/24 ...",
  "count": 2,
  "candidates": [
    {
      "message_id": "...",
      "thread_id": "...",
      "subject": "...",
      "from": "...",
      "date": "...",
      "snippet": "...",
      "matched_signals": ["company_name", "job_title"],
      "match_score": 0.78
    }
  ]
}
```

Disconnected response (no token, or token lost between status check
and search):

```jsonc
{
  "application_id": "...",
  "gmail_connected": false,
  "gmail_query": null,
  "count": 0,
  "candidates": [],
  "message": "Connect Gmail before searching for application emails"
}
```

The endpoint **does not** trigger OAuth on its own — the user must
visit `/gmail/auth-url` first (the task-082 surface).

### State updates on the application

After a successful search the endpoint persists exactly two summary
fields:

- `Application.last_gmail_check_at` — wall-clock of the search.
- `Application.email_search_state` — the new column added by this
  task; stores `"no_match"`, `"email_received"`, or `"error"`.

`derive_email_status` consults `email_search_state` when no `EmailLink`
rows exist for a submitted application, so the dashboard surfaces
`no_match` / `email_received` immediately after a search runs without
needing the user to attach an `EmailLink` first.

Side-effect rules:

| Outcome | `email_search_state` | `email_status` derivation |
|---|---|---|
| Gmail disconnected | unchanged | unchanged |
| Search OK, zero candidates | `no_match` | `no_match` |
| Search OK, ≥ 1 candidate | `email_received` | `email_received` |
| Search raised an unexpected error | `error` | `error` |

`Application.status` (main outcome) is **never** changed by this
endpoint. The next-action / outcome decision still lives with the
manual `EmailLink` flow (or a future classifier task) so the user
remains the final reviewer.

### Privacy constraints

- Read-only Gmail use only (scope unchanged from task 082).
- No send, archive, delete, label, or modify routes added.
- No background polling; the search is strictly user-triggered.
- Safe metadata only: `id`, `thread_id`, `subject`, `from`, `date`,
  `snippet`. No full bodies, no HTML, no attachments are fetched or
  returned.
- Candidate metadata is **not** persisted to the database — only the
  small summary fields above survive past the response.
- `gmail_query` is included in the response so the user can audit /
  copy the exact query Gmail saw.

### Known limitations

- The match score is purely substring / domain heuristics. It is good
  enough to surface obvious matches and obvious non-matches; the user
  is the final reviewer for ambiguous cases.
- No `EmailLink` rows are written by this endpoint. Linking a
  candidate to the application (and triggering the side-effect rules
  in `application_status.md`) remains a manual / future-task step.
- Multi-account is not modeled; the single connected mailbox from task
  082 is searched.
- Rate-limiting is not implemented; the endpoint is user-triggered and
  capped at `max_results=10` per call, so abuse risk is low for the
  local-first workload.

## Application Email Classification (task 084)

Task 084 adds a deterministic, evidence-based classifier that turns a
candidate email (already returned by the task-083 search endpoint) into
one of the contract-pinned classifier labels and, where appropriate,
into an `EmailLink` row + application status change. It is the first
step that may move `Application.status` based on inbound mail; all
other safety guarantees (read-only Gmail, no send/archive/delete/label,
no full bodies, no background polling) remain in force.

### Scope

- Classifies one candidate at a time via
  `POST /applications/{application_id}/gmail/classify`.
- Pure-Python deterministic phrase matching — no LLM, no network, no
  google libraries imported.
- Uses safe metadata only (`subject`, `from`, `snippet`); the
  classifier dataclass intentionally has no `body`/`html` field so a
  caller cannot leak full content.
- Writes at most one `EmailLink` per call. Re-classifying the same
  `(application_id, gmail_message_id)` is a no-op.
- Surfaces every classification with its evidence; nothing is changed
  silently.

### Deterministic phrase matching

`backend/app/gmail_application_classifier.py` keeps a per-label tuple of
short lower-case phrases. For each candidate, the classifier scans the
lowered `subject`, `snippet`, and `from` fields for substring hits and
records `(field, phrase)` evidence pairs. The phrase tables (shape, not
exact values) live in code:

```python
_PHRASES = {
    "rejection":               ("not moving forward", "will not be moving forward",
                                "decided not to proceed", "not selected",
                                "pursue other candidates", "unable to offer",
                                "position has been filled", "role has been filled",
                                "application was unsuccessful", "we regret to inform",
                                "unfortunately", ...),
    "interview_request":       ("schedule an interview", "schedule a call",
                                "phone screen", "technical interview",
                                "interview availability", "meet with", "next step",
                                "speak with", "chat with our team",
                                "reschedule your interview", ...),
    "assessment":              ("coding challenge", "take-home", "take home",
                                "technical exercise", "assignment", "questionnaire",
                                "hackerrank", "codesignal",
                                "complete the assessment", ...),
    "submission_confirmation": ("application received", "thank you for applying",
                                "we received your application",
                                "your application has been submitted",
                                "successfully submitted", ...),
    "offer":                   ("pleased to offer", "would like to extend",
                                "extend an offer", "selected for the role",
                                "congratulations", "offer letter"),
    "application_update":      ("under review", "reviewing your application",
                                "still reviewing", "update on your application",
                                "we will be in touch", ...),
    "recruiter_followup":      ("wanted to follow up", "following up on your application",
                                "circling back", "checking in", "touching base", ...),
    "newsletter_or_unrelated": ("unsubscribe", "view in browser", "newsletter",
                                "weekly digest", "marketing preferences", ...),
}
```

The classifier never inspects full email bodies and never escalates
beyond substring matching.

### Confidence scoring

Confidence is deterministic — there is no learned component. For the
winning label:

```
confidence = min(_MAX_CONFIDENCE,
                 _BASE_CONFIDENCE + _PER_EVIDENCE_BONUS * (len(evidence) - 1))
```

with `_BASE_CONFIDENCE = 0.55`, `_PER_EVIDENCE_BONUS = 0.18`, and
`_MAX_CONFIDENCE = 0.95`. A single matched phrase already yields the
floor (`0.55`); additional independent hits raise confidence up to the
cap. The numbers are deliberately coarse so a reviewer can see at a
glance how strong a match must be to flip the application's status.

### Precedence rule (ambiguity handling)

When several labels accumulate evidence on the same message, the
winner is chosen by this fixed precedence (highest first):

```
offer
interview_request
assessment
rejection
submission_confirmation
recruiter_followup
application_update
newsletter_or_unrelated
unknown
```

This is what protects against the canonical false-positive
`"Unfortunately, we need to reschedule your interview"`: the word
*unfortunately* hits the rejection table, but
*reschedule your interview* simultaneously hits the
`interview_request` table, and `interview_request` outranks
`rejection`. Tests pin this case so the rule does not regress.

### Evidence format

Every non-`unknown` classification carries an `evidence` array. Each
entry is small on purpose: the field name, a short quote, and a one-line
reason. Quotes are window-trimmed to ≤ 80 characters and centered on the
matched phrase so the user can see *exactly* why a label fired without
the response containing the full email:

```jsonc
{
  "classification": "rejection",
  "confidence": 0.73,
  "evidence": [
    {
      "field": "snippet",
      "text": "…we will not be moving forward with your application.",
      "reason": "contains rejection phrase"
    }
  ],
  "reason": "Matched rejection phrase in email snippet"
}
```

`field` is always one of `subject`, `from`, or `snippet`. Bodies,
HTML, and attachments are never accepted as evidence inputs and never
appear in the response.

### Mapping to EmailLink and application_status

The classifier produces a label from the richer 9-value vocabulary; the
persisted `EmailLink.classified_status` keeps the smaller 5-value set
already pinned by `application_status.md`. The endpoint writes at most
one row using this mapping (re-using the existing `_EMAIL_SIDE_EFFECTS`
rules so terminal-status protection stays in one place):

| Classifier label | `email_status` (response) | `EmailLink.classified_status` (persisted) | `Application.status` target |
|---|---|---|---|
| `submission_confirmation` | `confirmation_found` | `confirmation` | unchanged |
| `rejection` | `classified_rejection` | `rejection` | `rejected` *(unless `withdrawn`)* |
| `interview_request` | `classified_interview` | `next_step` | `interview` *(unless `rejected`/`withdrawn`/`offer`)* |
| `recruiter_followup` | `classified_interview` | `next_step` | `interview` *(same blockers)* |
| `assessment` | `classified_assessment` | `next_step` *(today)* | unchanged main status; `next_action` indicates "Complete assessment" |
| `offer` | `classified_offer` | `offer` | `offer` *(unless `withdrawn`)* |
| `application_update` | `classified_neutral` | `other` | unchanged |
| `newsletter_or_unrelated` | `needs_review` | *(none — no row)* | unchanged |
| `unknown` | `needs_review` | *(none — no row)* | unchanged |

`assessment → next_step` is the same compromise documented in the
"Classification Labels" section above: a future task may split
`assessment` into its own `EmailLink.classified_status` once the
manual-entry UI grows the matching choice. Until then the persisted
`EmailLink` uses `next_step` and the response `email_status` is
`classified_assessment`, which is the value the dashboard should
surface.

`withdrawn` is sticky: the classify endpoint short-circuits to
"persist nothing, propose no status change" when the application is
already `withdrawn`, even if the classifier's evidence is unambiguous.
The response still carries the classifier label / confidence /
evidence so the user sees what was detected.

### API endpoint

```
POST /applications/{application_id}/gmail/classify
```

Request body:

```jsonc
{
  // Required. The same shape returned by the task-083 search endpoint;
  // extra keys are ignored.
  "candidate": {
    "message_id": "...",     // gmail message id
    "thread_id":  "...",
    "subject":    "...",
    "from":       "...",
    "date":       "...",
    "snippet":    "..."
  },
  // Reserved for a future task that persists search candidates.
  // Passing it without ``candidate`` returns 400.
  "message_id": null,
  "classify_top_candidate": false
}
```

Today the project does not persist Gmail search candidates, so the
`message_id` / `classify_top_candidate` short-circuits are not honored
on their own; the frontend (or `curl` user) must hand the candidate
metadata directly to this endpoint. A future task may persist
candidates and lift this restriction without changing the wire shape.

Response:

```jsonc
{
  "application_id": "...",
  "message_id":    "...",
  "classification": "rejection",
  "confidence":    0.73,
  "email_status":  "classified_rejection",
  "application_status": "rejected",
  "application_status_changed": true,
  "email_link_id": "...",
  "evidence": [
    {
      "field":  "snippet",
      "text":   "…we will not be moving forward with your application.",
      "reason": "contains rejection phrase"
    }
  ],
  "reason": "Matched rejection phrase in email snippet"
}
```

`application_status_changed` is `false` when the application was
already in a terminal state (`withdrawn`, `rejected`, etc.) or when the
classifier label does not propose a status change.

### Privacy and safety

- Read-only Gmail scope only — the classifier never opens a Gmail
  connection of its own, the calling endpoint never touches the
  mailbox.
- No send / archive / delete / label / modify routes are added.
- Full email bodies and HTML are never accepted (`CandidateEmail`
  has no field for them) and never persisted; evidence quotes are
  ≤ 80 characters cut from the safe-metadata fields.
- Background polling is not implemented; classification is strictly
  user-triggered.
- Every automatic `Application.status` change is auditable — the
  endpoint reuses the existing `_EMAIL_SIDE_EFFECTS` rules which
  append an `ApplicationEvent` for every state transition.
- Confidence below the floor downgrades the classification to
  `unknown` with `needs_review` so the user reviews uncertain matches
  before any status change.

### Known limitations

- The classifier inspects only `subject`, `from`, and `snippet`. Gmail's
  snippet is itself short (~200 chars) and may not contain the
  decisive phrase for every email; the dashboard should display the
  candidate's metadata + classifier verdict + an "open in Gmail" link
  rather than pretending the snippet is the whole message.
- The phrase tables are intentionally narrow. They will miss legitimate
  signals expressed in unusual phrasing; the user remains the final
  reviewer.
- No bulk-classify endpoint is shipped in this task. The classify route
  takes one candidate at a time; a future task may add a bulk variant
  if needed.
- An optional LLM-assisted backstop is documented but not implemented;
  any future LLM step must keep the deterministic phrase matcher as
  the *primary* signal so behavior remains explainable.

## Frontend Gmail Evidence UI (task 085)

Task 085 wires the Gmail tracking surface above into the React UI. It
does **not** add any new backend endpoint, change classification logic,
or grow the privacy surface — it only renders the existing read-only
data and re-uses the task-082/083/084 endpoints exactly as documented.

### User actions surfaced in the UI

The Applications detail page (`frontend/src/components/GmailEvidence.tsx`)
exposes exactly these actions. All of them call existing endpoints; no
new write-side surface is introduced.

| UI action | Endpoint called | Purpose |
|---|---|---|
| Connect Gmail | `GET /gmail/auth-url` | Opens the returned `auth_url` in a new tab so the user can complete OAuth. |
| Check Gmail | `POST /applications/{id}/gmail/search` | Triggers the task-083 search. After the response the page re-fetches the application so `email_status` / `last_gmail_check_at` reflect the persisted summary. |
| Classify | `POST /applications/{id}/gmail/classify` | Sends one candidate's safe metadata. After the response the page re-fetches the application so `Application.status` and the dashboard reflect any side-effect change. |

The previous send/archive/delete/label hazards are still absent: there
is no button, link, or hidden affordance for any write-side Gmail
operation anywhere in the UI.

### Displayed fields

The detail-page Gmail card renders these read-only fields when
available, sourced from `ApplicationRead` (existing wire format — no
new fields are added):

```
email_status              → mapped to a human label via
                            ``emailStatusLabel`` (see
                            ``frontend/src/lib/workflow.ts``).
matched_email_count       → "N emails" decoration in the list row.
latest_email_subject      → "Latest email" line.
latest_email_from         → "from <sender>" continuation.
latest_email_classification → "Latest classification" line, via
                              ``classificationLabel``.
latest_email_confidence   → "confidence 0.NN" continuation.
latest_email_evidence     → "Latest evidence" line (reserved / null
                            today; the wire format already exists so
                            the UI is forward-compatible).
last_gmail_check_at       → "Checked: N minutes ago".
```

Each candidate returned by `POST /applications/{id}/gmail/search` is
rendered as a compact card showing **subject, sender, date, snippet,
matched signals, match score, and a Classify button**. Full bodies,
HTML, and attachments are never requested or rendered — the
`GmailCandidateEmail` TypeScript type intentionally has no `body` /
`html` field so a future regression cannot smuggle full content into
the UI surface.

After classification, the result panel renders:

```
Classification: <label>      (explicit text, not color-only)
Confidence: 86%
Reason: <one-line reason from the classifier>
Evidence:
  - <field>: "<quoted ≤80-char snippet>"
"Application status updated to <new status>." (only when the backend
                                                 reports
                                                 application_status_changed)
```

### Manual review behavior

When the classifier returns `unknown` or
`newsletter_or_unrelated` the response carries
`email_status = "needs_review"` and no `EmailLink` row is persisted by
the backend. The UI renders the label *Needs review* / *Unrelated*
explicitly (text label, not color) so the user knows they remain the
final reviewer. No automatic `Application.status` change happens for
those labels — this matches the manual-review safety rule from the
*Privacy and Safety Rules* section above.

### Privacy note in the UI

The Gmail card renders a short, always-visible note:

> Gmail is used read-only for application tracking. JobApplicator does
> not send, delete, archive, or label emails.

This text is a UI mirror of the contract's *Privacy and Safety Rules*
list and exists so a non-technical reviewer can see the safety scope
without reading this document. The note is rendered above the
action buttons so it is on screen whenever the user is about to
trigger any Gmail call.

### Accessibility / label-only display

The classification result, the candidate signals, and the status line
all render their meaning as **explicit text** (e.g. "Classification:
Rejection" rather than a red dot). Color is only used as a decoration
on the timeline-stage badge in the applications list, which already
has a text label. This keeps the surface usable for screen readers and
keeps the per-application story understandable without color.

### Error surfaces

`GmailEvidence` renders an inline alert (`role="alert"`) when any of
these conditions occur, so the user gets a useful message without the
UI crashing:

| Condition | Message |
|---|---|
| Gmail not connected during search | "Connect Gmail before searching for application emails." (forwarded from the backend response) |
| `GET /gmail/auth-url` failure | "Could not get Gmail auth URL. Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on the backend first." |
| Search fails | Forwarded `ApiError` message (e.g. "Request to /applications/X/gmail/search failed with status 500"). |
| Classification fails | Forwarded `ApiError` message or "Could not classify this email. Try again or review manually." |

## Manual Application Sync (task 086)

Task 086 adds a higher-level workflow on top of the task-083 search and
task-084 classify endpoints: a single user-triggered action that walks
every relevant application, runs a Gmail search, classifies the top
candidate, and returns a summary. It is **strictly manual** — there is
still no background polling, no scheduled job, and no listener.

### Scope

- Read-only Gmail use only (`gmail.readonly` scope, unchanged).
- User-triggered only — every call originates from a button press on the
  Applications page or a direct `curl` request. No background polling,
  no cron, no listeners.
- No send, archive, delete, label, modify, draft, or reply routes are
  added.
- Safe metadata only — the same `subject` / `from` / `date` / `snippet`
  surface as the task-083/084 endpoints. Full bodies, HTML, and
  attachments are never fetched, returned, or persisted.
- Every status change carries evidence; uncertain matches land in
  `needs_review` and do not auto-change the application's main status.

### Endpoint

```
POST /gmail/sync-applications
```

Request body (every field optional, sensible defaults applied):

```jsonc
{
  "max_applications": 25,
  "max_results_per_application": 10,
  "classify": true,
  "include_terminal": false
}
```

Connected response shape:

```jsonc
{
  "gmail_connected": true,
  "checked_count": 5,
  "updated_count": 2,
  "no_match_count": 3,
  "needs_review_count": 1,
  "results": [
    {
      "application_id": "...",
      "job_title": "...",
      "company": "...",
      "previous_email_status": "watching",
      "new_email_status": "classified_rejection",
      "previous_application_status": "submitted",
      "new_application_status": "rejected",
      "matched_email_count": 1,
      "classification": "rejection",
      "confidence": 0.86,
      "evidence": [
        {
          "field": "snippet",
          "text": "…not moving forward…",
          "reason": "contains rejection phrase"
        }
      ],
      "application_status_changed": true,
      "gmail_query": "(\"…\") after:2026/5/24 …",
      "skipped_reason": null
    }
  ]
}
```

Disconnected response (no stored token, or token lost between status
check and search):

```jsonc
{
  "gmail_connected": false,
  "checked_count": 0,
  "updated_count": 0,
  "no_match_count": 0,
  "needs_review_count": 0,
  "results": [],
  "message": "Connect Gmail before syncing applications"
}
```

The endpoint never starts OAuth on its own — the user visits
`/gmail/auth-url` first (the task-082 surface) and the response message
nudges them back to it.

### Included / excluded application statuses

The sync intentionally skips applications that cannot meaningfully
benefit from a Gmail check (pre-submission drafts, closed lanes).

| `Application.status` | Default sync | `include_terminal=true` |
|---|---|---|
| `draft` | excluded | excluded |
| `generated` | excluded | excluded |
| `approved` | excluded | excluded |
| `submitted` | **included** | **included** |
| `response_received` | **included** | **included** |
| `interview` | **included** | **included** |
| `rejected` | excluded | **included** |
| `offer` | excluded | **included** |
| `withdrawn` | **excluded** | **excluded** *(always)* |

`withdrawn` is the only status that the sync **never** touches —
regardless of `include_terminal`. The endpoint's per-application loop
also short-circuits with `skipped_reason = "withdrawn"` as a defensive
double-check so a future filter change cannot accidentally auto-change
a withdrawn application.

`approved` (the project's "ready to submit" lane) is excluded today
because the project has no signal that the user is actively watching it
for inbound mail yet. A future task can opt it in once an explicit
"watching" flag exists.

### Per-application behavior

For each included application:

1. Build the Gmail-search query with the task-083 query builder
   (`build_application_query`).
2. Search Gmail (read-only) via `gmail_client.search_messages`.
3. Update `Application.last_gmail_check_at` and `email_search_state`:
   - `email_search_state = "no_match"` when the result list is empty.
   - `email_search_state = "email_received"` when at least one candidate
     comes back.
4. If `classify=true` and there is at least one candidate, classify the
   top-scoring candidate (highest match score, Gmail's newest-first
   order as the stable tiebreak) via the task-084 classifier.
5. When the classifier maps to a persisted
   `EmailLink.classified_status`, write the EmailLink using the
   existing `_EMAIL_SIDE_EFFECTS` rules in `application_status.md`. The
   side-effect rules are the single source of truth for status
   transitions — `withdrawn` stays sticky, `rejected`/`offer` block
   `next_step`, and so on.
6. Record `result.evidence` (the matched phrase quote) on the response.
   No full bodies, no HTML, no attachments.

`classify=false` leaves the application's main status untouched and
writes no EmailLink rows; the response still includes the candidate
count so the user can see which applications had matches.

### Rate / cap rules

| Field | Default | Hard cap | Behavior above cap |
|---|---|---|---|
| `max_applications` | 25 | 50 | Request returns 422 |
| `max_results_per_application` | 10 | 10 | Request returns 422 |

The schema layer rejects values above the cap instead of silently
clamping so the user sees a clear error. The per-application loop also
caps the result count to the smallest of `MAX_APPLICATION_SEARCH_RESULTS`
(25, from task 083) and `gmail_client.MAX_TEST_SEARCH_RESULTS` (10, from
task 082); the effective per-application ceiling is therefore 10.

Applications are processed in deterministic order by
`Application.updated_at` (descending) so the most recently active
applications are processed first.

### Result summary format

`checked_count` is `len(results)` — the number of applications the sync
actually touched. `updated_count` counts results where the
`email_status` *or* the main `application_status` changed; `no_match_count`
counts the empty-search outcome; `needs_review_count` counts results
whose classifier output mapped to `needs_review` (today: `unknown` and
`newsletter_or_unrelated`). Per-application `results` rows carry the
job/company labels so the dashboard can render
`"<Company> — <verdict>"` lines with the matching evidence quote.

### Frontend surface

The Applications page (`frontend/src/pages/ApplicationsPage.tsx`)
exposes one new action: a **Sync Gmail** button at the top of the page.
Clicking it:

1. Calls `POST /gmail/sync-applications` with the defaults above.
2. Renders the loading affordance ("Syncing Gmail…") while the request
   is in flight.
3. On success, renders the summary line plus a per-application list of
   verdicts + evidence quotes.
4. Triggers a `listApplications()` refresh so derived fields
   (`email_status`, `last_gmail_check_at`, `latest_email_*`) reflect
   the persisted side-effects.
5. When the backend reports `gmail_connected=false`, renders the
   inline "Connect Gmail before syncing applications" message.

There is no per-row "sync just this one" action in this task —
per-application search/classify already exists on the detail page.

### Privacy and safety constraints

- **Read-only Gmail use only.** The sync uses the same
  `gmail.readonly` scope as task 082; no write scope is ever
  requested.
- **No send, archive, delete, label, modify, draft, or reply routes
  are added.** A safety test enumerates the FastAPI routes and rejects
  any path that contains one of those tokens.
- **User-triggered only.** No background polling, scheduler, or
  listener exists. The route fires exactly once per button press.
- **Safe metadata only.** The classifier inspects
  `subject` / `from` / `snippet`; full bodies and HTML are never
  accepted or persisted. Tests verify that even when the (mocked)
  Gmail client returns a `body` field the sync route never leaks it
  into the response or the persisted EmailLink.
- **Evidence is required.** Every classifier-driven status change ships
  with the matched phrase quote so the user can audit it. No silent
  transitions.
- **`withdrawn` is sticky.** The sync excludes withdrawn applications
  entirely and never moves them to a different status.

### Why background polling is deferred

A background poll would have to manage rate limits, retries,
fail-quiet behavior, OAuth-refresh edge cases, and a quiet-hours
schedule that respects the user's mail volume. Shipping a manual sync
first lets the user drive the cadence, confirms the search+classify
pipeline behaves on real mail, and gives the project a baseline for
the latency/quota budget a polling job would need. A future task can
lift the manual button into a scheduler once the manual flow has
proven stable on representative mail.

### Known limitations

- Single-account; the connected mailbox from task 082 is searched.
- The classifier is the same deterministic phrase matcher as task 084
  — it will miss legitimate signals expressed in unusual phrasing.
- Only the top candidate per application is classified. A future task
  may classify the top-N candidates if real-world traffic shows the
  highest-scoring candidate is the wrong one too often.
- No bulk "Sync N applications now" affordance beyond the single
  button. Adjusting `max_applications` requires a request override
  (curl / a future settings field).

## Settings-Owned Connection + Actionable Config Errors (task 087)

Task 087 moves the Gmail connect/disconnect affordance into the
Settings page and replaces the generic
`Request to /gmail/auth-url failed with status 400` error with an
actionable, structured response. The privacy / scope rules above are
unchanged.

### UI placement

| Surface | Affordance |
|---|---|
| Settings → Gmail integration card | "Connect Gmail" (when configured but no token), connection status, privacy note, listing of any `missing_config` env vars |
| Applications page | "Sync Gmail" button; an inline hint that links to Settings when Gmail is not configured/connected |
| Application detail / `GmailEvidence` | "Check Gmail" for that application (only when connected); an inline hint linking to Settings when Gmail is not configured/connected. **Never** a "Connect Gmail" button, and **never** a direct call to `/gmail/auth-url` |

The single source of truth for the OAuth handshake is the Settings page.
Application cards and the application detail must not call
`/gmail/auth-url` and must not surface their own Connect Gmail button.

### `/gmail/status` shape

`/gmail/status` carries two extra fields so the UI can render
not-configured / configured / connected without separately probing the
backend env vars:

```jsonc
{
  "connected": false,
  "configured": false,
  "missing_config": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"],
  "email": null,
  "scopes": [],
  "token_path_configured": true,
  "last_checked_at": null
}
```

`configured` is `true` iff both `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` are set. `missing_config` is empty when
`configured` is true; otherwise it lists every unset env var among
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`
(the redirect URI has a default but is included in the install-time
trio so the UI can name what to set).

### `/gmail/auth-url` structured error

When the OAuth credentials are missing, `/gmail/auth-url` returns
`HTTP 400` with a JSON `detail` object instead of a bare string:

```jsonc
{
  "detail": {
    "error": "gmail_oauth_not_configured",
    "message": "Gmail OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI.",
    "missing": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"]
  }
}
```

The frontend's `extractApiDetail` helper renders `detail.message`
verbatim so the user sees, e.g.:

> Gmail OAuth is not configured. Set GOOGLE_CLIENT_ID,
> GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI.

To clear the error, either save the Gmail OAuth config in Settings
(see task 088 below) or set the listed environment variables and
restart the backend.

## Settings-Stored OAuth Configuration (task 088)

Task 088 lets the user save the Gmail OAuth config from the Settings
page so the env-var-and-restart loop is no longer required for local
use. Privacy / scope rules above are unchanged: read-only scope only,
no send/archive/delete/label/modify, no full bodies, no background
polling.

### Resolution priority

`gmail_client.get_gmail_config()` resolves the active config from, in
order:

```
1. Settings-stored Gmail OAuth config (app.gmail_settings)
2. Environment variables (GOOGLE_CLIENT_ID etc.)
3. Built-in defaults for non-secret fields
```

Env vars remain a fully supported fallback for CI / deployment /
power users. When both layers supply credentials the Settings-stored
config wins; the env vars are not consulted further until the
Settings-stored row is deleted.

### Storage and secret handling

The Settings-stored config is a JSON blob in the existing
`app_settings` key/value table (ADR-009), keyed by
`gmail_oauth_config`. The blob shape:

```jsonc
{
  "google_client_id": "<client id>",
  "google_client_secret": "<client secret>",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json",
  "updated_at": "2026-05-26T12:00:00+00:00"
}
```

Safety rules:

- The DB file is local-machine state and is gitignored.
- The plaintext `google_client_secret` is never returned by any GET
  endpoint, never logged, and never rendered in the UI after save.
- GET / response shapes return `has_google_client_secret: true` and a
  masked `google_client_secret_preview` of `••••••••`.
- The `.gitignore` also lists
  `candidate_context/settings/gmail_oauth.json` and
  `candidate_context/settings/*.secret.json` defensively so a future
  file-based storage choice cannot accidentally commit a secret.

### Backend endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/settings/gmail-oauth` | Sanitized snapshot of the effective config (`source` ∈ `settings` / `environment` / `none`). |
| PUT | `/settings/gmail-oauth` | Save / overwrite the Settings-stored config. |
| DELETE | `/settings/gmail-oauth` | Remove the Settings-stored config (the OAuth token file is **not** deleted). |

Sanitized GET response when settings own the config:

```jsonc
{
  "configured": true,
  "source": "settings",
  "google_client_id": "123456789-abc.apps.googleusercontent.com",
  "has_google_client_secret": true,
  "google_client_secret_preview": "••••••••",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json",
  "updated_at": "2026-05-26T12:00:00+00:00"
}
```

When the env-var fallback is in effect, `source: "environment"`,
`google_client_secret_preview: "from environment"`, and `updated_at`
is `null`. When nothing is configured at all, `configured: false`,
`source: "none"`, and `has_google_client_secret: false`.

PUT request body:

```jsonc
{
  "google_client_id": "...",
  "google_client_secret": "...",
  "google_redirect_uri": "http://localhost:8000/gmail/oauth/callback",
  "gmail_token_path": "candidate_context/gmail/token.json",
  "preserve_existing_secret": false
}
```

Validation:

- `google_client_id` is required.
- `google_client_secret` is required unless
  `preserve_existing_secret` is `true` and a saved secret already
  exists for the user.
- `google_redirect_uri` is required (defaulted in the UI to
  `http://localhost:8000/gmail/oauth/callback`).
- `gmail_token_path` is optional; defaults to
  `candidate_context/gmail/token.json`.

The request body is never logged in full — the persistence helper
exists so the secret value is the only field that needs special
handling, and it is written straight into the AppSetting row.

### Hot-reload behavior

`/gmail/status`, `/gmail/auth-url`, `/gmail/oauth/callback`, and
`/gmail/test-search` all call `gmail_client.get_gmail_config()` on
every request, so saving config in Settings clears the
`gmail_oauth_not_configured` error without a backend restart. The
Settings card immediately shows **Not connected** (or **Connected**
if a previous token survives the config change).

### Settings UI summary

The Gmail integration card on the Settings page renders:

- The current status (Not configured / Not connected / Connected).
- A config-source label ("Local settings" / "Environment variables"
  / "Not configured").
- A form for entering Google Client ID, Client Secret, Redirect URI,
  and Token Path. The form is shown automatically when nothing is
  configured and can be re-opened via **Edit Gmail config** (or
  **Override with local settings** when env-loaded).
- A **Connect Gmail** button once credentials are present.
- A **Delete local Gmail config** button when the Settings row exists.

The plaintext client secret is never rendered after save — the input
shows a `••••••••` placeholder, and the masked field is purely
visual. When env vars are the active source the card displays a
short note explaining this and offering an override path.
