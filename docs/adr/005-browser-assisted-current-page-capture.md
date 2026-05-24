# ADR-005: Browser-Assisted Current-Page Capture

## Status

Accepted

## Context

The app should avoid forcing the user to manually copy and paste job descriptions. The user wants a smoother LinkedIn/EasyApply workflow while keeping final submission human-controlled.

## Decision

The MVP may support browser-assisted current-page capture.

The user must explicitly trigger capture. The capture helper may extract job information from the currently visible job page and send a normalized payload to the local backend.

## Rationale

Manual copy/paste creates a bad user experience. Current-page capture makes the app useful while preserving user control over job review, resume approval, and final application submission.

## Consequences

The backend must treat captured data as untrusted input.

The user must confirm captured job data before resume generation.

LinkedIn-specific parsing must stay isolated from the core backend.

### Clarification: Capture → Job vs Job → Application vs Resume Generation

"User must confirm captured job data" applies to resume generation and application creation, not to creating a Job row.

A complete browser-extension capture (non-empty `title`, `company`, `url`, and `description`) may be auto-confirmed into a Job record without an extra manual confirmation step. This is allowed because:

- the user explicitly initiated the capture from the extension
- the extension surfaces the captured fields to the user before sending
- creating a Job record is not the same as creating an Application
- creating a Job record is not the same as generating a tailored resume
- creating a Job record is not the same as submitting an application

Explicit user action is still required for:

- Job → tailored resume generation
- Resume draft → user approval
- Approved resume draft → Application creation
- Application → submitted/sent state

Incomplete or ambiguous captures (missing required fields) must continue to surface in the Captures review flow for manual confirmation before becoming a Job.

## Alternatives Considered

- Manual paste only: simpler, but poor UX.
- Fully automated LinkedIn application: too broad and not aligned with the human-in-the-loop design.
- Clipboard capture only: safer and simple, but less smooth than current-page capture.

## Notes

Allowed behavior includes one-job current-page capture after explicit user action.

Forbidden behavior includes background crawling, auto-clicking EasyApply, auto-attaching files, auto-submitting applications, profile harvesting, and recruiter messaging.
