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

### Clarification: Capture → Job is not Capture → Application

"Captured data must be confirmed by the user before it becomes an application record" refers to the Application entity (and the downstream resume tailoring and submission flow), not the Job entity.

A complete capture from a capture provider — currently defined for the browser-extension provider as having non-empty `title`, `company`, `url`, and `description` — may be auto-confirmed into a Job record. Auto-confirmation is permitted because:

- the user explicitly initiated the capture
- the capture provider surfaces the captured fields to the user before they are sent
- a Job is a tracked work item, not an application or a resume artifact
- the user still chooses when to tailor a resume or create an Application from that Job

Manual user confirmation is still required for:

- Job → tailored resume generation
- Resume draft → user approval
- Approved resume draft → Application creation
- Application → submitted/sent state

Capture providers that produce incomplete payloads must continue to route through the Captures review flow so the user can fill in missing fields before a Job is created.

## Alternatives Considered

- LinkedIn-only architecture: rejected because it is brittle.
- Manual-only architecture: rejected because it creates too much friction.
- Pluggable capture providers: accepted.

## Notes

A normalized capture payload should include fields such as source platform, capture method, URL, external job ID, company, title, location, description text, application method, raw text, capture time, and user confirmation state.
