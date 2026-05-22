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

## Alternatives Considered

- Manual paste only: simpler, but poor UX.
- Fully automated LinkedIn application: too broad and not aligned with the human-in-the-loop design.
- Clipboard capture only: safer and simple, but less smooth than current-page capture.

## Notes

Allowed behavior includes one-job current-page capture after explicit user action.

Forbidden behavior includes background crawling, auto-clicking EasyApply, auto-attaching files, auto-submitting applications, profile harvesting, and recruiter messaging.
