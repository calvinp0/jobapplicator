# Task 113: Add Interactive Resume Suggestion Review

## Goal

Move resume tailoring toward an interactive review workflow where the user can see AI-suggested edits section-by-section and accept, reject, or request revisions.

The UI should behave more like modern resume tools such as Rezi-style editors:

```text
Resume preview
  +
section-level AI suggestions
  +
Accept / Reject / Revise controls
  +
evidence-backed explanations
```

Do not remove existing one-shot tailoring yet.  
Do not remove deterministic DOCX renderer work.  
Do not remove ATS audit.  
Do not remove claim audit.  
Do not change Gmail behavior.  
Do not change browser extension behavior.

## Background

The current tailoring flow produces full output artifacts:

```text
tailored_resume.md
tailored_resume.docx
change_log.md
claim_audit.md
ats_audit.md
template_fidelity_audit.md
recruiter_review.md
```

This is useful, but it gives the user too little control.

The better product experience is:

```text
1. Show the current resume content.
2. Show AI suggestions for each section.
3. Explain why each suggestion improves the resume.
4. Show evidence supporting the suggestion.
5. Let the user accept/reject/revise suggestions.
6. Render the final DOCX from accepted state.
```

This also supports the deterministic DOCX renderer because the final resume can be represented as structured JSON.

## Inspect

Inspect:

```text
runtime_prompts/resume_tailoring.md
runtime_prompts/resume_revision.md
backend/app/
backend/tests/
frontend/src/pages/
frontend/src/components/
frontend/src/api/
docs/contracts/
agent_tasks/queue.yaml
```

Search:

```bash
rg "tailored_resume.json|resume section|suggestion|claim_audit|ats_audit|resume_version|revision|draft" backend frontend runtime_prompts docs tests
```

Use existing project architecture.

## New Concept: Resume Suggestions

Add a structured suggestions artifact:

```text
output/resume_suggestions.json
```

Suggested schema:

```json
{
  "target_company": "Amazon",
  "target_job_title": "Software Development Engineer, AWS Agentic AI",
  "suggestions": [
    {
      "id": "sug_001",
      "section_id": "professional_summary",
      "section_heading": "PROFESSIONAL SUMMARY",
      "operation": "replace_section_text",
      "current_text": "...",
      "suggested_text": "...",
      "reason": "Emphasizes agentic AI developer tooling and distributed systems experience required by the job.",
      "evidence_refs": [
        {
          "source": "vtrace evidence",
          "quote": "Built a local-first code intelligence engine for AI coding agents..."
        }
      ],
      "ats_keywords": ["agentic AI", "developer tooling", "distributed systems"],
      "confidence": 0.86,
      "risk": "low",
      "status": "pending"
    }
  ]
}
```

Supported operations:

```text
replace_section_text
rewrite_bullet
insert_bullet
delete_bullet
reorder_bullets
add_skill
remove_skill
rewrite_entry
```

Keep the first implementation simple. At minimum support:

```text
replace_section_text
rewrite_bullet
insert_bullet
add_skill
```

## Prompt Requirements

Update the tailoring prompt so Claude produces:

```text
output/resume_suggestions.json
```

The prompt should say:

```text
Generate section-level suggestions before finalizing the resume.

Each suggestion must include:
- section heading
- current text or target text
- suggested text
- operation
- reason
- evidence references
- ATS keywords addressed
- confidence
- risk
```

The prompt must say:

```text
Do not suggest unsupported claims.
If a suggestion relies on weak or user-provided evidence, mark risk accordingly.
Use concise, reviewable suggestions.
Avoid rewriting the whole resume as one giant suggestion.
```

The prompt should also produce:

```text
output/tailored_resume.json
```

where possible, but the suggestion artifact is the main new user-review artifact.

## Backend Model Requirements

Add persistence for suggestion review state.

Use one of these approaches:

### Option A: Store suggestions as JSON on ResumeVersion

Add fields:

```text
suggestions_json
suggestion_review_state
```

### Option B: Add normalized ResumeSuggestion model

Suggested fields:

```text
id
resume_version_id
section_id
section_heading
operation
current_text
suggested_text
reason
evidence_refs_json
ats_keywords_json
confidence
risk
status
created_at
updated_at
```

For a first implementation, JSON storage is acceptable if it fits the current architecture.

Statuses:

```text
pending
accepted
rejected
revised
```

## Backend API Requirements

Add endpoints following existing route style.

Suggested endpoints:

```text
GET  /api/resume-versions/{id}/suggestions
POST /api/resume-versions/{id}/suggestions/{suggestion_id}/accept
POST /api/resume-versions/{id}/suggestions/{suggestion_id}/reject
POST /api/resume-versions/{id}/suggestions/{suggestion_id}/revise
POST /api/resume-versions/{id}/apply-suggestions
```

