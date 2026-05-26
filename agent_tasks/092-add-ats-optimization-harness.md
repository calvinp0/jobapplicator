# Task 092: Add ATS Optimization Harness to Resume Tailoring

## Goal

Strengthen the resume tailoring prompt/harness so every generated resume is optimized for Applicant Tracking Systems while remaining truthful, readable, and evidence-backed.

The tailoring worker should explicitly analyze the job description for ATS keywords, map those keywords to supported evidence, apply them naturally in the resume, and produce an ATS audit.

Do not implement Gmail.  
Do not implement LinkedIn automation.  
Do not change OAuth behavior.  
Do not remove claim auditing.  
Do not encourage false or unsupported keyword stuffing.

## Background

Applicant Tracking Systems parse resumes for information such as:

```text
contact information
job titles
education
skills
certifications
keywords from the job posting
```

ATS-friendly resumes generally use:

```text
simple formatting
standard section headings
clear skills/work experience sections
standard fonts
minimal tables/graphics/text boxes
relevant keywords from the job description
correct spelling/acronyms/full terms
.docx when appropriate
```

The current tailoring system may not be strong enough at:

```text
- extracting ATS keywords from the job description
- distinguishing required vs preferred keywords
- placing keywords in the right resume sections
- preserving ATS-safe formatting
- avoiding keyword stuffing
- auditing whether each inserted keyword is supported by evidence
```

## Inspect

Inspect:

```text
runtime_prompts/resume_tailoring.md
runtime_prompts/resume_revision.md
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/run_import.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
backend/tests/test_revision_feedback_api.py
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
```

Search:

```bash
rg "ATS|keyword|claim_audit|tailored_resume|resume_tailoring|resume_revision" runtime_prompts backend docs tests
```

Use the existing project architecture.

## Required Outputs

Add a new required or optional output file:

```text
output/ats_audit.md
```

Preferred: make it required for successful tailoring and revision runs.

If changing required outputs is too disruptive, make it optional in this task and add a follow-up task to require it.

The ATS audit should include:

```text
# ATS Audit

## Target Role
- Job title:
- Company:

## Extracted Keywords
### Required / strongly signaled
- keyword
- keyword

### Preferred / nice-to-have
- keyword
- keyword

### Industry / role keywords
- keyword
- keyword

## Keyword Coverage
| Keyword | Included? | Resume section | Evidence source | Notes |
| --- | --- | --- | --- | --- |

## Formatting Check
- Standard section headings: pass/fail
- Simple bullet structure: pass/fail
- Avoided tables/text boxes/graphics for critical content: pass/fail
- ATS-friendly file type: pass/fail
- Standard fonts/readable typography: pass/fail

## Risks
- Missing important keywords:
- Keywords not used because unsupported by evidence:
- Possible keyword stuffing:
- Formatting risks:

## Summary
Short assessment of ATS readiness.
```

## Prompt Requirements

Update the tailoring prompt so the worker performs an explicit ATS pass.

The prompt should say:

```text
Before writing the tailored resume, analyze the job description for ATS keywords.

Extract:
- exact job title
- company name
- required skills
- preferred skills
- tools/technologies
- certifications/degrees
- domain keywords
- repeated phrases
- responsibility keywords

Classify keywords as:
- required
- preferred
- industry/role-specific
```

The prompt should then say:

```text
Use ATS keywords only when they are truthful and supported by the master resume or evidence sources.

Do not add unsupported skills, certifications, degrees, employers, dates, metrics, or responsibilities.

Do not keyword-stuff.

Place supported keywords naturally in:
- Professional Summary
- Skills
- Work Experience bullets
- Projects
- Education, if relevant
```

The prompt should include:

```text
Use both acronym and full phrase when useful and truthful.

Examples:
- Large Language Models (LLMs)
- Applicant Tracking System (ATS)
- Machine Learning (ML)
```

The prompt should also say:

