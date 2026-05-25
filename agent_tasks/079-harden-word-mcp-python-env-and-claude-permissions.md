# Task 079: Harden Word MCP Python Environment and Claude Code Permissions

## Goal

Make the Office Word MCP integration reliable for backend non-interactive tailoring runs.

The Word MCP server is a Python program. Claude Code must launch it with a deterministic Python interpreter, preferably a dedicated virtualenv or conda environment, not an ambiguous system `python`, `python3`, or PATH-dependent interpreter.

Claude Code must also run tailoring jobs without interactive permission prompts, tool approval prompts, or clarifying questions.

Do not change frontend UI in this task.  
Do not implement Gmail.  
Do not implement LinkedIn automation.  
Do not change application tracking UI.  
Do not remove existing output validation.

## Background

Office Word MCP was successfully connected in Claude Code:

```text
word-document-server connected · 82 tools
```

The server entry point in the local clone was found as:

```text
./word_mcp_server.py
```

Because this server runs with Python, the MCP registration should point to an explicit interpreter such as:

```text
<WORD_MCP_DIR>/.venv/bin/python
```

or a conda interpreter such as:

```text
<CONDA_PREFIX_FOR_WORD_MCP>/bin/python
```

Do not rely on:

```text
python
python3
```

unless there is no better option and the docs clearly warn about the risk.

## Inspect

Inspect:

```text
backend/app/claude_worker.py
backend/app/run_directory.py
backend/tests/test_claude_worker.py
backend/tests/test_run_directory.py
runtime_prompts/resume_tailoring.md
docs/office_word_mcp_setup.md
docs/install.md
README_INSTALL.md
agent_tasks/queue.yaml
```

Also inspect local Claude Code help:

```bash
claude --help
claude mcp --help
claude mcp add --help
```

Use the actual installed Claude Code behavior. Do not guess unsupported flags.

## Required Documentation Updates

Update the install/MCP docs to recommend a dedicated Python environment for Word MCP.

Document both supported approaches:

```text
Option A: virtualenv
Option B: conda
```

The documentation must be portable across Linux, macOS, and Windows.

Do not hardcode user-specific paths such as:

```text
/home/calvin/...
C:\Users\Calvin\...
```

Documentation may show examples, but primary commands must use portable placeholders or variables.

Use placeholders such as:

```text
<WORD_MCP_DIR>
<WORD_MCP_PYTHON>
<WORD_MCP_SERVER>
```

and shell variables such as:

```text
$HOME
$WORD_MCP_DIR
$WORD_MCP_PYTHON
$WORD_MCP_SERVER
```

For Windows PowerShell, use:

```text
$HOME
$WORD_MCP_DIR
$WORD_MCP_PYTHON
$WORD_MCP_SERVER
```

## Option A: virtualenv Setup

Document Linux/macOS:

```bash
WORD_MCP_DIR="$HOME/code/mcp/Office-Word-MCP-Server"

mkdir -p "$(dirname "$WORD_MCP_DIR")"
cd "$(dirname "$WORD_MCP_DIR")"

git clone https://github.com/frastlin/Office-Word-MCP-Server.git
cd "$WORD_MCP_DIR"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
pip install -r requirements.txt

WORD_MCP_PYTHON="$WORD_MCP_DIR/.venv/bin/python"
WORD_MCP_SERVER="$WORD_MCP_DIR/word_mcp_server.py"

echo "$WORD_MCP_PYTHON"
echo "$WORD_MCP_SERVER"

test -x "$WORD_MCP_PYTHON"
test -f "$WORD_MCP_SERVER"
```

Document Windows PowerShell:

```powershell
$WORD_MCP_DIR = "$HOME\code\mcp\Office-Word-MCP-Server"

New-Item -ItemType Directory -Force -Path (Split-Path $WORD_MCP_DIR)
Set-Location (Split-Path $WORD_MCP_DIR)

git clone https://github.com/frastlin/Office-Word-MCP-Server.git
Set-Location $WORD_MCP_DIR

py -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install -U pip
pip install -r requirements.txt

$WORD_MCP_PYTHON = "$WORD_MCP_DIR\.venv\Scripts\python.exe"
$WORD_MCP_SERVER = "$WORD_MCP_DIR\word_mcp_server.py"

Write-Host $WORD_MCP_PYTHON
Write-Host $WORD_MCP_SERVER

Test-Path $WORD_MCP_PYTHON
Test-Path $WORD_MCP_SERVER
```

