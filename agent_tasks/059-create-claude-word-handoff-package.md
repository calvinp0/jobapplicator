# Task 059: Create Claude for Word Handoff Package

## Goal

Add a backend service that prepares a Claude for Word handoff package for a tailoring run.

This is the semi-automated high-quality path:

```text
JobApplicator prepares a polished DOCX + prompt
user opens DOCX in Microsoft Word
user invokes Claude for Word
user saves final DOCX
JobApplicator imports it in a later task
```

Do not change frontend UI in this task.
Do not import the finished Word result in this task.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

Inspect:

```text
backend/app/run_directory.py
backend/app/main.py
backend/tests/test_run_directory.py
docs/contracts/claude_run_directory.md
docs/contracts/agent_orchestration.md
runtime_prompts/resume_tailoring.md
```

This task depends on the run metadata/status model from Task 058.

## Required Behavior

Add a backend service for creating:

```text
runs/<run_id>/word_handoff/
  01_resume_for_claude_word.docx
  02_prompt_for_claude_word.txt
  03_job_description.txt
  04_instructions.md
```

If the source resume DOCX exists, copy it to:

```text
word_handoff/01_resume_for_claude_word.docx
```

Accepted source names should include the current project’s actual input file names. Also support these common names if they do not conflict:

```text
input/resume.docx
input/base_resume.docx
input/original_resume.docx
```

If no DOCX exists but markdown exists, still create the prompt and instructions files. Do not fail merely because the DOCX is absent unless existing contracts require DOCX input.

Accepted markdown fallback names:

```text
input/resume.md
input/base_resume.md
input/original_resume.md
```

Accepted job description names should include current project names plus:

```text
input/job_description.md
input/job_description.txt
input/jd.md
input/jd.txt
```

## Prompt Requirements

Create `02_prompt_for_claude_word.txt` with instructions suitable for Claude for Word:

```text
Use this document as the source resume and tailor it for the target job.

Preserve the existing Word formatting:
- Keep fonts, margins, section spacing, headings, bullets, and page layout.
- Edit inside the resume rather than rebuilding the document from scratch.
- Use tracked changes if available.
- Do not invent employers, dates, degrees, technologies, metrics, publications, awards, responsibilities, or credentials.
- Only strengthen claims that are supported by the original resume.
- Prefer concise, high-signal bullets.

Edit these areas first:
1. Summary
2. Skills
3. Most relevant experience bullets
4. Project bullets if they match the job

After editing, add or update these sections at the end of the document:
CHANGE LOG
CLAIM AUDIT
```

The prompt must include the target job description text.

If a markdown version of the resume exists, include it as fallback context.

## Instructions File

Create `04_instructions.md` explaining the manual steps:

```text
1. Open 01_resume_for_claude_word.docx in Microsoft Word.
2. Open Claude for Word.
3. Paste the contents of 02_prompt_for_claude_word.txt.
4. Ask Claude to edit using tracked changes.
5. Save the completed file as ../output/word_tailored_resume.docx.
6. Return to JobApplicator and import the Word result.
```

Use paths relative to the run directory.

## Status Behavior

After successful handoff creation:

```text
tailoring_method = word_handoff
status = word_handoff_ready
```

The run log should record:

```text
jobapply: created Claude for Word handoff package
jobapply: handoff_dir=<path>
jobapply: expected Word output=output/word_tailored_resume.docx
```

Do not print secrets.

## Tests

Add/update tests to prove:

1. Handoff folder is created.
2. Source DOCX is copied when present.
3. Prompt file is created.
4. Prompt includes job description text.
5. Prompt includes formatting preservation instructions.
6. Instructions file is created.
7. Missing DOCX does not fail if markdown exists.
8. Metadata is updated to `tailoring_method=word_handoff`.
9. Status is updated to `word_handoff_ready`.
10. Run log records handoff creation.

Do not require Microsoft Word.
Do not require Claude for Word.
Do not require the real Claude binary.

## Acceptance Criteria

- Backend can create a Claude for Word handoff package.
- Package includes DOCX when available.
- Package includes prompt, job description, and instructions.
- Run status becomes `word_handoff_ready`.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_run_directory.py
pytest backend/tests/test_word_handoff.py
pytest
```

If `test_word_handoff.py` does not exist, create it.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add Claude for Word handoff package generation
```

Do not push.
