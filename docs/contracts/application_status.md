# Application Status Timeline and Email Links Contract

This document is the API contract for the application-status timeline and
the `EmailLink` surface that backs it. It pins the field names, endpoint
shapes, and side-effect rules that the backend (task 071) and the
frontend (tasks 072 and 073) must agree on so the data shape does not
drift between sides.

The design decisions behind this contract — including the rationale for a
derived timeline, the choice of canonical `classified_status` values, and
the explicit deferral of Gmail integration — are captured in
[ADR-010: Application Status Timeline and Gmail Integration
Boundary](../adr/010-application-status-timeline.md). This contract
restates only the API-visible rules. Where this contract and ADR-010
overlap, ADR-010 supplies the reasoning and this contract supplies the
exact strings, fields, and side effects.

## Status Vocabulary

### `Application.status`

`Application.status` is a stable, lowercase string. The current allowed
values mirror `APPLICATION_STATUSES` in `backend/app/models.py`:

```
draft
generated
approved
submitted
response_received
rejected
interview
offer
withdrawn
```

The database stores this column as TEXT. The values are stable strings,
not a SQL enum, following the existing convention in
`backend/app/models.py` (see also `CLAUDE_RUN_STATUSES` and
`REVISION_FEEDBACK_STATUSES`). Adding a new status is therefore a code
change only and requires no migration.

### `EmailLink.classified_status`

The canonical values for `EmailLink.classified_status` are fixed by
ADR-010:

```
confirmation
rejection
next_step
offer
other
```

The database stores this column as TEXT and it is nullable: a recorded
email without a classification is still a valid row. As with
`Application.status`, the values are stable strings, not a SQL enum.

Per ADR-010, `confidence` is reserved for a future automated classifier
and is unused today. Manual entries leave it null.

## Derived Timeline Stages

The application timeline is a **derivation**, not a stored column. The
inputs are `Application.status`, `Application.submitted_at`, and the
attached `EmailLink` rows. ADR-010 explains why this is computed rather
than stored.

The derived stages, in chronological order, are:

```
draft
sent
confirmation_received
response_received
rejected
interview
offer
withdrawn
```

### Derivation rule

The backend computes the timeline stage by applying the following rules
in order. The first rule whose condition is true wins; later rules do
not fire.

1. If `Application.status == "withdrawn"` → `withdrawn`. (Withdrawal is
   sticky and takes precedence over any email evidence.)
2. Else if `Application.status == "offer"` → `offer`.
3. Else if `Application.status == "rejected"` → `rejected`.
4. Else if `Application.status == "interview"` → `interview`.
5. Else if `Application.status == "response_received"` →
   `response_received`.
6. Else if `Application.status == "submitted"` (or `submitted_at` is
   set):
   - if any attached `EmailLink` has
     `classified_status == "confirmation"` and no attached `EmailLink`
     has `classified_status in {"rejection", "next_step", "offer"}` →
     `confirmation_received`.
   - else → `sent`.
7. Else (`Application.status in {"draft", "generated", "approved"}` and
   `submitted_at is null`) → `draft`.

### Precedence summary

- `Application.status` outranks email evidence for terminal-ish values
  (`withdrawn`, `offer`, `rejected`, `interview`,
  `response_received`). A user who manually overrides
  `Application.status` wins over any email signal already attached.
- Email evidence only refines the stage between `sent` and
  `confirmation_received`. It never demotes a higher stage.
- A `confirmation` email does not advance the stage past
  `confirmation_received`; only a non-confirmation signal does, and
  that signal advances `Application.status` itself (see *Side
  effects* below) which then carries the stage.

### Server-side, returned on `ApplicationRead`

The timeline stage is **computed server-side** and returned as a string
field (`timeline_stage`, see below) on every `ApplicationRead`. Clients
must not re-derive the stage from the underlying `status`,
`submitted_at`, and `EmailLink` fields. Treating the server as the sole
deriver keeps the backend and frontend in sync even if the rule set
evolves.

## `ApplicationRead` Shape Extensions

