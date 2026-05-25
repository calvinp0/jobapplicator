# Claude DOCX Skill Setup

The auto tailoring path asks Claude Code to use Anthropic's DOCX document
skill (`anthropics/docx-documents`) when generating
`output/tailored_resume.docx`. The skill helps Claude produce a real Word
document with professional formatting (headings, bullet indentation,
margins, spacing) rather than a plain-text dump shoved into a `.docx`.

This document describes how to install and verify the skill locally.
Available commands vary by Claude Code version; not every install path
below will work in every environment. Try Option A first and fall back to
Option B if it is not available.

## Option A: install via `mdskills`

If the `mdskills` CLI is available on your machine (the skill page lists
it as the canonical install path), run:

```bash
npx mdskills install anthropics/docx-documents
```

This pulls the published skill and registers it for Claude Code to pick
up automatically on the next run.

## Option B: install the Claude Code `document-skills` plugin

If your Claude Code build supports the plugin marketplace (`/plugin`
commands inside an interactive Claude Code session), run, from an
interactive Claude Code session:

```text
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
```

The marketplace command registers Anthropic's skills marketplace; the
install command pulls the `document-skills` bundle (which includes the
DOCX skill).

## How to verify

The commands available to verify skill installation vary by Claude Code
version. Try, in order, whichever your build supports:

1. From an interactive Claude Code session, ask Claude Code to list its
   available skills/plugins, e.g.:

   ```text
   /plugin list
   ```

   The `document-skills` plugin (or `docx-documents` skill) should appear
   if Option B succeeded.

2. If your Claude Code build does not expose a stable listing command,
   run a small local DOCX generation prompt and confirm the resulting
   `.docx` opens in Word/LibreOffice with proper headings and bullets
   instead of a plain-text wall.

3. Run an end-to-end tailoring run via this project's backend and open
   `runs/<run_id>/output/tailored_resume.docx`. The file should be a
   real Word document with consistent heading styles, bullet indentation,
   and readable typography — not a single block of plain text.

## What the worker does

The backend worker (`backend/app/claude_worker.py`) does not attempt to
prove that the skill is installed. As of task 075, it logs that
Word/DOCX tooling was requested and that both the Office Word MCP
server and the DOCX skill were requested *if available*:

```text
jobapply: Word/DOCX tooling requested for DOCX generation
jobapply: Office Word MCP server requested if available
jobapply: DOCX skill requested if available
jobapply: Office Word MCP availability unknown
jobapply: DOCX skill availability unknown
```

The runtime prompt (`runtime_prompts/resume_tailoring.md`) instructs
Claude to prefer the Office Word MCP server
(`word-document-server`) first, then the DOCX / Word document skill,
then existing fallback DOCX generation. It must still produce the other
three required outputs (`tailored_resume.md`, `change_log.md`,
`claim_audit.md`) and explain any DOCX failure in `claim_audit.md` if
generation fails.

If neither the MCP nor the skill is installed, runs still attempt
normal DOCX generation through the existing Claude Code path; the
worker's output validation is what ultimately decides whether the run
completed.

For the Office Word MCP setup details, see
[`docs/office_word_mcp_setup.md`](office_word_mcp_setup.md).