Mention Windows execution-policy fix if activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Option B: conda Setup

Document Linux/macOS:

```bash
WORD_MCP_DIR="$HOME/code/mcp/Office-Word-MCP-Server"

mkdir -p "$(dirname "$WORD_MCP_DIR")"
cd "$(dirname "$WORD_MCP_DIR")"

git clone https://github.com/frastlin/Office-Word-MCP-Server.git
cd "$WORD_MCP_DIR"

conda create -n word-mcp python=3.11 -y
conda activate word-mcp

python -m pip install -U pip
pip install -r requirements.txt

WORD_MCP_PYTHON="$(python -c 'import sys; print(sys.executable)')"
WORD_MCP_SERVER="$WORD_MCP_DIR/word_mcp_server.py"

echo "$WORD_MCP_PYTHON"
echo "$WORD_MCP_SERVER"

test -x "$WORD_MCP_PYTHON"
test -f "$WORD_MCP_SERVER"
```

Document Windows PowerShell:

```powershell
$WORD_MCP_DIR = "$HOME\code\mcp\Office-Word-MCP-Server"

New-Item -ItemType Directory -Force -Path (Split-Path $WORD_MCP_DIR)
Set-Location (Split-Path $WORD_MCP_DIR)

git clone https://github.com/frastlin/Office-Word-MCP-Server.git
Set-Location $WORD_MCP_DIR

conda create -n word-mcp python=3.11 -y
conda activate word-mcp

python -m pip install -U pip
pip install -r requirements.txt

$WORD_MCP_PYTHON = python -c "import sys; print(sys.executable)"
$WORD_MCP_SERVER = "$WORD_MCP_DIR\word_mcp_server.py"

Write-Host $WORD_MCP_PYTHON
Write-Host $WORD_MCP_SERVER

Test-Path $WORD_MCP_PYTHON
Test-Path $WORD_MCP_SERVER
```

Explain:

```text
Use the explicit virtualenv or conda Python path.
Do not rely on python or python3 from PATH in the Claude Code MCP registration.
Use a dedicated environment such as word-mcp.
Do not reuse the JobApplicator backend env unless intentionally maintaining them together.
```

## Claude Code MCP Registration Documentation

Document the Claude Code MCP registration using the resolved variables.

Linux/macOS:

```bash
claude mcp add word-document-server -- \
  "$WORD_MCP_PYTHON" \
  "$WORD_MCP_SERVER"
```

If this syntax is not supported by the installed Claude Code version, document the version-supported syntax discovered from:

```bash
claude mcp add --help
```

Also include the possible alternate form if appropriate:

```bash
claude mcp add word-document-server \
  "$WORD_MCP_PYTHON" \
  "$WORD_MCP_SERVER"
```

Windows PowerShell:

```powershell
claude mcp add word-document-server -- `
  "$WORD_MCP_PYTHON" `
  "$WORD_MCP_SERVER"
```

If this syntax is not supported, document the supported syntax from:

```powershell
claude mcp add --help
```

Verification:

```text
Open Claude Code.
Run /mcp.
Confirm:
  word-document-server connected
```

The docs should mention the observed successful state:

```text
word-document-server connected · 82 tools
```

## Smithery Troubleshooting

Document that Smithery one-click install was not reliable locally.

Include:

```bash
npx -y @smithery/cli install @GongRzhe/Office-Word-MCP-Server --client claude
```

Observed failure:

```text
No connection configuration found for server
```

And:

```bash
npx -y @smithery/cli install @frastlin/Office-Word-MCP-Server --client claude
```

Observed failure:

```text
404 {"error":"Server not found"}
```

Recommend manual frastlin clone plus explicit Claude Code MCP registration instead.

## Claude Code Permission Requirements

Update the backend worker and docs so non-interactive runs cannot hang on permission prompts.

The worker should inspect/use the local Claude Code CLI’s supported non-interactive and permission options.

The run log should record:

```text
jobapply: launching Claude Code in non-interactive mode
jobapply: permission mode=<mode>
jobapply: MCP Word tools may be used by Claude Code if available
```

The exact permission mode should be whatever the installed Claude Code supports.

The worker must not use an interactive Claude command from the backend.

If Claude Code supports explicit allowed tools, configure or document allowing:

```text
word-document-server tools
file read/write tools required for the run directory
shell/file operations needed to write output files
```

If Claude Code supports a backend-safe permission bypass flag, use it only if project policy accepts it and document the tradeoff.

