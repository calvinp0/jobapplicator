# Task 077: Add Cross-Platform Install README

## Goal

Create a clear installation and setup guide for running JobApplicator on Linux, macOS, and Windows.

This should document:

```text
- backend setup
- frontend setup
- environment variables
- Claude Code setup
- Anthropic DOCX/document skill setup
- Office Word MCP setup
- platform-specific notes
- verification commands
```

Do not change application behavior in this task.
Do not change frontend UI.
Do not change backend logic unless needed to support docs.
Do not implement Gmail.
Do not implement LinkedIn automation.

## Background

The project currently runs locally with two commands similar to:

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

and:

```bash
cd frontend
VITE_API_BASE=http://localhost:8000 npm run dev -- --host localhost --port 5173
```

Claude Code is used by the backend worker to generate resume/application artifacts.

The project now also relies on optional but important document tooling:

```text
Anthropic DOCX / document skill
Office Word MCP server
```

The Office Word MCP server was successfully connected in Claude Code as:

```text
word-document-server connected · 82 tools
```

The previous Smithery install was unreliable locally:

```text
@GongRzhe/Office-Word-MCP-Server failed with "No connection configuration found for server"
@frastlin/Office-Word-MCP-Server failed with 404 "Server not found"
```

The reliable setup path was:

```text
clone the frastlin fork locally
create a Python virtualenv
install requirements
register word_mcp_server.py with Claude Code MCP
verify with /mcp
```

## Required Documentation

Create:

```text
README_INSTALL.md
```

or, if the project already has docs structure:

```text
docs/install.md
```

Use whichever convention fits the repo. If a top-level README already exists, link to this install guide from it.

## Content Requirements

The guide must include these sections.

### 1. Prerequisites

Document required tools:

```text
Python 3.10+ or project-required version
Node.js 20+ or project-required version
npm
Git
Claude Code
Claude account/login
```

Also mention optional tools:

```text
Microsoft Word, for Claude for Word/manual review flow
uv or uvx, if used
npx, for plugin tooling
```

### 2. Clone and Install

Document generic clone:

```bash
git clone <repo-url>
cd <repo>
```

Backend install should follow the project’s actual dependency manager.

If the backend uses requirements.txt:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For Windows PowerShell:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If the project uses Poetry, uv, pyproject, or another tool, document the actual commands instead.

Frontend install:

```bash
cd frontend
npm install
```

### 3. Run Locally

Document Linux/macOS:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
VITE_API_BASE=http://localhost:8000 npm run dev -- --host localhost --port 5173
```

Document Windows PowerShell equivalent:

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
$env:VITE_API_BASE="http://localhost:8000"
npm run dev -- --host localhost --port 5173
```

### 4. Environment Variables

Document any existing project environment variables.

At minimum include:

```text
VITE_API_BASE
ANTHROPIC_API_KEY, if used
CLAUDE_CODE-related environment assumptions, if used
```

Do not invent secrets. If a variable is unknown, write that the reader should copy from `.env.example` if present.

If `.env.example` does not exist, add a task note recommending one, but do not create fake values unless project convention supports it.

### 5. Claude Code Setup

Document:

```bash
claude
```

and login/authentication expectations.

Document how to verify Claude Code is available:

```bash
claude --version
claude --help
```

Document that Claude Code plugins/skills/MCP servers are local-machine configuration and must be reinstalled/reconfigured on each new Linux/macOS/Windows machine.

### 6. Anthropic DOCX / Document Skill Setup

Document that the DOCX/document skill is not guaranteed to follow the repo automatically on a new machine.

State clearly:

```text
When moving to a new machine, assume you must reinstall or re-enable the document/DOCX skill for Claude Code.
The runtime prompt can ask Claude to use the skill, but the project cannot guarantee it exists unless Claude Code has it installed.
```

Include both possible setup paths, marked as version-dependent:

