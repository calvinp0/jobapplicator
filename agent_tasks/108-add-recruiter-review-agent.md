# Task 108: Add Recruiter Review Agent for Tailored Resumes

## Goal

Add a recruiter/hiring-manager review step after resume tailoring.

The review agent should evaluate the tailored resume as if it were being read by the target company for the target role.

It should identify whether the resume is likely to pass a human screen, not only an ATS scan.

Do not replace ATS optimization.  
Do not remove claim auditing.  
Do not change Gmail behavior.  
Do not change browser extension behavior.  
Do not change database reset behavior.

## Background

Current tailoring produces:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
output/ats_audit.md
output/template_fidelity_audit.md
```

The next quality layer should be a simulated recruiter/company review.

The reviewer should act as:

```text
a recruiter
a hiring manager
a resume screener
the target company
```

and answer:

```text
Would this candidate likely be shortlisted?
What is compelling?
What is weak?
What is missing?
What sounds generic?
What sounds unsupported?
What should be revised before submission?
```

## Inspect

Inspect:

```text
runtime_prompts/
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/run_import.py
backend/tests/
frontend/src/pages/
frontend/src/api/
docs/contracts/
agent_tasks/queue.yaml
```

Search:

```bash
rg "ats_audit|claim_audit|change_log|tailored_resume|review|revision|prompt" runtime_prompts backend frontend docs
```

Use the existing project architecture.

## New Output

Add a new output artifact:

```text
output/recruiter_review.md
```

Preferred: make this required for successful tailoring runs after this task.

If making it required is too disruptive, request it first and make it required in a follow-up.

## Recruiter Review Prompt

Create a dedicated prompt file:

```text
runtime_prompts/recruiter_review.md
```

or add a clear review section to the existing tailoring prompt.

Preferred: separate prompt.

The review agent should receive:

```text
job description
company name
job title
tailored_resume.md
claim_audit.md
ats_audit.md
template_fidelity_audit.md if present
evidence_sources_index.md if present
```

It should review the tailored resume from the perspective of:

```text
1. recruiter initial screen
2. hiring manager technical screen
3. ATS/human keyword alignment
4. credibility and evidence
5. visual/readability quality
```

## Review Output Format

`output/recruiter_review.md` should use this structure:

```text
# Recruiter Review

## Target Role
- Company:
- Job title:

## Overall Recommendation
One of:
- Strong submit
- Submit after minor edits
- Needs revision before submit
- Do not submit yet

## Scorecard
| Category | Score / 5 | Notes |
| --- | ---: | --- |
| Role fit |  |  |
| Technical keyword alignment |  |  |
| Evidence strength |  |  |
| Recruiter readability |  |  |
| Hiring manager credibility |  |  |
| Seniority/level fit |  |  |
| Formatting/professionalism |  |  |

## First 30-Second Impression
Short paragraph describing what a recruiter would likely notice first.

## Strengths
- ...

## Weaknesses / Risks
- ...

## Missing or Under-emphasized Requirements
- ...

## Claims That Need Stronger Evidence
- ...

## Lines or Bullets to Improve
| Current text | Issue | Suggested rewrite |
| --- | --- | --- |

## Company-Specific Fit
Explain how well the resume speaks to this company and role.

## Final Recommendation
Clear submit / revise recommendation.
```

## Review Criteria

The review agent should look for:

```text
clear match to role title
required skills from job description
strong first impression
relevant technical depth
evidence-backed claims
specific accomplishments
appropriate seniority
readability
resume length
formatting quality
lack of generic filler
lack of unsupported exaggeration
```

## Company Persona

The prompt should instruct the reviewer to infer the likely company expectations from the job description.

Examples:

```text
If the company is a startup:
  value ownership, speed, pragmatic engineering, breadth.

If the role is research-heavy:
  value publications, rigorous methods, technical depth.

If the role is enterprise/backend:
  value reliability, production systems, maintainability, collaboration.

If the role is ML:
  value modeling, data pipelines, evaluation, deployment, measurable impact.
```

Do not invent facts about the company beyond the provided job description.

## Integration Option A: Same Tailoring Run

The simplest implementation:

```text
Tailoring prompt asks Claude to produce recruiter_review.md along with other outputs.
```

This is acceptable if the worker already invokes Claude once per tailoring run.

## Integration Option B: Separate Review Worker

Preferred longer-term implementation:

```text
Tailoring worker creates resume.
Review worker reads outputs.
Review worker writes recruiter_review.md.
Optional revision worker applies feedback.
```

If separate worker is too large, implement Option A now and document Option B as future work.

## Backend Validation

Update worker validation to expect:

```text
output/recruiter_review.md
```

if making it required.

Run log should include:

```text
jobapply: recruiter review requested
jobapply: recruiter review expected at output/recruiter_review.md
```

## Revision Flow

Revision runs should also update:

```text
output/recruiter_review.md
```

The revision prompt should say:

```text
After applying the revision request, re-review the result as a recruiter/hiring manager and update recruiter_review.md.
```

## Frontend Requirements

Expose recruiter review on run/draft detail pages.

Add link/button:

```text
Open recruiter review
```

If artifact tabs exist, include:

```text
Recruiter Review
```

Suggested artifact order:

```text
Resume
Change Log
Claim Audit
ATS Audit
Template Fidelity
Recruiter Review
Prompt Snapshot
```

If UI work is too large, ensure the file is accessible through existing artifact APIs.

## Optional Auto-Revision Recommendation

Do not automatically apply recruiter feedback in this task.

But `recruiter_review.md` should include suggested rewrites that can be used later by revision flow.

Future task can add:

```text
Apply recruiter review suggestions
```

## Tests

Add/update backend tests:

1. Tailoring prompt or review prompt requests `recruiter_review.md`.
2. Review prompt tells reviewer to act as recruiter/hiring manager for target company.
3. Review prompt includes scorecard.
4. Review prompt includes first 30-second impression.
5. Review prompt includes strengths/weaknesses.
6. Review prompt includes missing requirements.
7. Review prompt includes suggested rewrites.
8. Review prompt says not to invent company facts.
9. Worker log records recruiter review requested.
10. Worker validates `recruiter_review.md` if required.
11. Fake Claude writing all required outputs including recruiter review completes.
12. Fake Claude omitting recruiter review fails if required.
13. Revision flow requests updated recruiter review.

Add/update frontend tests if infrastructure exists:

1. Draft/run detail shows Open recruiter review when artifact exists.
2. Recruiter review appears in artifact list/tabs.

## Acceptance Criteria

- Tailoring runs request recruiter/hiring-manager review.
- `recruiter_review.md` is produced or requested.
- Review includes scorecard and recommendation.
- Review evaluates human readability and company/role fit.
- Review identifies weaknesses and suggested rewrites.
- Review does not invent company facts.
- Recruiter review is visible from the web UI.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_revision_feedback_api.py
pytest backend/tests/test_run_directory.py
pytest
cd frontend && npm run build
```

Manual verification:

1. Generate a tailored resume.
2. Confirm output includes:

```text
output/recruiter_review.md
```

3. Open recruiter review.
4. Confirm it includes:
   - recommendation
   - scorecard
   - first 30-second impression
   - strengths
   - weaknesses
   - missing requirements
   - suggested rewrites
5. Confirm the review is visible from the draft/run detail page.
6. Confirm it does not invent facts beyond the job description/resume/evidence.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add recruiter review agent
```

Do not push.
