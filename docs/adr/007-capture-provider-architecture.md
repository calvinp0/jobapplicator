# ADR-007: Capture Provider Architecture

## Status

Accepted

## Context

The app should support multiple ways of creating job records.

LinkedIn current-page capture is useful, but the core app should not become tightly coupled to LinkedIn or any single job board.

## Decision

Job intake will use a capture provider architecture.

Initial providers may include:

- manual paste capture
- clipboard capture
- selected-text capture
- browser-extension current-page capture

All providers must return a normalized job capture payload.

## Rationale

This keeps the backend and application tracker independent of any one website.

If LinkedIn parsing breaks, the rest of the app still works through clipboard/manual capture or other providers.

## Consequences

The backend should expose a generic capture intake endpoint.

Site-specific parsing should live in provider-specific modules, not in the core job/application logic.

Captured data must be confirmed by the user before it becomes an application record.

## Alternatives Considered

- LinkedIn-only architecture: rejected because it is brittle.
- Manual-only architecture: rejected because it creates too much friction.
- Pluggable capture providers: accepted.

## Notes

A normalized capture payload should include fields such as source platform, capture method, URL, external job ID, company, title, location, description text, application method, raw text, capture time, and user confirmation state.
