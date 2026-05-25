# Task 062: Add Frontend Controls for Auto and Claude for Word Modes

## Goal

Update the frontend so users can choose between:

```text
Generate Automatically
Prepare for Claude for Word
```

The existing Claude Code generation path should remain the default.

The Claude for Word path should call the backend handoff endpoints and show clear manual instructions.

Do not implement Gmail.
Do not implement LinkedIn automation.
Do not automate Microsoft Word.
Do not automate Claude for Word UI.

## Background

Inspect:

```text
frontend/
backend/app/main.py
docs/contracts/agent_orchestration.md
docs/contracts/claude_run_directory.md
```

This task depends on Task 061.

## Required UI Behavior

Add two visible actions where the user currently generates a draft/resume:

```text
Primary button:
Generate Automatically

Secondary button:
Prepare for Claude for Word
```

The default/primary action should preserve the current auto generation behavior.

The Word handoff action should:

```text
1. Call POST /api/runs/{run_id}/word-handoff
2. Display the returned handoff file paths
3. Display the prompt text or a "copy prompt" control
4. Display the instructions markdown
5. Show the expected save path:
   output/word_tailored_resume.docx
6. Provide an "Import Word Result" button
```

The import button should call:

```text
POST /api/runs/{run_id}/import-word-result
```

If the result is missing, show:

```text
Waiting for Word result.
Save the completed document as output/word_tailored_resume.docx, then click Import again.
```

If import succeeds, show the final resume download option.

## UX Requirements

The UI should make the flow obvious:

```text
Step 1: Open the prepared DOCX in Word
Step 2: Open Claude for Word
Step 3: Paste the generated prompt
Step 4: Save as output/word_tailored_resume.docx
Step 5: Click Import Word Result
```

If no source DOCX is available, show a warning but still show the prompt/instructions if the backend created them.

Do not expose secrets.
Do not expose absolute filesystem paths if the existing UI avoids them.

## Tests

Add/update frontend tests if the project has them.

Tests should prove:

1. Existing auto generation button still works.
2. Word handoff button calls the handoff endpoint.
3. Prompt/instructions are displayed after handoff creation.
4. Import button calls import endpoint.
5. Missing Word result message is displayed.
6. Successful import shows final resume/download state.

If the project currently has no frontend tests, add a short manual verification section to the relevant docs instead of creating a new frontend test framework.

## Acceptance Criteria

- User can still use fully automated generation.
- User can create a Claude for Word handoff.
- UI shows prompt/instructions.
- UI shows expected save path.
- User can import Word result.
- Successful import exposes final resume download.
- Existing frontend build passes.

## Verification

Run:

```bash
cd frontend
npm test -- --run
npm run build
```

If the project uses different commands, use the existing project-standard commands.

Also run backend tests:

```bash
pytest
```

Manual verification:

1. Start backend.
2. Start frontend.
3. Open a job.
4. Click Generate Automatically.
5. Confirm current auto path still works.
6. Click Prepare for Claude for Word.
7. Confirm prompt/instructions appear.
8. Save a dummy nonempty DOCX at the expected output path.
9. Click Import Word Result.
10. Confirm final resume appears.

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add frontend controls for Word handoff tailoring
```

Do not push.