Do not hardcode a flag without confirming it exists in:

```bash
claude --help
```

## Runtime Prompt Requirements

Ensure `runtime_prompts/resume_tailoring.md` says:

```text
You are running inside a non-interactive backend job.
Do not ask clarifying questions.
Do not wait for user input.
Do not ask the user whether to apply changes.
Do not ask for permission to edit the resume.
The task contract already grants permission to create and edit files inside this run directory.
Only write inside this run directory.
Use the provided files and make a best effort.
If a tool is unavailable, use another available method.
If DOCX/MCP editing fails, write the markdown/audit outputs and clearly document the DOCX failure.
```

The prompt should also preserve the Word MCP instructions:

```text
When creating output/tailored_resume.docx, prefer Office Word MCP tools through word-document-server if available.

If input/ contains a source resume DOCX:
- copy it as the editable base when possible
- preserve the original margins, fonts, headings, bullet indentation, spacing, and layout
- edit relevant text in place rather than rebuilding the entire document from scratch

If no source DOCX exists:
- create a professional resume DOCX using Word MCP tools or DOCX skill
- use real Word headings, paragraphs, and bullet structures
- do not create a plain-text dump inside a DOCX
```

The required output files remain:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

Do not remove output validation.

## Failure Handling

If Claude exits successfully but writes no required files, preserve existing validation behavior and mark the run failed.

If Claude output/log contains obvious permission-blocked text, surface a helpful failure message in the run log such as:

```text
jobapply: Claude Code appears to have been blocked by a permission/tool approval prompt
```

Examples of suspicious text may include:

```text
permission
approval
allowed
allow tool
do you want me to
should I
would you like me to
```

Do not rely only on this heuristic. Missing-output validation remains the source of truth.

## Tests

Update tests to prove:

1. Docs recommend explicit virtualenv Python for Word MCP.
2. Docs recommend explicit conda Python for Word MCP.
3. Docs warn not to rely on system `python` or `python3`.
4. Docs avoid hardcoded user-specific home paths like `/home/calvin`.
5. Docs include Linux/macOS path verification commands.
6. Docs include Windows PowerShell path verification commands.
7. Docs include Claude Code MCP registration with variables/placeholders.
8. Runtime prompt says not to ask permission or clarifying questions.
9. Runtime prompt says the run contract grants permission to edit files inside the run directory.
10. Runtime prompt says to only write inside the run directory.
11. Worker log records non-interactive launch mode.
12. Worker log records permission mode.
13. Worker still passes prompt text, not just prompt path.
14. Fake Claude writing all required files completes.
15. Fake Claude writing no files fails.
16. Tests do not require a real MCP server or real Claude Code.

## Acceptance Criteria

- Word MCP docs explain virtualenv and conda setup.
- MCP docs recommend explicit interpreter path.
- MCP docs avoid hardcoded user-specific paths in primary commands.
- Linux/macOS and Windows examples use portable variables/placeholders.
- Linux/macOS and Windows examples include path verification commands.
- Runtime prompt blocks clarifying and permission questions.
- Runtime prompt states the run contract grants permission to edit files inside the run directory.
- Backend worker records non-interactive mode and permission mode.
- Backend worker does not use interactive Claude invocation.
- Existing output validation remains.
- Tests pass.

## Verification

Run:

```bash
pytest backend/tests/test_claude_worker.py
pytest backend/tests/test_run_directory.py
pytest
```

Manual verification:

1. Confirm Claude Code MCP config points to an explicit Python interpreter, such as:

```text
<WORD_MCP_DIR>/.venv/bin/python
```

or:

```text
<CONDA_PREFIX_FOR_WORD_MCP>/bin/python
```

On Windows this should be something like:

```text
<WORD_MCP_DIR>\.venv\Scripts\python.exe
```

or:

```text
<CONDA_PREFIX_FOR_WORD_MCP>\python.exe
```

2. In Claude Code, run:

```text
/mcp
```

3. Confirm:

```text
word-document-server connected
```

4. Run a backend tailoring job.

5. Confirm run does not ask:

```text
whether to apply changes
whether to edit files
whether to continue
whether to use a tool
```

6. Confirm required outputs are either created or the run fails with a concrete non-interactive error:

```text
output/tailored_resume.md
output/tailored_resume.docx
output/change_log.md
output/claim_audit.md
```

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Harden Word MCP environment and Claude permissions
```

Do not push.
