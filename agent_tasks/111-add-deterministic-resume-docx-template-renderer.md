# Task 111: Add Deterministic Resume DOCX Template Renderer

## Goal

Stop relying on Claude Code / Word MCP to perfectly preserve DOCX formatting.

Use Claude for content tailoring and reasoning, then use a deterministic backend renderer to generate the final DOCX from a known resume template/style.

The core idea:

```text
Claude decides what text goes where.
Backend code decides how the DOCX looks.
```

Do not remove existing Claude Code tailoring.  
Do not remove Claude for Word handoff.  
Do not remove Word MCP support.  
Do not remove ATS optimization.  
Do not remove claim auditing.  
Do not change Gmail behavior.  
Do not change browser extension behavior.

## Background

The generated tailored DOCX has repeatedly lost formatting from the original master resume, including:

```text
- centered name/header block
- centered contact links
- horizontal separator lines
- bullet list formatting
- date alignment
- spacing rhythm
- clean section hierarchy
```

Even after prompt/harness changes telling Claude to preserve styling, the DOCX output still looks like a regenerated document rather than a faithful edit of the original template.

This suggests a limitation of relying on Claude Code / Word MCP as the final DOCX layout engine.

Instead, the app should move toward:

```text
1. Claude produces structured tailored resume content.
2. Backend validates the structure.
3. Backend renders the final DOCX deterministically using a fixed template/style.
4. Audits remain Claude-generated or backend-assisted.
```

## Inspect

Inspect:

```text
runtime_prompts/resume_tailoring.md
runtime_prompts/resume_revision.md
backend/app/claude_worker.py
backend/app/run_directory.py
backend/app/run_import.py
backend/app/docx_extract.py
backend/app/word_handoff.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
backend/tests/test_run_import.py
backend/tests/test_word_handoff.py
backend/tests/test_docx_extract.py
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/office_word_mcp_setup.md
frontend/src/pages/
frontend/src/api/
```

Search:

```bash
rg "tailored_resume.docx|tailored_resume.md|claim_audit|ats_audit|template_fidelity|Word MCP|DOCX|json|structured" runtime_prompts backend frontend docs tests
```

Use the existing project architecture.

## Desired Architecture

Current fragile path:

```text
Claude Code / Word MCP
  -> generates final output/tailored_resume.docx directly
```

New preferred path:

```text
Claude Code
  -> output/tailored_resume.json
  -> output/tailored_resume.md
  -> output/change_log.md
  -> output/claim_audit.md
  -> output/ats_audit.md
  -> output/recruiter_review.md if supported

Backend deterministic renderer
  -> output/tailored_resume.docx
  -> output/template_fidelity_audit.md
```

Word MCP / Claude for Word remains available as:

```text
manual fallback
experimental fallback
human-in-the-loop path
```

but should not be the only way to get formatted DOCX output.

## New Required Structured Output

Add a new structured output file:

```text
output/tailored_resume.json
```

The JSON should contain the tailored resume content in a stable schema.

Suggested schema:

```json
{
  "header": {
    "name": "Calvin Pieters",
    "contact_items": [
      "calvinpieters@gmail.com",
      "linkedin.com/in/calvin-pieters",
      "github.com/calvinp0",
      "Haifa, Israel"
    ],
    "subtitle": "Australian citizen currently based in Israel..."
  },
  "sections": [
    {
      "type": "summary",
      "heading": "PROFESSIONAL SUMMARY",
      "paragraphs": [
        "..."
      ]
    },
    {
      "type": "skills",
      "heading": "SKILLS",
      "groups": [
        {
          "label": "Languages",
          "items": ["Python", "SQL", "TypeScript", "Bash"]
        }
      ]
    },
    {
      "type": "experience",
      "heading": "EXPERIENCE",
      "entries": [
        {
          "title": "Agentic AI Developer Tooling",
          "organization": "Personal Project",
          "location": null,
          "dates": "2025 – Present",
          "subtitle": "Optional subtitle",
          "bullets": [
            "Built repo-aware developer tooling..."
          ]
        }
      ]
    },
    {
      "type": "education",
      "heading": "EDUCATION",
      "entries": [
        {
          "institution": "Technion – Israel Institute of Technology",
          "degree": "PhD Candidate, Chemical Engineering",
          "dates": "2023 – Present",
          "location": "Israel"
        }
      ]
    },
    {
      "type": "publications",
      "heading": "PUBLICATIONS",
      "items": [
        "..."
      ]
    }
  ],
  "metadata": {
    "target_company": "...",
    "target_job_title": "...",
    "generated_for_ats": true
  }
}
```

