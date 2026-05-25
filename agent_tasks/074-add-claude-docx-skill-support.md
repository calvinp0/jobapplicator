# Task 058: Add Claude DOCX Skill Support to Auto Tailoring

## Goal

Improve the existing automatic Claude Code tailoring path so Claude Code can use Anthropic's DOCX document skill when generating polished Word resume outputs.

This task should make Auto mode better at producing:

```text
output/tailored_resume.docx
```

while preserving the current required outputs:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

Do not implement Claude for Word handoff in this task.
Do not change frontend UI.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

There is an Anthropic DOCX document skill:

```text
anthropics/docx-documents
```

The skill is intended for creating, reading, editing, and manipulating Word documents, including `.docx` files, professional formatting, headings, tables of contents, comments, tracked changes, templates, XML-level editing, and validation workflows.

Installation options mentioned by the skill page include:

```bash
npx mdskills install anthropics/docx-documents
```

Claude Code plugin installation options mentioned by the skill page include:

```text
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
```

Use the approach that is actually appropriate for this local project/environment.

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/tests/test_claude_worker.py
runtime_prompts/resume_tailoring.md
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
agent_tasks/queue.yaml
```

Also inspect current Claude Code/plugin/skill availability if needed:

```bash
claude --help
claude plugin --help
claude mcp --help
npx mdskills --help
```

Do not assume a command exists. Check what is actually available.

## Required Behavior

The automatic tailoring path should explicitly instruct Claude Code to use the DOCX document skill when generating or editing:

```text
output/tailored_resume.docx
```

The runtime prompt should say something equivalent to:

```text
Use the DOCX / Word document skill if available when creating output/tailored_resume.docx.
Preserve professional resume formatting.
Use real Word document structure rather than plain text dumped into a DOCX.
Validate that the DOCX opens and contains the tailored resume content.
```

The worker should continue to require all four outputs:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

Do not remove output validation.

## Skill Setup

Add project documentation for setting up the DOCX skill locally.

Create or update:

```text
docs/claude_docx_skill_setup.md
```

It should include:

```text
Option A: install via mdskills if available
npx mdskills install anthropics/docx-documents

Option B: install Claude Code document-skills plugin if available
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills

How to verify:
- Ask Claude Code to list available skills/plugins if supported
- Run one small local DOCX generation test if supported
```

The docs must be honest that available commands may vary by Claude Code version.

## Worker Logging

When launching Claude Code for tailoring, the run log should include:

```text
jobapply: DOCX skill requested for Word output generation
```

Do not claim the skill is definitely installed unless the worker actually detects it.

If detection is implemented, log one of:

```text
jobapply: DOCX skill appears available
jobapply: DOCX skill availability unknown
jobapply: DOCX skill not detected
```

Detection is optional if the installed Claude Code version does not expose a stable way to check skills.

## Prompt Contract Update

Update `runtime_prompts/resume_tailoring.md` so it says:

```text
When creating output/tailored_resume.docx, use the DOCX / Word document skill if available.
The DOCX must be a professional resume document, not a plain-text dump.
Preserve consistent heading styles, bullet indentation, margins, spacing, and readable typography.
If a source DOCX exists in input/, use it as a formatting reference when possible.
If DOCX generation fails, still write output/tailored_resume.md, output/change_log.md, and output/claim_audit.md, and explain the DOCX failure clearly in output/claim_audit.md.
```

Also preserve the non-interactive requirements from Task 057:

```text
Do not ask clarifying questions.
Do not wait for user input.
Make a best effort using provided input files.
Write the required output files exactly as specified.
```

## Fallback Behavior

If the DOCX skill is unavailable, the run should still attempt normal DOCX generation using the existing Claude Code path.

Do not fail early only because skill availability cannot be proven.

Validation remains responsible for deciding whether the run completed.

## Tests

Update tests so they prove:

1. The runtime tailoring prompt requests the DOCX / Word document skill.
2. The prompt says the DOCX must not be a plain-text dump.
3. The prompt says source DOCX should be used as a formatting reference when available.
4. The worker log records that DOCX skill usage was requested.
5. The worker still validates all four required outputs.
6. A fake Claude binary that writes all four outputs results in `completed`.
7. A fake Claude binary that omits DOCX still results in `failed`.
8. Tests do not require the real Claude binary or the real DOCX skill.

## Acceptance Criteria

- Auto mode prompts Claude Code to use the DOCX document skill when available.
- DOCX generation instructions are stronger and formatting-aware.
- Worker logs that DOCX skill usage was requested.
- Documentation explains how to install/verify the DOCX skill.
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

1. Install the DOCX skill or Claude Code document-skills plugin if available.
2. Start backend.
3. Open a job.
4. Click Generate draft.
5. Confirm run log contains:

```text
DOCX skill requested
```

6. Confirm successful run creates:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

7. Open `output/tailored_resume.docx` and confirm it is formatted like a resume, not a plain-text dump.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Claude DOCX skill support to tailoring
```

Do not push.