```text
Match spelling and terminology from the job description when truthful.

If the job description says "PostgreSQL", prefer "PostgreSQL" over "Postgres" unless both are useful.
If the job description says "LLM", include "Large Language Models (LLMs)" if supported.
```

## ATS Formatting Requirements

Update the prompt so generated DOCX/markdown follows ATS-safe structure.

Require standard headings:

```text
Professional Summary
Skills
Work Experience
Projects
Education
```

Use headings only when the section exists.

Avoid critical content in:

```text
headers/footers
text boxes
images
graphics
complex tables
multi-column layouts
```

For DOCX:

```text
Use real Word headings, paragraphs, and bullet lists.
Do not create a plain-text dump.
Do not place important resume content only in headers/footers/text boxes.
Prefer ATS-readable layout over decorative layout.
```

For markdown:

```text
Use plain headings and bullet lists.
Avoid tables for key experience content.
```

## Evidence and Claim Audit Integration

Update the claim audit expectations.

For every important ATS keyword inserted or emphasized, the audit should identify:

```text
keyword
resume location
supporting evidence
risk level
```

If a keyword appears in the job description but is not supported, the audit should say:

```text
Keyword not used because unsupported by evidence.
```

The claim audit must remain honest.

## Revision Prompt Requirements

Update the revision prompt too.

When revising a tailored resume, the worker should:

```text
preserve ATS-relevant keywords that remain truthful
apply the user revision request
avoid removing important ATS coverage unless necessary
update ats_audit.md
update claim_audit.md
```

If the revision request adds new facts, the worker should:

```text
treat them as user-provided evidence
flag them in claim_audit.md
include them in ats_audit.md only if relevant
```

## Backend Validation

Update worker validation to expect `output/ats_audit.md` if making it required.

If optional in this task, the worker should still surface it when present.

Run logs should include:

```text
jobapply: ATS optimization requested
jobapply: ATS audit expected at output/ats_audit.md
```

## Frontend Requirements

If easy, expose ATS audit from run/draft detail pages.

Add a link/button:

```text
Open ATS audit
```

or include it with other artifacts.

If frontend artifact display is too large, ensure the file is downloadable/openable through existing file APIs.

## Tests

Add/update backend tests to prove:

1. Tailoring prompt mentions ATS optimization.
2. Tailoring prompt extracts required/preferred/industry keywords.
3. Tailoring prompt says not to keyword-stuff.
4. Tailoring prompt says ATS keywords must be evidence-backed.
5. Tailoring prompt requires standard section headings.
6. Tailoring prompt warns against headers, text boxes, graphics, complex tables for critical content.
7. Tailoring prompt says to use full terms and acronyms when useful and truthful.
8. Revision prompt preserves ATS coverage and updates ATS audit.
9. Worker log records ATS optimization requested.
10. Fake Claude that writes `ats_audit.md` plus required outputs completes.
11. Fake Claude that omits `ats_audit.md` fails if the file is required.
12. Claim audit or ATS audit includes unsupported-keyword handling.
13. Existing output validation still works.

If frontend changed, add tests if frontend test infrastructure exists:

1. Run/draft page shows Open ATS audit when file exists.
2. ATS audit file can be opened/downloaded.

## Acceptance Criteria

- Tailoring prompt performs explicit ATS keyword extraction.
- Tailoring prompt applies supported keywords naturally.
- Prompt forbids unsupported keyword stuffing.
- Prompt enforces ATS-safe resume formatting.
- Claim audit covers ATS keyword support.
- `ats_audit.md` is produced or at least requested.
- Revision flow updates ATS audit.
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

1. Create a job with a detailed job description.
2. Generate a tailored draft.
3. Confirm outputs include:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
output/ats_audit.md
```

4. Open `ats_audit.md`.
5. Confirm it lists:
   - required keywords
   - preferred keywords
   - keyword coverage
   - unsupported keywords
   - formatting risks
6. Open the resume and confirm it uses:
   - standard section headings
   - simple bullets
   - no critical content hidden in tables/images/headers
7. Confirm unsupported keywords are not invented.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add ATS optimization harness
```

Do not push.
