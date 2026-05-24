# Task 056: Clarify Capture Auto-Confirm ADR Semantics

## Goal

Clarify the architecture decision around browser-extension capture auto-confirmation.

Task 054 added auto-confirmation for complete extension captures:

```text
Extension captures complete LinkedIn job
→ backend stores Capture
→ backend creates/reuses Job
→ extension can open Job workspace

The review approved the implementation but noted that ADR-005 / ADR-007 discuss user confirmation before captured data becomes an application or before resume generation.

This task should clarify the distinction:

Capture → Job auto-confirmation is allowed for complete extension captures.
Job → Application and Job → Resume generation still require explicit user action.

This is documentation/ADR clarification only.

Do not implement product code.

Background

Read:

docs/adr/
agent_tasks/054-auto-confirm-complete-extension-captures.md
backend/app/routers/captures.py
extension/**

Review note from task 054:

ADR-005 / ADR-007 say the user must confirm captured data before it becomes an application / before resume generation. The auto-confirm path here only creates the Job row, not an Application and not a resume run, and the user still explicitly clicks "Send to backend" in the popup, so the spirit of the ADRs is preserved. Consider a follow-up ADR note clarifying the distinction between Capture→Job and Job→Application confirmation.
Scope

Update:

docs/adr/**

Optionally update:

docs/product_requirements.md
docs/contracts/agent_orchestration.md
agent_tasks/056-adr-capture-auto-confirm-clarification.md
agent_tasks/queue.yaml

Do not edit backend, frontend, extension, or runtime code.

Required Clarification

Document that:

Complete extension captures may be auto-confirmed into Job records.

A complete extension capture means it has enough required fields to create a usable Job, such as:

title
company
url
description

This auto-confirmation is allowed because:

- the user explicitly initiated capture from the extension
- the extension shows the captured fields before sending
- creating a Job is not the same as submitting an application
- creating a Job is not the same as generating a tailored resume

Still require explicit user action for:

Job → tailored resume generation
Resume draft → approval
Approved draft → application creation
Application → submitted/sent state
Acceptance Criteria
ADR text clearly distinguishes Capture → Job from Job → Application.
ADR text clearly states auto-confirming a complete extension capture into a Job is allowed.
ADR text clearly states resume generation still requires explicit user action.
ADR text clearly states application creation/submission still requires explicit user action.
No product code is changed.
Verification

Run:

grep -R "Capture.*Job\|auto-confirm\|resume generation\|application" -n docs/adr
Git

After verification passes:

Stage changed files.
Commit locally with:
Clarify capture auto-confirm ADR semantics

Do not push.