The exact schema can be adjusted, but it must be:

```text
stable
documented
testable
sufficient to render a resume with bullets, dates, headings, and contact header
```

## Prompt Requirements

Update the tailoring prompt so Claude must write:

```text
output/tailored_resume.json
```

The prompt should say:

```text
The JSON is the source of truth for deterministic DOCX rendering.
Use the JSON schema exactly.
Do not omit required fields.
Do not include unsupported claims.
Keep bullets as separate bullet strings.
Keep section entries structured.
Do not encode layout instructions in prose.
```

Claude should still write:

```text
output/tailored_resume.md
output/change_log.md
output/claim_audit.md
output/ats_audit.md
output/recruiter_review.md if applicable
```

The prompt should say:

```text
The backend will render output/tailored_resume.docx from output/tailored_resume.json using the resume template.
```

If Claude also generates a DOCX through Word MCP, treat it as:

```text
optional/fallback
```

not the source of truth.

## Renderer Requirements

Add a backend renderer.

Suggested file:

```text
backend/app/resume_docx_renderer.py
```

Responsibilities:

```text
load output/tailored_resume.json
validate schema
render output/tailored_resume.docx
write output/template_fidelity_audit.md
```

Use the existing dependency stack if possible.

Acceptable tools:

```text
python-docx
docxtpl
custom python-docx renderer
```

Do not require Microsoft Word.

Do not require LibreOffice for DOCX generation.

## Template Style Requirements

The renderer should produce a DOCX with the user’s desired resume style:

```text
centered name
centered contact line
small subtitle line
blue section headings
horizontal separator line under header or section headings if template uses it
professional font
consistent margins
consistent paragraph spacing
proper bullet lists
date alignment where practical
```

At minimum, implement a stable professional style close to the master resume:

```text
- name centered, large, blue
- contact line centered
- subtitle centered/small
- section headings uppercase and blue
- simple horizontal separator line after header or before major sections
- experience entries with bold title and right-aligned dates if practical
- bullets as real Word bullets
```

If exact date right-alignment is complex, implement a reasonable deterministic approximation and document it in `template_fidelity_audit.md`.

## Template Source Options

Support one or both approaches:

### Option A: Code-defined template

Use python-docx to create the resume document from scratch with fixed style rules.

This is simplest and testable.

### Option B: DOCX template file

Use a template file such as:

```text
candidate_context/templates/resume_template.docx
```

or:

```text
backend/app/templates/resume_template.docx
```

Do not commit user-private resume templates unless they are generic and safe.

If using a template file, document where users can place their own local template.

Preferred for this task:

```text
Option A first
```

because it is easier to test and avoids private template files in git.

## Backend Worker Integration

After Claude finishes, worker should:

```text
1. validate required text/audit outputs
2. validate output/tailored_resume.json
3. render output/tailored_resume.docx deterministically from JSON
4. validate output/tailored_resume.docx exists
5. write output/template_fidelity_audit.md
```

If Claude-generated DOCX already exists, the renderer may overwrite it or save a separate comparison artifact.

Preferred:

```text
output/tailored_resume.docx = deterministic renderer output
output/claude_generated_tailored_resume.docx = optional backup if Claude generated one
```

Only implement backup behavior if simple.

Run log should include:

```text
jobapply: structured resume JSON expected at output/tailored_resume.json
jobapply: rendering DOCX deterministically from structured resume JSON
jobapply: rendered output/tailored_resume.docx
```

## Validation Requirements

If `tailored_resume.json` is missing or invalid, fail the run with a clear error:

