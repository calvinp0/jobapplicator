# Task 112: Fix Claude for Word Handoff State and File Links

## Goal

Fix the Claude for Word handoff UI so it only shows handoff instructions and filenames after the handoff package actually exists.

Current observed issue:

```text
Tailoring in progress...
Recent activity:
  created Claude for Word handoff package
  handoff_dir=...
  expected word output=output/word_tailored_resume.docx

Claude for Word handoff prepared
1. Open 01_resume_for_claude_word.docx in Microsoft Word.
...
```

But while tailoring is still happening, the handoff directory/files may not exist yet, making the UI confusing.

Do not change Gmail behavior.
Do not change browser extension behavior.
Do not change resume tailoring logic except handoff packaging/state.
Do not remove automated tailoring.

## Background

The UI currently displays Claude for Word handoff instructions that reference:

```text
01_resume_for_claude_word.docx
02_prompt_for_claude_word.txt
output/word_tailored_resume.docx
```

but it does not clearly show:

```text
- whether the handoff package exists
- where the handoff folder is
- whether the source DOCX file exists
- whether the prompt file exists
- whether the expected Word output exists
```

The user tried to follow the instructions while tailoring was still running and found that the handoff directory did not exist.

## Inspect

Inspect:

```text
backend/app/word_handoff.py
backend/app/routers/
backend/app/claude_worker.py
backend/app/run_directory.py
backend/tests/test_word_handoff.py
backend/tests/test_claude_worker.py
frontend/src/pages/
frontend/src/components/
frontend/src/api/
frontend/src/test/
docs/contracts/claude_run_directory.md
docs/office_word_mcp_setup.md
```

Search:

```bash
rg "word_handoff|Claude for Word|01_resume_for_claude_word|word_tailored_resume|handoff_dir|Import Word Result|Prepare for Claude" backend frontend docs tests
```

## Required State Model

Represent the Claude for Word handoff with explicit states:

```text
not_prepared
preparing
prepared
missing_files
import_ready
imported
error
```

Suggested response shape:

```json
{
  "status": "prepared",
  "handoff_dir": "runs/<run_id>/word_handoff",
  "files": {
    "resume_docx": {
      "path": "word_handoff/01_resume_for_claude_word.docx",
      "exists": true
    },
    "prompt_txt": {
      "path": "word_handoff/02_prompt_for_claude_word.txt",
      "exists": true
    },
    "instructions_md": {
      "path": "word_handoff/03_instructions.md",
      "exists": true
    },
    "expected_output_docx": {
      "path": "output/word_tailored_resume.docx",
      "exists": false
    }
  },
  "message": "Claude for Word handoff is ready."
}
```

Use project conventions.

## Backend Requirements

Add or update endpoint to inspect handoff status.

Suggested endpoint:

```text
GET /api/runs/{run_id}/word-handoff/status
```

or existing route equivalent.

It should check filesystem existence, not only database/log state.

It should return:

```text
not_prepared
```

if the handoff folder does not exist.

It should return:

```text
missing_files
```

if the folder exists but required files are absent.

It should return:

```text
prepared
```

only if these exist:

```text
word_handoff/01_resume_for_claude_word.docx
word_handoff/02_prompt_for_claude_word.txt
word_handoff/03_instructions.md
```

It should return:

```text
import_ready
```

if:

```text
output/word_tailored_resume.docx
```

exists.

## Handoff Creation Requirements

The “Prepare for Claude for Word” action should synchronously or clearly asynchronously create:

```text
word_handoff/
word_handoff/01_resume_for_claude_word.docx
word_handoff/02_prompt_for_claude_word.txt
word_handoff/03_instructions.md
```

If creation is async, frontend must poll status.

If creation fails, show a clear error.

Do not show “prepared” until files exist.

## File Access Requirements

When prepared, UI should provide direct actions:

```text
Open source DOCX
Download source DOCX
Open prompt
Copy prompt
Open instructions
Open handoff folder path / copy path
```

