# ADR-003: Human-in-the-Loop Submission

## Status

Accepted

## Context

The app should help prepare better job applications, but it should not behave like an autonomous job bot.

The user wants automation around capture, resume tailoring, record keeping, and response tracking, while keeping control over final submission.

## Decision

The system will remain human-in-the-loop for application submission.

The app may capture job context, generate tailored resumes, open generated files, and track application state.

The user manually reviews the captured job, approves the resume, attaches the resume, and submits the application.

## Rationale

This keeps the product focused on high-value assistance rather than uncontrolled automation.

It also makes the workflow easier to trust because every submitted application is explicitly reviewed.

## Consequences

The app will not auto-click Easy Apply.

The app will not auto-attach resumes.

The app will not auto-submit applications.

Application status changes such as `submitted` require user confirmation unless a later trusted signal is explicitly implemented.

## Alternatives Considered

- Fully automatic job application submission: rejected because it is too broad and risky.
- Manual tracking only: rejected because it does not remove enough friction.
- Semi-automatic capture and resume generation: accepted as the right MVP balance.

## Notes

This decision does not prevent future workflow assistance, but final submission remains user-controlled.