Use actual project route conventions.

### Accept

Marks suggestion as accepted and updates the working resume state.

### Reject

Marks suggestion as rejected.

### Revise

Request:

```json
{
  "instruction": "Make this less startup-focused and more backend systems-focused."
}
```

May either:

```text
- store the instruction for a later revision run
- or call the existing revision mechanism if simple
```

Do not overcomplicate first version.

### Apply Suggestions

Builds a new structured resume state from accepted suggestions.

If deterministic renderer exists, render a new DOCX from the accepted state.

## Frontend Requirements

Add an interactive resume review UI.

Suggested page or panel:

```text
Resume Review
```

Layout:

```text
left/main:
  resume preview by section

right/sidebar or inline cards:
  AI suggestions for selected section
```

For each suggestion card show:

```text
section
operation
current text
suggested text
reason
evidence refs
ATS keywords
confidence
risk
actions:
  Accept
  Reject
  Ask to revise
```

Accepted suggestions should visually mark the resume preview.

Rejected suggestions should collapse or move to a rejected list.

## Resume Preview Requirements

The preview does not need to perfectly render DOCX.

It should show structured resume sections:

```text
Header
Professional Summary
Skills
Experience
Education
Publications
```

Use the same section IDs as `tailored_resume.json` if available.

## Evidence Display

Suggestion cards should show evidence in a compact way:

```text
Evidence:
- vtrace evidence: "Built a local-first code intelligence engine..."
- AI Engineering resume: "Designed MCP-style tool interfaces..."
```

Do not show huge evidence blocks by default.

## ATS Display

Suggestion cards should show:

```text
ATS keywords addressed:
agentic AI, developer tooling, distributed systems
```

## Revision Interaction

For this task, “Ask to revise” may be simple:

```text
open textarea
save revision instruction
mark suggestion as revised_requested
```

If a working revision endpoint exists, it may call it.

Do not block task on full live AI per-suggestion regeneration unless easy.

## Output / Artifact Requirements

When tailoring completes, expected artifacts include:

```text
output/resume_suggestions.json
output/tailored_resume.json
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
output/ats_audit.md
output/recruiter_review.md
```

If `resume_suggestions.json` is missing, the run should still be allowed to complete only if this task chooses optional rollout.

Preferred:

```text
make resume_suggestions.json required after tests are updated
```

## Documentation

Update:

```text
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/frontend_redesign.md
```

Document:

```text
resume suggestion schema
review statuses
accept/reject/revise flow
relationship to deterministic DOCX renderer
evidence-backed suggestions
```

## Tests

Add/update backend tests:

1. Tailoring prompt requests `resume_suggestions.json`.
2. Suggestion schema validation accepts valid suggestions.
3. Suggestion schema validation rejects missing required fields.
4. Run import stores suggestions.
5. Suggestions API returns pending suggestions.
6. Accept endpoint marks suggestion accepted.
7. Reject endpoint marks suggestion rejected.
8. Apply suggestions builds or updates working resume state.
9. Evidence refs are preserved.
10. ATS keywords are preserved.
11. Unsupported claims are not encouraged by prompt.
12. Existing tailoring output validation still passes.

Add/update frontend tests if infrastructure exists:

1. Resume Review page renders sections.
2. Suggestion cards render.
3. Suggestion card shows reason.
4. Suggestion card shows evidence refs.
5. Suggestion card shows ATS keywords.
6. Accept button calls API and updates status.
7. Reject button calls API and updates status.
8. Revise textarea appears.
9. Accepted suggestion is visually marked.

## Acceptance Criteria

- Tailoring produces structured section-level suggestions.
- Suggestions include reasons, evidence, ATS keywords, confidence, and risk.
- Suggestions are persisted with review status.
- User can accept/reject suggestions in the UI.
- Resume preview displays sections and suggestions.
- Accepted suggestions can be applied to the working resume state.
- Existing one-shot artifact workflow still works.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_run_import.py
pytest
cd frontend && npm run build
```

If frontend tests exist:

```bash
cd frontend && npm test -- --run
```

Manual verification:

1. Generate a tailored run.
2. Open the resulting draft/review page.
3. Confirm AI suggestions are visible by section.
4. Confirm each suggestion has:
   - current text
   - suggested text
   - reason
   - evidence
   - ATS keywords
   - confidence/risk
5. Accept one suggestion.
6. Reject one suggestion.
7. Confirm statuses update.
8. Apply accepted suggestions.
9. Confirm final resume state updates.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add interactive resume suggestion review
```

Do not push.
