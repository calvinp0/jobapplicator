# Task 107: Add DOCX Template Fidelity Audit for Tailored Resumes

## Goal

Ensure tailored DOCX resumes preserve the visual template and formatting structure of the selected master resume DOCX.

Current observed issue:

The tailored resume content was reasonable, but the generated DOCX lost key formatting from the original master resume:

```text
- centered name/header block
- centered contact links
- horizontal divider line
- blue section heading style
- proper bullet/list structure
- original spacing rhythm
- original resume visual identity
```

The output looked like a generic regenerated document rather than a tailored version of the original resume template.

Do not remove ATS optimization.  
Do not make the resume ATS-hostile.  
Do not change Gmail behavior.  
Do not change browser extension behavior.  
Do not change database reset behavior.

## Background

The user's master resume DOCX includes:

```text
- centered name
- centered contact links
- professional summary heading
- experience heading
- blue section heading style
- horizontal separator lines
- structured bullet lists
- date alignment for experience entries
- consistent spacing and typography
```

The tailoring pipeline should treat:

```text
input/master_resume.docx
```

as the formatting/template source of truth.

The tailored output:

```text
output/tailored_resume.docx
```

should preserve the template as much as possible while changing content for the job.

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
rg "DOCX|Word MCP|style|formatting|template|bullet|heading|ATS|master_resume.docx|tailored_resume.docx|plain-text dump" runtime_prompts backend docs tests
```

## Required Prompt Behavior

Update the tailoring prompt so it explicitly states:

```text
If input/master_resume.docx exists, it is the formatting/template source of truth.

Do not rebuild the resume from scratch unless copying/editing the source DOCX fails.

Prefer this workflow:
1. Copy input/master_resume.docx as the editable base.
2. Replace/tailor text inside the copied document.
3. Preserve paragraph styles, heading styles, list styles, colors, spacing, margins, and alignment.
4. Save the result as output/tailored_resume.docx.
```

The prompt must specifically require preserving:

```text
- centered name/header block
- centered contact line / links
- header spacing
- horizontal divider/separator lines
- blue or colored section heading style
- standard section heading names
- bullet list formatting
- date alignment
- margins
- font families
- font sizes
- paragraph spacing
- bold/italic emphasis patterns
```

The prompt must say:

```text
If the master resume uses blue section headings or similar simple color styling, preserve that styling in output/tailored_resume.docx.

If the master resume has bullet points, the tailored resume should keep bullet points rather than converting them to plain paragraphs.

If the master resume has a centered header block, preserve centered alignment for the name and contact details.
```

## ATS Balance Requirements

The prompt must balance style preservation with ATS readability:

```text
Preserve visual styling while keeping the resume ATS-readable.

Simple colored headings, standard fonts, horizontal rules, normal paragraphs, and bullet lists are acceptable.

Do not place critical resume content only in:
- headers
- footers
- text boxes
- images
- graphics
- complex tables
- multi-column layouts
```

## Word MCP Requirements

Update prompt instructions for Word MCP:

```text
When word-document-server is available:
- inspect the source DOCX structure/styles
- copy the source DOCX as the editable base when possible
- preserve paragraph styles and run formatting
- preserve heading colors
- preserve list/bullet styles
- preserve centered header alignment
- preserve horizontal separators if present
- replace/tailor content without flattening styles
```

If the MCP tools cannot preserve styling, the worker should document the limitation in:

```text
output/claim_audit.md
output/ats_audit.md
```

## New Output: template_fidelity_audit.md

Add a new output file:

```text
output/template_fidelity_audit.md
```

Preferred: make it required for successful tailoring and revision runs.

If changing required outputs is too disruptive, make it optional for one task and required in a follow-up.

The audit should include:

```text
# Template Fidelity Audit

## Source Template
- Source DOCX:
- Tailored DOCX:

## Formatting Preservation Checklist
| Feature | Source had it? | Output preserved it? | Notes |
| --- | --- | --- | --- |
| Centered name/header block | yes/no | yes/no | ... |
| Centered contact line | yes/no | yes/no | ... |
| Blue/colored section headings | yes/no | yes/no | ... |
| Horizontal divider lines | yes/no | yes/no | ... |
| Bullet lists | yes/no | yes/no | ... |
| Date alignment | yes/no | yes/no | ... |
| Margins | yes/no | yes/no | ... |
| Font family/size consistency | yes/no | yes/no | ... |
| Section spacing | yes/no | yes/no | ... |

