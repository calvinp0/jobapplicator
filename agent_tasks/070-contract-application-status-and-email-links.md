# Task 070: Contract for application status timeline and email links

Task ID: `070-contract-application-status-and-email-links`

## Goal

Add a new contract document, `docs/contracts/application_status.md`,
that pins down the API surface for the timeline + email-link work
decided in ADR-010. The backend (task 071) and frontend (tasks 072 and
073) will share this contract so the data shape does not drift between
sides.

## Background

Read first:

- `docs/adr/010-application-status-timeline.md` (lands in task 069)
- `docs/contracts/agent_orchestration.md` (style and tone for our
  contract documents)
- `docs/contracts/claude_run_directory.md` (precedent for how a
  contract enumerates fields and rules)
- `backend/app/models.py` (`Application`, `ApplicationEvent`,
  `EmailLink`, `APPLICATION_STATUSES`)
- `backend/app/schemas.py` (`ApplicationRead`, `ApplicationEventRead`)
- `backend/app/routers/applications.py`

## Scope

Create `docs/contracts/application_status.md`. It must contain, at
minimum:

- **Status vocabulary**:
  - The set of `Application.status` values currently allowed
    (mirroring `APPLICATION_STATUSES` in `models.py`).
  - The canonical set of `EmailLink.classified_status` values
    (`confirmation`, `rejection`, `next_step`, `offer`, `other`) from
    ADR-010.
  - A clear note that the database stores both as TEXT and the values
    are stable strings, not enums.

- **Derived timeline stages**:
  - The stage list from ADR-010 (`draft`, `sent`,
    `confirmation_received`, `response_received`, `rejected`,
    `interview`, `offer`, `withdrawn`).
  - The exact derivation rule the backend must apply when computing
    each stage from `(status, submitted_at, email_links)`. Where
    multiple signals could match, the rule must define precedence.
  - A statement that the timeline is computed server-side and
    returned as a string field on `ApplicationRead`
    (e.g. `timeline_stage`). Clients must not re-derive it.

- **`ApplicationRead` shape extensions** (the contract owns the field
  names so task 071 and tasks 072/073 agree):
  - `timeline_stage: string` — one of the derived stage values.
  - `last_email_link: EmailLinkRead | null` — most recent attached
    email link (by `received_at` desc, then `created_at` desc).
  - `email_link_count: integer` — total attached email links.

- **`EmailLinkRead` shape** (new schema, name and fields fixed by this
  contract):
  - `id`
  - `application_id`
  - `gmail_message_id`
  - `gmail_thread_id`
  - `subject`
  - `sender`
  - `received_at`
  - `classified_status`
  - `confidence`
  - `created_at`

- **EmailLink endpoints** (the contract pins URL, method, request
  body, response, idempotency):
  - `POST /applications/{application_id}/email-links` — create an
    EmailLink. Request body fields:
    - `gmail_message_id` (required; may be `manual:<uuid>` for
      hand-entered rows per ADR-010),
    - `gmail_thread_id` (optional),
    - `subject` (optional),
    - `sender` (optional),
    - `received_at` (optional ISO-8601),
    - `classified_status` (required; one of the canonical values),
    - `confidence` (optional float).
    Response: `EmailLinkRead` with 201.
  - `GET /applications/{application_id}/email-links` — list email
    links for the application, ordered by `received_at` desc then
    `created_at` desc. Response: `list[EmailLinkRead]` with 200.

- **Side effects when an EmailLink is created**: the rules from
  ADR-010, restated in contract form, for how
  `Application.status` and `ApplicationEvent` rows must change for
  each `classified_status`. The contract must spell out:
  - `confirmation` → no status change; append an `ApplicationEvent`
    with `event_type="email_confirmation_received"` and
    `source="email"`.
  - `rejection` → set `Application.status = "rejected"` unless the
    application is already `withdrawn`; append an `ApplicationEvent`
    with `event_type="email_rejection_received"` and
    `source="email"`.
  - `next_step` → set `Application.status = "interview"` unless the
    application is already `rejected`, `withdrawn`, or `offer`;
    append `event_type="email_next_step_received"`,
    `source="email"`.
  - `offer` → set `Application.status = "offer"` unless `withdrawn`;
    append `event_type="email_offer_received"`, `source="email"`.
  - `other` → no status change; append
    `event_type="email_other_received"`, `source="email"`.

- **Gmail integration boundary**: a short subsection noting that
  Gmail-driven creation of EmailLink rows is out of scope; the
  endpoint is intentionally usable both manually (today) and by a
  future Gmail integration without contract changes. Reference
  ADR-010.

The contract MUST cross-reference ADR-010 by id and must not
duplicate ADR-010's prose — link, do not copy.

## Allowed files

```
docs/contracts/application_status.md
agent_tasks/070-contract-application-status-and-email-links.md
agent_tasks/queue.yaml
```

## Forbidden files

```
backend/**
frontend/**
extension/**
runtime_prompts/**
candidate_context/**
runs/**
docs/adr/**
docs/contracts/agent_orchestration.md
docs/contracts/browser_extension_capture.md
docs/contracts/claude_run_directory.md
docs/product_requirements.md
docs/architecture.md
```

## Out of scope

- Backend implementation (task 071).
- Frontend implementation (tasks 072 and 073).
- Any Gmail API, MCP, or polling design.
- Changes to existing contract files.

## Acceptance criteria

- `docs/contracts/application_status.md` exists.
- It enumerates all canonical `EmailLink.classified_status` values and
  cites ADR-010.
- It enumerates all derived timeline stages and the derivation rule.
- It names every new field added to `ApplicationRead`
  (`timeline_stage`, `last_email_link`, `email_link_count`) and every
  field on `EmailLinkRead`.
- It specifies the two new endpoints, their request/response shapes,
  and status codes.
- It specifies, for each `classified_status`, the side effects on
  `Application.status` and `ApplicationEvent`.
- No file outside the Allowed list is modified.

## Verification

```bash
test -f docs/contracts/application_status.md
grep -q "ADR-010" docs/contracts/application_status.md
grep -q "timeline_stage" docs/contracts/application_status.md
grep -q "classified_status" docs/contracts/application_status.md
grep -q "email-links" docs/contracts/application_status.md
```

## Git instructions

Commit locally on the task branch with the message:

```
Add application status timeline contract
```

Do not push.