Use existing file-open/download endpoints if available.

If direct file open is not supported, show exact absolute or project-relative path and copy buttons.

## UI Requirements

### Not prepared

Show:

```text
Claude for Word handoff is not prepared yet.
Prepare a handoff package to edit this resume manually in Word.
[Prepare for Claude for Word]
```

### Preparing

Show:

```text
Preparing Claude for Word handoff...
```

### Prepared

Show:

```text
Claude for Word handoff ready
Folder: runs/<run_id>/word_handoff

Files:
✓ 01_resume_for_claude_word.docx
✓ 02_prompt_for_claude_word.txt
✓ 03_instructions.md
```

Then show instructions.

### Missing files

Show:

```text
Claude for Word handoff folder exists, but required files are missing.
[Regenerate handoff package]
```

List missing files.

### Import ready

Show:

```text
Word result detected.
[Import Word Result]
```

### While automated tailoring is running

Do not claim handoff is prepared unless files exist.

If a handoff can be prepared during tailoring, show it separately:

```text
Automated tailoring is still running.
Claude for Word handoff: not prepared / prepared / import ready
```

If handoff cannot be prepared during tailoring, disable button and explain:

```text
Wait for tailoring to finish before preparing Word handoff.
```

Use actual backend constraints.

## Prompt Strength Requirements

When generating `02_prompt_for_claude_word.txt`, include:

```text
- target job title
- company
- job description
- evidence source summary/index
- claim/evidence rules
- ATS keyword instructions
- template/style preservation instructions
- requirement to edit the open document rather than rebuild from scratch
```

If full evidence contents are too large, include:

```text
evidence_sources_index.md
```

and key evidence summaries if available.

## Documentation

Update:

```text
docs/office_word_mcp_setup.md
docs/contracts/claude_run_directory.md
README_INSTALL.md
```

Document:

```text
what the handoff folder is
when it is created
where files are stored
how to open the source DOCX
how to paste prompt into Claude for Word
where to save the result
how to import result
```

## Tests

Add/update backend tests:

1. Handoff status returns `not_prepared` when folder is absent.
2. Handoff creation creates `word_handoff/`.
3. Handoff creation creates `01_resume_for_claude_word.docx`.
4. Handoff creation creates `02_prompt_for_claude_word.txt`.
5. Handoff creation creates `03_instructions.md`.
6. Status returns `prepared` only when required files exist.
7. Status returns `missing_files` when folder exists but required files are missing.
8. Status returns `import_ready` when `output/word_tailored_resume.docx` exists.
9. Prompt file includes job description and evidence/source references.
10. Prompt file includes style preservation instructions.

Add/update frontend tests if infrastructure exists:

1. UI shows not prepared when handoff folder absent.
2. UI does not show instructions when files are missing.
3. UI shows prepared instructions only when status is `prepared`.
4. UI lists handoff files with exists indicators.
5. UI shows import button only when output exists.
6. UI shows clear message while tailoring is in progress.

## Acceptance Criteria

- UI no longer says handoff is prepared before files exist.
- Handoff status is based on filesystem checks.
- User can see exact handoff folder path.
- User can access/copy paths for handoff files.
- Prompt file is stronger and includes job/evidence/style instructions.
- Import Word Result appears only when expected output exists.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_word_handoff.py
pytest backend/tests/test_claude_worker.py
pytest
cd frontend && npm run build
```

Manual verification:

1. Start a tailoring run.
2. Before preparing handoff, confirm UI says not prepared.
3. Click Prepare for Claude for Word.
4. Confirm UI does not say prepared until files exist.
5. Confirm folder exists:

```bash
ls runs/<run_id>/word_handoff
```

6. Confirm files exist:

```text
01_resume_for_claude_word.docx
02_prompt_for_claude_word.txt
03_instructions.md
```

7. Confirm UI shows the exact folder path.
8. Confirm Import Word Result appears only after:

```text
output/word_tailored_resume.docx
```

exists.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Fix Claude for Word handoff state
```

Do not push.
