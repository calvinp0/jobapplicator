# Task 078: Extract Master Resume DOCX Before Tailoring

## Goal

Support a master resume stored as a `.docx` file by extracting its visible text/structure before Claude Code tailoring runs.

The backend should preserve the DOCX as the formatting source while also creating a markdown/text extraction that Claude can use as a reliable semantic source.

Do not change frontend UI in this task.
Do not implement Gmail.
Do not implement LinkedIn automation.
Do not remove existing markdown resume support.

## Background

The user's master resume is currently a Word document.

The automatic tailoring path now has access to Claude Code MCP tooling:

```text
word-document-server connected
```

The Office Word MCP server should be used by Claude Code when available to read/copy/edit DOCX files.

However, the backend should not rely only on Claude successfully reading `.docx` at runtime. It should create a deterministic extracted text file before invoking Claude.

## Required Input Support

Support source resume DOCX files under `input/`, including current project names plus these common names:

```text
input/master_resume.docx
input/resume.docx
input/base_resume.docx
input/original_resume.docx
```

Do not break existing support for:

```text
input/master_resume.md
input/resume.md
input/base_resume.md
input/original_resume.md
```

## Required Behavior

Before launching Claude Code tailoring, the backend should check for a source resume DOCX.

If found, extract visible text and basic structure into:

```text
input/master_resume_extracted.md
```

or, if the project naming convention prefers another name:

```text
input/resume_extracted.md
```

Use one consistent name and document it.

The extracted markdown should include:

```text
# Extracted Master Resume

Source DOCX: input/<filename>.docx

## Extracted Text

...
```

If headings or paragraphs can be detected, preserve them reasonably.

If tables are present, extract table contents in a readable markdown-like format.

If extraction fails, write:

```text
input/master_resume_extraction_error.md
```

and continue only if another usable resume source exists.

Do not silently ignore extraction failure.

## Extraction Implementation

Use a deterministic backend-side extractor.

Acceptable options:

```text
python-docx
mammoth
pandoc
LibreOffice conversion
existing project utilities
```

Prefer the simplest dependency already available in the project.

If adding a dependency, update the appropriate dependency file.

Do not require Microsoft Word.

Do not require Claude Code or MCP for backend extraction tests.

## Claude Prompt Update

Update the runtime tailoring prompt so it says:

```text
The source resume may be provided as a DOCX file in input/.

If a source DOCX exists:
- use Office Word MCP tools through word-document-server if available to inspect/copy/edit the DOCX
- use the DOCX as the formatting source and editable base
- preserve margins, fonts, headings, bullet indentation, spacing, and layout where possible

Also read the extracted markdown file:
input/master_resume_extracted.md

Use the extracted markdown as the reliable evidence source for claims.
Use the DOCX as the formatting/layout source.
Do not invent claims that are not supported by the source resume or extracted markdown.
Do not rebuild the DOCX from scratch unless copying/editing the source DOCX fails.
```

Preserve non-interactive constraints:

```text
Do not ask clarifying questions.
Do not wait for user input.
Make a best effort.
Write the required output files exactly as specified.
```

## Output Requirements

Required Claude outputs remain:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

Do not remove output validation.

## Run Log

The run log should record:

```text
jobapply: checking for master resume DOCX
jobapply: found source resume DOCX=input/<filename>.docx
jobapply: extracted source resume DOCX to input/master_resume_extracted.md
```

If extraction fails:

```text
jobapply: failed to extract source resume DOCX
```

Do not print secrets.

## Tests

Add/update tests to prove:

1. Backend detects `input/master_resume.docx`.
2. Backend extracts visible text into `input/master_resume_extracted.md`.
3. Extracted markdown includes the source DOCX filename.
4. Existing markdown-only resume input still works.
5. Extraction failure is logged.
6. Extraction failure does not silently pass if no other resume source exists.
7. Runtime prompt references `input/master_resume_extracted.md`.
8. Runtime prompt tells Claude to use `word-document-server` for DOCX when available.
9. Worker still validates all four required outputs.
10. Tests do not require Microsoft Word, Claude Code, or a real MCP server.

Use a generated minimal DOCX fixture in tests rather than committing a large binary fixture if possible.

## Acceptance Criteria

- Master resume DOCX is supported as a first-class input.
- Backend creates extracted markdown before Claude tailoring.
- Claude prompt distinguishes DOCX formatting source from markdown evidence source.
- Existing markdown resume support still works.
- Output validation remains unchanged.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_run_directory.py
pytest
```

Manual verification:

1. Put master resume at:

```text
runs/<run_id>/input/master_resume.docx
```

2. Start a tailoring run.
3. Confirm this file is created:

```text
runs/<run_id>/input/master_resume_extracted.md
```

4. Confirm run log includes:

```text
found source resume DOCX
extracted source resume DOCX
```

5. Confirm Claude outputs:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

6. Open the tailored DOCX and confirm it preserves resume-like formatting.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Extract master resume DOCX before tailoring
```

Do not push.
