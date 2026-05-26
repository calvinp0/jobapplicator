# Task 105: Preserve Master Resume DOCX Style During Tailoring

## Goal

Strengthen the resume tailoring and revision harness so generated DOCX resumes preserve the visual style of the master resume DOCX.

If the user's master resume has blue section headers, specific fonts, spacing, margins, bullet indentation, or other simple professional styling, the tailored resume should retain that style.

Do not remove ATS optimization.  
Do not make the resume visually complex or ATS-hostile.  
Do not change Gmail behavior.  
Do not change browser extension behavior.  
Do not change database reset behavior.

## Background

The user's master resume is a DOCX and may contain styling such as:

```text
colored section headers
specific font choices
section spacing
bullet indentation
simple separators
bold/italic emphasis
```

The tailoring pipeline should treat the master DOCX as both:

```text
1. a factual source / resume source
2. a formatting and style template
```

The current harness emphasizes ATS and DOCX generation but may not explicitly require preserving the master resume's styling.

## Inspect

Inspect:

```text
runtime_prompts/resume_tailoring.md
runtime_prompts/resume_revision.md
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/docx_extract.py
backend/app/word_handoff.py
backend/tests/test_claude_worker.py
backend/tests/test_word_handoff.py
backend/tests/test_docx_extract.py
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/office_word_mcp_setup.md
```

Search:

```bash
rg "DOCX|Word MCP|style|formatting|ATS|master_resume.docx|tailored_resume.docx|plain-text dump" runtime_prompts backend docs tests
```

## Required Prompt Behavior

Update the tailoring prompt so it explicitly states:

```text
If input/master_resume.docx exists, treat it as the formatting/style source of truth.

Prefer copying/editing the source DOCX when possible instead of rebuilding a generic resume from scratch.

Preserve the master resume's professional styling, including:
- section heading colors
- font families
- font sizes
- margins
- paragraph spacing
- bullet indentation
- bold/italic emphasis patterns
- simple horizontal rules or separators
- section heading hierarchy
```

Also state:

```text
If the master resume uses blue section headers or similar simple color styling, preserve that styling in output/tailored_resume.docx.

Do not strip professional color styling unless it causes ATS readability problems.

Do not create a plain-text dump inside a DOCX.
```

## ATS Balance Requirements

The prompt must balance style preservation with ATS readability:

```text
Preserve visual styling while keeping the resume ATS-readable.

Do not place critical resume content only in:
- headers
- footers
- text boxes
- images
- graphics
- complex tables
- multi-column layouts

Simple colored headings, standard fonts, normal paragraphs, and bullet lists are acceptable.
```

## Word MCP Requirements

Update the prompt so Claude Code knows how to use Word MCP for style preservation:

```text
When word-document-server is available:
- inspect the source DOCX structure/styles
- copy the source DOCX as the editable base when possible
- replace/tailor text while preserving paragraph styles and run formatting
- preserve heading styles/colors where possible
- preserve bullet/list styles where possible
```

If the MCP tools cannot preserve styling, the worker should:

```text
document the limitation in output/claim_audit.md or output/ats_audit.md
still produce the required outputs
```

## Revision Prompt Requirements

Update the revision prompt too.

Revision runs should preserve:

```text
the current tailored resume's style
the original master resume's style
```

The revision prompt should say:

```text
Do not restyle the resume unless the user explicitly asks.
Apply the requested content changes while preserving existing DOCX styling.
```

## Word Handoff Requirements

Update Claude for Word handoff prompt/instructions if present.

It should say:

```text
Preserve the master resume's existing visual style, including colored headings, fonts, spacing, margins, and bullet indentation.
Use tracked changes if available.
Do not rebuild the document from scratch.
```

## Run Log Requirements

When a DOCX master resume is present, log:

```text
jobapply: source DOCX style preservation requested
```

If possible, log:

```text
jobapply: master resume DOCX staged as formatting source
```

Do not log sensitive resume content.

## Tests

Add/update tests to prove:

1. Tailoring prompt mentions preserving master DOCX style.
2. Tailoring prompt specifically mentions preserving heading colors.
3. Tailoring prompt says blue/simple colored headings should be preserved.
4. Tailoring prompt says to copy/edit source DOCX when possible.
5. Tailoring prompt says not to create a generic/plain-text DOCX.
6. Tailoring prompt balances style preservation with ATS readability.
7. Tailoring prompt warns against critical content in headers/text boxes/images/complex tables.
8. Revision prompt says to preserve existing DOCX styling.
9. Word handoff prompt says to preserve colored headings/fonts/spacing.
10. Worker log records style preservation requested when master_resume.docx exists.
11. Existing DOCX extraction tests still pass.
12. Existing ATS prompt tests still pass.

## Acceptance Criteria

- Tailoring harness treats master DOCX as formatting/style template.
- Colored section headers are explicitly preserved when ATS-safe.
- Word MCP instructions prioritize copy/edit over rebuild.
- Revision harness preserves styling.
- Word handoff instructions preserve styling.
- ATS readability constraints remain intact.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_word_handoff.py
pytest backend/tests/test_docx_extract.py
pytest
```

Manual verification:

1. Use a master resume DOCX with colored section headers.
2. Generate a tailored resume.
3. Open:

```text
output/tailored_resume.docx
```

4. Confirm:
   - section header colors are preserved
   - fonts are preserved
   - margins/spacing look similar
   - bullets retain indentation
   - content is tailored to the job
   - ATS audit does not flag style as harmful unless there is a real issue

5. Run a revision.
6. Confirm the revised DOCX preserves the same style.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Preserve master resume DOCX style
```

Do not push.