`ApplicationRead` keeps its existing fields and adds the following three
fields. The names below are fixed by this contract; tasks 071, 072, and
073 must use them as-is.

| Field             | Type                  | Description |
|-------------------|-----------------------|-------------|
| `timeline_stage`  | `string`              | One of the derived stages listed above. Always present. Computed server-side per the derivation rule. |
| `last_email_link` | `EmailLinkRead \| null` | The most recently received attached email link, or `null` when no email links are attached. Ordering: `received_at` desc, then `created_at` desc. A row with `received_at is null` sorts after any row with a non-null `received_at` (i.e. real timestamps win), and ties break on `created_at` desc. |
| `email_link_count`| `integer`             | Total number of `EmailLink` rows attached to this application. `0` when none. |

These are read-only response fields. They are not accepted on
`ApplicationCreate` or on any application-update path.

## `EmailLinkRead` Shape

`EmailLinkRead` is a new response schema introduced by this contract.
Its fields are fixed here:

| Field                | Type                  | Description |
|----------------------|-----------------------|-------------|
| `id`                 | `string`              | Server-assigned UUID. |
| `application_id`     | `string`              | UUID of the parent `Application`. |
| `gmail_message_id`   | `string`              | Real Gmail message id, or a `manual:<uuid>` placeholder per ADR-010. Always non-null. |
| `gmail_thread_id`    | `string \| null`      | Real Gmail thread id, or `null` for manual entries with no thread context. |
| `subject`            | `string \| null`      | Email subject line. |
| `sender`             | `string \| null`      | Email `From` value (display name and/or address). |
| `received_at`        | `string \| null` (ISO-8601 datetime) | Timestamp the email was received. May be `null` for manual entries with no known time. |
| `classified_status`  | `string \| null`      | One of the canonical values listed above, or `null` for an unlabeled record. |
| `confidence`         | `float \| null`       | Reserved for a future classifier; `null` for manual entries. |
| `created_at`         | `string` (ISO-8601 datetime) | Server-assigned row creation timestamp. Always present. |

## EmailLink Endpoints

The contract pins URL, HTTP method, request body, response body,
response status code, and idempotency expectations for the two new
endpoints. Both endpoints are scoped under the parent application.

### Create an EmailLink

```
POST /applications/{application_id}/email-links
```

Request body (JSON):

| Field               | Type                  | Required | Notes |
|---------------------|-----------------------|----------|-------|
| `gmail_message_id`  | `string`              | yes      | Real Gmail message id, or `manual:<uuid>` for hand-entered rows per ADR-010. |
| `gmail_thread_id`   | `string \| null`      | no       | Optional; defaults to `null`. |
| `subject`           | `string \| null`      | no       | Optional. |
| `sender`            | `string \| null`      | no       | Optional. |
| `received_at`       | `string \| null` (ISO-8601) | no | Optional. |
| `classified_status` | `string`              | yes      | One of the canonical values (`confirmation`, `rejection`, `next_step`, `offer`, `other`). |
| `confidence`        | `float \| null`       | no       | Optional; `null` for manual entries. |

Response: `EmailLinkRead`.

Response status: `201 Created`.

Error responses follow existing router conventions: `404 Not Found`
when `application_id` does not exist; `422 Unprocessable Entity` when
`classified_status` is not in the canonical set or when
`gmail_message_id` is missing.

Idempotency: creation is **not** idempotent at the protocol level — two
successive POSTs with identical bodies produce two rows. Callers that
need to avoid duplicate manual entries are responsible for not
re-posting. (A future Gmail integration ADR will tighten this with a
real uniqueness rule on `gmail_message_id`.)

### List EmailLinks for an application

```
GET /applications/{application_id}/email-links
```

Response: `list[EmailLinkRead]`.

Response status: `200 OK`. Returns `[]` when the application has no
attached email links.

Ordering: `received_at` desc, then `created_at` desc. Rows with
`received_at is null` sort after rows with a non-null `received_at`;
ties break on `created_at` desc. This matches the ordering used to pick
`ApplicationRead.last_email_link`, so the first element of this list
equals `last_email_link` when the list is non-empty.