## Known Deviations
- ...

## Remediation
- ...
```

## Backend Validation / Logging

Update worker logging:

```text
jobapply: source DOCX style preservation requested
jobapply: template fidelity audit expected at output/template_fidelity_audit.md
```

When `input/master_resume.docx` exists, the worker should explicitly tell Claude that template fidelity is required.

If `template_fidelity_audit.md` is required, update validation.

If optional for now, log a warning if missing.

## Revision Prompt Requirements

Update revision prompt too.

Revision runs should preserve:

```text
- current tailored resume style
- original master resume style
- bullet lists
- centered header
- colored headings
- separator lines
```

The revision prompt should say:

```text
Do not restyle the resume unless the user explicitly asks.
Apply requested content changes while preserving DOCX styling and layout.
```

Revision outputs should update:

```text
output/template_fidelity_audit.md
```

## Word Handoff Requirements

Update Claude for Word handoff prompt/instructions if present.

It should say:

```text
Preserve the master resume's existing visual style, including:
- centered name/contact header
- colored section headings
- separator lines
- fonts
- spacing
- margins
- bullet indentation
- date alignment

Use tracked changes if available.
Do not rebuild the document from scratch.
```

## Optional Deterministic DOCX Style Check

If practical, add a lightweight deterministic DOCX style inspection helper.

Suggested helper:

```text
backend/app/docx_style_audit.py
```

It may inspect:

```text
- whether first non-empty paragraph is centered
- whether early contact paragraph is centered
- whether section heading paragraphs use color
- whether document contains bullet/numbered list styles
- whether output has similar count of list paragraphs
```

Do not over-engineer full DOCX visual diffing.

Do not require Microsoft Word.

Use `python-docx` if already available.

This helper can support tests and future validation but does not need to be perfect.

## Tests

Add/update tests to prove:

1. Tailoring prompt says master DOCX is the formatting/template source of truth.
2. Tailoring prompt says to copy/edit source DOCX instead of rebuilding when possible.
3. Tailoring prompt mentions preserving centered name/header block.
4. Tailoring prompt mentions preserving centered contact links.
5. Tailoring prompt mentions preserving blue/colored section headings.
6. Tailoring prompt mentions preserving horizontal separator lines.
7. Tailoring prompt mentions preserving bullet lists.
8. Tailoring prompt balances style preservation with ATS readability.
9. Tailoring prompt warns against critical content in headers/text boxes/images/complex tables.
10. Revision prompt says to preserve existing DOCX styling/layout.
11. Word handoff prompt says to preserve centered header, colored headings, separator lines, and bullets.
12. Worker log records template/style preservation requested when master_resume.docx exists.
13. Worker requests or validates `template_fidelity_audit.md`.
14. Existing ATS prompt tests still pass.
15. Existing DOCX extraction tests still pass.

If deterministic DOCX style helper is added, test with generated DOCX fixtures:

1. Source DOCX with centered first paragraph is detected.
2. Source DOCX with colored heading is detected.
3. Source DOCX with bullet list is detected.
4. Audit detects output missing bullets or centered header.

## Acceptance Criteria

- Tailoring harness treats master DOCX as template source of truth.
- Centered header/contact block preservation is explicitly required.
- Blue/colored section heading preservation is explicitly required.
- Horizontal separator preservation is explicitly required.
- Bullet list preservation is explicitly required.
- Revision harness preserves existing style.
- Word handoff instructions preserve style.
- Template fidelity audit is produced or requested.
- ATS readability remains intact.
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

1. Use a master resume DOCX with:
   - centered name
   - centered links
   - blue headings
   - horizontal separator
   - bullet lists
2. Generate a tailored resume.
3. Open:

```text
output/tailored_resume.docx
```

4. Confirm:
   - name/contact header remains centered
   - section heading color is preserved
   - horizontal lines are preserved
   - bullets remain bullets
   - date alignment is similar
   - margins/spacing look similar
   - content is tailored to the job

5. Open:

```text
output/template_fidelity_audit.md
```

6. Confirm deviations are listed honestly.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add DOCX template fidelity audit
```

Do not push.