```text
expected output file missing: output/tailored_resume.json
```

or:

```text
invalid tailored resume JSON: <reason>
```

Do not silently fall back to generic DOCX rendering without structured data.

## Markdown Rendering

Keep `tailored_resume.md`.

It may be generated by Claude or rendered from JSON.

If feasible, render markdown from the same JSON to keep consistency.

If not, preserve Claude-generated markdown for now.

## Template Fidelity Audit

The renderer should write:

```text
output/template_fidelity_audit.md
```

Include:

```text
# Template Fidelity Audit

## Rendering Mode
Deterministic backend DOCX renderer.

## Preserved Style Features
- Centered name/header: yes
- Centered contact line: yes
- Blue section headings: yes
- Horizontal separators: yes/no
- Real bullet lists: yes
- Consistent margins: yes
- Consistent spacing: yes
- Date alignment: partial/full

## Known Limitations
- ...

## Notes
The DOCX was rendered from structured JSON rather than generated directly by Claude.
```

## Revision Flow Requirements

Revision runs should also produce/update:

```text
output/tailored_resume.json
```

The revision prompt should instruct Claude to revise the structured JSON as well as markdown/audits.

The backend should render revised DOCX from revised JSON.

Do not let revision DOCX fall back to generic Claude-generated output unless the deterministic renderer fails clearly.

## Frontend Requirements

If run/draft detail pages list artifacts, include:

```text
tailored_resume.json
template_fidelity_audit.md
```

If artifact display is generic, no frontend change may be needed.

If there is a run log/detail page, show:

```text
DOCX rendered deterministically
```

or equivalent if available.

## Documentation

Update:

```text
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/office_word_mcp_setup.md
README_INSTALL.md
```

Document:

```text
structured resume JSON
deterministic DOCX rendering
why Word MCP is no longer the primary formatting path
Word MCP/Claude for Word as fallback/manual path
template fidelity audit
```

## Tests

Add/update backend tests:

1. Tailoring prompt requests `output/tailored_resume.json`.
2. Tailoring prompt says JSON is source of truth for DOCX rendering.
3. Worker requires `tailored_resume.json`.
4. Invalid JSON fails with clear error.
5. Renderer creates `output/tailored_resume.docx` from minimal valid JSON.
6. Rendered DOCX contains centered name.
7. Rendered DOCX contains contact line.
8. Rendered DOCX contains blue/colored section headings if python-docx inspection allows.
9. Rendered DOCX uses real bullet paragraphs.
10. Rendered DOCX includes experience entries and dates.
11. Renderer writes `template_fidelity_audit.md`.
12. Worker logs deterministic DOCX rendering.
13. Revision prompt requests updated JSON.
14. Existing claim audit / ATS audit validation still passes.
15. Existing Word handoff tests still pass.

Add JSON schema tests if a schema module is introduced.

## Acceptance Criteria

- Claude produces structured `output/tailored_resume.json`.
- Backend renders `output/tailored_resume.docx` deterministically from JSON.
- DOCX has centered header/contact line, section styling, and real bullets.
- `template_fidelity_audit.md` is produced.
- Worker validates JSON and fails clearly if missing/invalid.
- Word MCP remains available as fallback/manual path.
- Revision flow supports structured JSON.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_run_directory.py
pytest backend/tests/test_run_import.py
pytest backend/tests/test_word_handoff.py
pytest
cd frontend && npm run build
```

Manual verification:

1. Generate a tailored draft.
2. Confirm outputs include:

```text
output/tailored_resume.json
output/tailored_resume.md
output/tailored_resume.docx
output/template_fidelity_audit.md
output/change_log.md
output/claim_audit.md
output/ats_audit.md
```

3. Open `output/tailored_resume.docx`.
4. Confirm:
   - name is centered
   - contact line is centered
   - section headings are blue/styled
   - bullets are real bullets
   - spacing is consistent
   - resume looks like a professional template
5. Open `template_fidelity_audit.md`.
6. Confirm it says DOCX was rendered deterministically from structured JSON.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add deterministic resume DOCX renderer
```

Do not push.