```text
Claude Code plugin marketplace path:
  /plugin marketplace add anthropics/skills
  /plugin install document-skills@anthropic-agent-skills

mdskills path, if available:
  npx mdskills install anthropics/docx-documents
```

Document verification:

```text
Ask Claude Code whether document/DOCX skills are available.
Run a tiny DOCX generation test.
```

### 7. Office Word MCP Setup

Document the working local setup.

Use frastlin fork as preferred manual install:

```bash
mkdir -p ~/code/mcp
cd ~/code/mcp
git clone https://github.com/frastlin/Office-Word-MCP-Server.git
cd Office-Word-MCP-Server
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Windows PowerShell equivalent:

```powershell
mkdir $HOME\code\mcp
cd $HOME\code\mcp
git clone https://github.com/frastlin/Office-Word-MCP-Server.git
cd Office-Word-MCP-Server
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

macOS should be same as Linux, except note that Python may be:

```bash
python3 -m venv .venv
```

Document how to find the server file:

```bash
find . -name "word_mcp_server.py" -o -name "*server*.py"
```

Expected:

```text
./word_mcp_server.py
```

Document Claude Code MCP registration.

Use actual Claude Code command style if known from local project docs. Otherwise document both:

```bash
claude mcp add word-document-server \
  /absolute/path/to/Office-Word-MCP-Server/.venv/bin/python \
  /absolute/path/to/Office-Word-MCP-Server/word_mcp_server.py
```

or:

```bash
claude mcp add word-document-server -- \
  /absolute/path/to/Office-Word-MCP-Server/.venv/bin/python \
  /absolute/path/to/Office-Word-MCP-Server/word_mcp_server.py
```

For Windows, show:

```powershell
claude mcp add word-document-server -- `
  C:\Users\<YOU>\code\mcp\Office-Word-MCP-Server\.venv\Scripts\python.exe `
  C:\Users\<YOU>\code\mcp\Office-Word-MCP-Server\word_mcp_server.py
```

Document verification:

```text
Open Claude Code
Run /mcp
Confirm:
  word-document-server connected
```

Also document the observed successful state:

```text
word-document-server connected · 82 tools
```

### 8. Smithery Troubleshooting

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

Recommend manual frastlin clone + Claude Code MCP registration instead.

### 9. Verification Checklist

Include commands:

```bash
pytest
cd frontend && npm run build
```

And manual checks:

```text
Open frontend at http://localhost:5173
Open Claude Code and run /mcp
Confirm word-document-server connected
Run one auto tailoring job
Confirm output/tailored_resume.docx exists
Open DOCX and confirm it is formatted
```

### 10. Platform Notes

Linux:

```text
Use source .venv/bin/activate.
Paths look like /home/<user>/...
```

macOS:

```text
Use python3 if python is not available.
Claude Desktop config, if needed, is under ~/Library/Application Support/Claude/.
```

Windows:

```text
Use PowerShell activation.
If script execution is blocked, run:
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
Paths use .venv\Scripts\python.exe.
Use $env:VITE_API_BASE for frontend env var.
```

## Tests

No application tests are required unless docs linting exists.

If docs linting exists, run it.

## Acceptance Criteria

- Cross-platform install guide exists.
- Linux/macOS/Windows backend setup is documented.
- Linux/macOS/Windows frontend setup is documented.
- Claude Code setup is documented.
- Anthropic DOCX/document skill setup is documented.
- Guide clearly says DOCX skill/plugin must be reinstalled/re-enabled per machine.
- Office Word MCP setup uses frastlin fork manual install as preferred path.
- Claude Code MCP registration is documented.
- Smithery failure is documented as troubleshooting.
- Verification checklist exists.
- Top-level README links to the install guide if appropriate.

## Verification

Run:

```bash
test -f README_INSTALL.md || test -f docs/install.md
```

If docs linting exists, run it.

Optionally run:

```bash
pytest
cd frontend && npm run build
```

## Git

After verification passes:

1. Stage changed files.
2. Commit locally with:

```text
Add cross-platform install guide
```

Do not push.
