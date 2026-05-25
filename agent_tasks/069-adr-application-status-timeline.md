# Task 069: ADR for application status timeline and Gmail integration boundary

Task ID: `069-adr-application-status-timeline`

## Goal

Write a new ADR (ADR-010) that records the decision for how an
Application's lifecycle is surfaced to the user — covering manual
submit, email-driven status updates (confirmation, rejection,
moving-forward signals), and the boundary between the existing
`Application.status` field and the `EmailLink` evidence rows.
Downstream contract, backend, and frontend tasks will reference this
ADR.

## Background

Read first:

- `docs/product_requirements.md` (Application Tracking, Non-goals)
- `docs/architecture.md` (Human-in-the-Loop Rule, components)
- `docs/adr/000-template.md`
- `docs/adr/001-local-first-mvp.md`
- `docs/adr/003-human-in-the-loop-submission.md`
- `backend/app/models.py` (`Application`, `ApplicationEvent`,
  `EmailLink`, `APPLICATION_STATUSES`)
- `backend/app/routers/applications.py`
- `frontend/src/pages/ApplicationsPage.tsx`
- `frontend/src/pages/ApplicationDetailPage.tsx`

Context the ADR must reconcile:

- `Application.status` already supports `submitted`,
  `response_received`, `rejected`, `interview`, `offer`, `withdrawn`,
  but the frontend currently only highlights `submitted` and treats
  everything else as a generic label.
- An `EmailLink` model exists but has no router, no schema, and no UI
  surface. Its `classified_status` and `confidence` columns hint at a
  future Gmail-driven classifier.
- Gmail integration is explicitly out of scope for the first MVP
  (product-requirements.md "Non-Goals" + non-goals list). The ADR must
  preserve that boundary while letting the UI display email evidence
  recorded by hand today and by a future Gmail integration tomorrow.
- ADR-003 keeps the human in control of submitting; this ADR must not
  introduce any automated send.

## Scope

Add `docs/adr/010-application-status-timeline.md` following
`docs/adr/000-template.md`. The ADR must take a concrete position on:

- **Timeline model**: an Application's user-visible state is a
  *timeline* of stages, derived from `Application.status`,
  `Application.submitted_at`, and the `EmailLink` rows attached to the
  application. The ADR must enumerate the stages the UI surfaces, at
  minimum:

  - `draft` — created, not yet sent
  - `sent` — `submitted_at` set, no confirmation email recorded yet
  - `confirmation_received` — at least one `EmailLink` with
    `classified_status="confirmation"` is attached
  - `response_received` — any non-confirmation classified email is
    attached, or status was manually advanced
  - `rejected` / `interview` / `offer` / `withdrawn` — explicit terminal
    or branching states; map to `Application.status` values of the same
    name

  The ADR must state explicitly that the timeline is a *derivation*,
  not a new column. `Application.status` remains the authoritative
  coarse state; the timeline is computed from status + submitted_at +
  email evidence.

- **EmailLink semantics**: define the canonical values for
  `EmailLink.classified_status`:

  - `confirmation` — the recipient acknowledged that the application
    was received (e.g. ATS auto-reply)
  - `rejection` — explicit "no" from the employer
  - `next_step` — interview invite, take-home, recruiter screen, etc.
  - `offer` — formal offer
  - `other` — fallback for unclassified mail

  The ADR must state that these values are stable strings (the
  database stores them as TEXT, following the existing pattern in
  `models.py`), and that the contract/router task may pin them to a
  module-level tuple.

- **Manual vs. automated entry**: until Gmail integration lands, an
  EmailLink may be entered by the user manually (via a new endpoint
  + UI control) and `gmail_message_id` may carry a placeholder value
  (e.g. `manual:<uuid>`). The ADR must state this is allowed and that
  a future Gmail-integration ADR will tighten the contract.

- **Status transitions driven by email evidence**: the ADR must
  describe the rule the backend applies when a new EmailLink is
  recorded:

  - if `classified_status="rejection"` and the application is not
    `withdrawn`, set `Application.status = "rejected"` and append an
    `ApplicationEvent`
  - if `classified_status="next_step"` and the application is not
    `rejected`/`withdrawn`/`offer`, set
    `Application.status = "interview"` (or leave at
    `response_received`; the ADR may pick — record the choice and the
    reason)
  - if `classified_status="offer"`, set
    `Application.status = "offer"`
  - if `classified_status="confirmation"`, do *not* change
    `Application.status` (confirmation is timeline-only). Record the
    rationale: confirmation does not progress the application from the
    employer's side; it only confirms our send.

- **Gmail integration boundary**: the ADR must restate that Gmail API,
  MCP, or browser-extension Gmail polling is **out of scope** for this
  ADR. It must explicitly defer:

  - the Gmail credential model,
  - polling cadence and dedupe behaviour,
  - server-side classification (the `confidence` column is reserved
    for it but unused for now),
  - automatic resolution of `Application` ↔ `gmail_thread_id`.

  The ADR must say a future ADR will cover those, and that this ADR
  only locks in the UI/data surface.

- **Human-in-the-loop preservation**: cite ADR-003 and state that no
  outbound email or auto-submission is added by this ADR.

## Allowed files

```
docs/adr/010-application-status-timeline.md
agent_tasks/069-adr-application-status-timeline.md
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
docs/contracts/**
docs/product_requirements.md
docs/architecture.md
docs/adr/000-template.md
docs/adr/001-local-first-mvp.md
docs/adr/002-claude-code-worker-boundary.md
docs/adr/003-human-in-the-loop-submission.md
docs/adr/004-evidence-constrained-resume-tailoring.md
docs/adr/005-browser-assisted-current-page-capture.md
docs/adr/006-candidate-context-as-source-material.md
docs/adr/007-capture-provider-architecture.md
docs/adr/008-revision-feedback-flow.md
docs/adr/009-llm-provider-selection.md
```

Existing ADRs are immutable. Only ADR-010 may be added. ADR-009 may
also be added by task 063; this task must not touch it.

## Out of scope

- Backend schema, router, or migration code (task 071).
- Contract update for the API surface (task 070).
- Frontend changes (tasks 072 and 073).
- Any Gmail API, MCP, or extension Gmail-polling integration.
- Automatic classification of email contents.

## Acceptance criteria

- `docs/adr/010-application-status-timeline.md` exists and follows the
  ADR template structure (Status, Context, Decision, Rationale,
  Consequences, Alternatives Considered, Notes).
- Status is `Accepted`.
- The ADR explicitly names:
  - the timeline stages enumerated above and that the timeline is a
    derivation, not a new column,
  - the canonical `EmailLink.classified_status` values
    (`confirmation`, `rejection`, `next_step`, `offer`, `other`),
  - that manual EmailLink entry is allowed and `gmail_message_id`
    may be a `manual:<…>` placeholder,
  - the per-classification rule for updating `Application.status`,
  - the explicit Gmail-out-of-scope boundary,
  - that ADR-003 is preserved (no automated send).
- The ADR references ADR-001 and ADR-003 by id.
- No file under `docs/adr/` other than `010-application-status-timeline.md`
  is modified.
- No file outside `docs/adr/` or the listed agent_tasks files is
  modified.

## Verification

```bash
ls docs/adr/
test -f docs/adr/010-application-status-timeline.md
grep -q "ADR-003" docs/adr/010-application-status-timeline.md
grep -q "EmailLink" docs/adr/010-application-status-timeline.md
grep -q "classified_status" docs/adr/010-application-status-timeline.md
```

## Git instructions

Commit locally on the task branch with the message:

```
Add ADR-010 for application status timeline
```

Do not push.