Error responses: `404 Not Found` when `application_id` does not exist.

## Side Effects When an EmailLink Is Created

Creating an `EmailLink` may transition `Application.status` and always
appends an `ApplicationEvent`. These rules run **only** when a new
`EmailLink` row is inserted (via the `POST` endpoint above). They do
not fire on a list/read operation and they do not fire on a later
re-derivation. A direct manual update of `Application.status` through
the existing applications router is unaffected by these rules and
always wins.

For each `classified_status` value the backend must apply:

### `confirmation`

- `Application.status`: **no change.** Confirmations acknowledge that
  the employer's intake system received the submission and do not
  reflect any decision.
- Append an `ApplicationEvent` with:
  - `event_type = "email_confirmation_received"`
  - `source = "email"`

### `rejection`

- `Application.status`: set to `"rejected"` **unless** the application
  is already `withdrawn`. In the `withdrawn` case, leave the status
  unchanged.
- Append an `ApplicationEvent` with:
  - `event_type = "email_rejection_received"`
  - `source = "email"`

### `next_step`

- `Application.status`: set to `"interview"` **unless** the application
  is already `rejected`, `withdrawn`, or `offer`. In those cases, leave
  the status unchanged.
- Append an `ApplicationEvent` with:
  - `event_type = "email_next_step_received"`
  - `source = "email"`

### `offer`

- `Application.status`: set to `"offer"` **unless** the application is
  already `withdrawn`. In the `withdrawn` case, leave the status
  unchanged.
- Append an `ApplicationEvent` with:
  - `event_type = "email_offer_received"`
  - `source = "email"`

### `other`

- `Application.status`: **no change.** The row is still attached and
  is visible in subsequent reads of the timeline; the user may advance
  status manually if they choose.
- Append an `ApplicationEvent` with:
  - `event_type = "email_other_received"`
  - `source = "email"`

### `null` (no classification supplied)

A `classified_status` of `null` is rejected at the create endpoint
(see request body table above). It is therefore not a case the side-
effect rules need to handle. Rows that already exist in the database
with `classified_status is null` (a legacy case) cause no
status transitions and no event row at create-time, since no create
ever produced them.

### Always-true invariants

- Every successful create produces **exactly one** `ApplicationEvent`
  row, with `source = "email"` and an `event_type` matching the table
  above. The event is written in the same transaction as the
  `EmailLink` row.
- The `ApplicationEvent` row is written **even when** the status did
  not change (e.g. a `rejection` email arriving against a `withdrawn`
  application), so the user can audit that an email was attached and
  why no status changed.
- The `ApplicationEvent` row records the email-driven transition only;
  no separate event is appended for the underlying status change.

## Gmail Integration Boundary

Gmail-driven creation of `EmailLink` rows is **out of scope** for this
contract. Per ADR-010, the first MVP has no Gmail credential model, no
polling, no server-side classification, no automatic
thread-to-application matching, and no outbound Gmail actions.

The endpoints defined above are intentionally usable from two callers:

- a future Gmail integration that posts real Gmail message ids,
  thread ids, and classifier-produced `classified_status` / `confidence`
  values; and
- the manual-entry UI shipping today (tasks 072 / 073), which posts a
  `manual:<uuid>` placeholder for `gmail_message_id`, leaves
  `gmail_thread_id` and `confidence` null, and supplies a
  user-chosen `classified_status`.

A future ADR will cover the Gmail integration itself (credentials,
polling, dedupe, classification, thread matching, and any Gmail-side
writes). That ADR is expected to plug into the same endpoint and the
same `classified_status` vocabulary without changing this contract.

See ADR-010 for the full rationale, including why the timeline is a
derivation rather than a column, why the `classified_status` vocabulary
is fixed up front, why `confirmation` does not advance status, why
`next_step` maps to `interview`, and why the `manual:<uuid>` namespace
exists.
