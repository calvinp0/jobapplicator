# Task 075: Add Claude Code Office Word MCP Support for DOCX Tailoring

## Goal

Update the automatic resume tailoring path so Claude Code explicitly uses the connected Office Word MCP server when available.

The current Claude Code environment now shows:

```text
word-document-server connected
82 tools
```

This server should be treated as the preferred DOCX manipulation path for Auto mode.

Do not implement Google Docs in this task.
Do not implement Claude for Word handoff in this task.
Do not change frontend UI.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

The Office Word MCP server exposes Word document operations including:

```text
create_document
copy_document
get_document_text
get_document_outline
add_heading
add_paragraph
add_table
add_picture
search_and_replace
format_text
create_custom_style
replace_with_track_changes
insert_after_with_track_changes
insert_before_with_track_changes
list_revisions
accept_revision
reject_revision
add_comment
get_all_comments
convert_to_pdf
```

The local Claude Code MCP screen shows:

```text
Local MCPs
word-document-server connected · 82 tools
```

This means Claude Code can use the Word MCP tools in the project environment.

## Inspect

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
runtime_prompts/resume_tailoring.md
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
docs/claude_docx_skill_setup.md
agent_tasks/queue.yaml
```

Also inspect Claude Code MCP command behavior if needed:

```bash
claude mcp --help
claude mcp list
```

Do not assume exact command output in tests.

## Required Behavior

Update the automatic tailoring prompt so it tells Claude Code to use available Word/DOCX tooling in this priority order:

```text
1. Office Word MCP tools through word-document-server, if available
2. DOCX / Word document skill, if available
3. Existing fallback DOCX generation behavior
```

The prompt should say something equivalent to:

```text
When creating output/tailored_resume.docx, prefer the Office Word MCP server if available.

If input/ contains a source resume DOCX:
- copy it as the editable base when possible
- preserve the original margins, fonts, headings, bullet indentation, and spacing
- edit relevant text in place rather than rebuilding the entire document from scratch

If no source DOCX exists:
- create a professional resume DOCX using Word MCP tools or DOCX skill
- use real Word headings, paragraphs, and bullet structures
- do not create a plain-text dump inside a DOCX

Always validate that output/tailored_resume.docx exists and has nonzero size.
```

Preserve the non-interactive constraints from Task 057:

```text
You are running inside a non-interactive backend job.
Do not ask clarifying questions.
Do not wait for user input.
Make a best effort using the provided input files.
Write the required output files exactly as specified.
```

The required output files remain:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

Do not remove output validation.

## Worker Logging

Update the Claude worker run log to include:

```text
jobapply: Word/DOCX tooling requested for DOCX generation
jobapply: Office Word MCP server requested if available
jobapply: DOCX skill requested if available
```

If the worker can cheaply detect MCP availability using a stable command, it may log one of:

```text
jobapply: Office Word MCP appears available
jobapply: Office Word MCP availability unknown
jobapply: Office Word MCP not detected
```

Detection is optional. Do not make tests depend on a real MCP server.

## Documentation

Create or update:

```text
docs/office_word_mcp_setup.md
```

Document:

```text
Manual frastlin fork install
Claude Code MCP registration
How to verify with /mcp
Expected connected server name: word-document-server
Expected capability: about 82 tools
Why this helps DOCX tailoring
How it differs from Claude for Word
How it differs from Google Docs
Known limitations
```

Include the local successful setup pattern:

```text
Clone frastlin fork.
Create Python virtualenv.
Install requirements.
Register word_mcp_server.py with Claude Code MCP.
Verify /mcp shows word-document-server connected.
```

Also document that Smithery was not reliable locally:

```text
@GongRzhe/Office-Word-MCP-Server failed with no connection configuration.
@frastlin/Office-Word-MCP-Server failed with 404 server not found.
```

## Google Docs Note

Add a short section to the docs:

```text
Google Docs MCP is not part of the core Auto DOCX path.

Google Docs may be useful later for:
- collaborative review
- cloud storage
- comments
- sharing drafts
- exporting reviewed documents

But for resume application artifacts, DOCX/PDF remains the primary target, so Office Word MCP is the better first integration.
```

Do not add Google Docs code in this task.

## Tests

Update tests so they prove:

1. The runtime tailoring prompt mentions `word-document-server`.
2. The runtime tailoring prompt prioritizes Office Word MCP before fallback DOCX generation.
3. The prompt says to copy/edit source DOCX as a base when available.
4. The prompt says not to produce a plain-text dump DOCX.
5. The prompt preserves the non-interactive constraints.
6. The worker log records Word/DOCX tooling and Office Word MCP were requested.
7. The worker still validates all four required outputs.
8. Fake Claude that writes all four outputs still completes.
9. Fake Claude that omits DOCX still fails.
10. Tests do not require an actual MCP server.

## Acceptance Criteria

- Auto tailoring prompt explicitly tells Claude Code to use `word-document-server` when available.
- Office Word MCP is documented as the preferred automatic DOCX manipulation path.
- Google Docs MCP is documented only as a possible future review/share workflow.
- Existing Auto mode still works without a real MCP server in tests.
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

1. In Claude Code, run:

```text
/mcp
```

2. Confirm:

```text
word-document-server connected
```

3. Start backend.
4. Run an auto tailoring job.
5. Confirm run log includes:

```text
Office Word MCP server requested
```

6. Confirm outputs exist:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

7. Open `output/tailored_resume.docx`.
8. Confirm it is a formatted Word resume, not a plain-text dump.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Claude Code Office Word MCP support
```

Do not push.
