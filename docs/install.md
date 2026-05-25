# Install Guide

Cross-platform setup for running JobApplicator locally on Linux,
macOS, and Windows.

JobApplicator is a local-first cockpit. There is no hosted version,
and Claude Code is invoked as a local worker, so each developer
machine needs the same backend, frontend, Claude Code, and
document-tooling pieces in place.

The deeper companion docs for the document-tooling pieces are:

- [`docs/claude_docx_skill_setup.md`](claude_docx_skill_setup.md)
- [`docs/office_word_mcp_setup.md`](office_word_mcp_setup.md)

This guide is the top-level entry point; those documents are the
canonical reference for skill/MCP details.

## 1. Prerequisites

Required:

```text
Python 3.12+         (backend; see backend/pyproject.toml)
Node.js 20+          (frontend)
npm                  (ships with Node.js)
Git
Claude Code          (the `claude` CLI, logged in to your Claude account)
```

Optional but useful:

```text
Microsoft Word       (for the Claude for Word / manual review flow)
uv or uvx            (alternative Python installer; not required)
npx                  (ships with Node.js; used by some MCP/plugin tooling)
LibreOffice          (for opening generated DOCX on Linux)
```

Claude Code must be installed and logged in before the auto tailoring
path will work. Plugins, skills, and MCP servers configured in Claude
Code are *local-machine* state. They are not part of this repository
and must be set up again on every new Linux/macOS/Windows machine.

## 2. Clone and Install

### Clone

```bash
git clone <repo-url> jobapply
cd jobapply
```

### Backend (Linux / macOS)

The backend is a PEP 621 package defined in `backend/pyproject.toml`
(no `requirements.txt`). Install it in editable mode inside a
virtualenv.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
# Optional: install test extras
pip install -e .[test]
```

On macOS, if `python` is not on `PATH`, use `python3`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
```

### Backend (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
# Optional: install test extras
pip install -e .[test]
```

If PowerShell blocks `Activate.ps1` with an execution-policy error,
see the Platform Notes section below.

### Frontend (all platforms)

```bash
cd frontend
npm install
```

## 3. Run Locally

You can either use the helper script (Linux/macOS) or run the two
services manually.

### Helper script (Linux / macOS)

From the repo root:

```bash
./scripts/dev.sh
# or
make dev
```

This starts the backend on `http://127.0.0.1:8000` and the frontend
on `http://localhost:5173` with `VITE_API_BASE` already wired up.

### Manual (Linux / macOS)

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend
VITE_API_BASE=http://localhost:8000 npm run dev -- --host localhost --port 5173
```

### Manual (Windows PowerShell)

Backend:

```powershell
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second PowerShell:

```powershell
cd frontend
$env:VITE_API_BASE="http://localhost:8000"
npm run dev -- --host localhost --port 5173
```

Open `http://localhost:5173` in your browser.

## 4. Environment Variables

The project is intentionally minimal about environment configuration.
The known variables are:

```text
VITE_API_BASE
    Frontend → backend URL. Defaults to http://127.0.0.1:8000 via
    scripts/dev.sh and the Makefile. Override when running the
    frontend against a non-default backend port.

ANTHROPIC_API_KEY
    Used by Claude Code itself, not directly by this repo's backend.
    Configure it the way Claude Code expects on your platform
    (usually via `claude` login or the standard Claude Code env var).

API_HOST / API_PORT / WEB_HOST / WEB_PORT
    Recognized by scripts/dev.sh to override the default hosts/ports
    when starting both services together.

GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
GMAIL_TOKEN_PATH
    Optional Gmail read-only OAuth integration (task 082).
    See section 11 (Optional Gmail Read-Only Connection) below and
    docs/contracts/gmail_integration.md for the full contract.
```

There is currently no `.env.example` in this repo; the variables
above are the complete known surface. If you need to add a new
environment variable, prefer documenting it here (and in the relevant
service's README) over relying on undocumented `os.environ` reads.

## 5. Claude Code Setup

Claude Code is the worker that produces tailored resume artifacts.
Install it per Anthropic's instructions for your platform, then log
in:

```bash
claude
```

Verify the CLI is available:

```bash
claude --version
claude --help
```

Plugins, skills, and MCP servers registered inside Claude Code are
stored in your local Claude Code configuration, not in this
repository. When you move to a new Linux/macOS/Windows machine, you
must reinstall and reconfigure them separately. The two pieces this
project specifically depends on are covered in sections 6 and 7
below.

## 6. Anthropic DOCX / Document Skill Setup

The auto tailoring path asks Claude Code to use Anthropic's DOCX /
document skill (`anthropics/docx-documents`) when writing
`output/tailored_resume.docx`. The skill helps Claude generate a
properly formatted Word document instead of a plain-text dump shoved
into a `.docx`.

> **Per-machine setup.** When moving to a new machine, assume you
> must reinstall or re-enable the document / DOCX skill for Claude
> Code. The runtime prompt can ask Claude to use the skill, but the
> project cannot guarantee it exists unless Claude Code has it
> installed on this machine.

Try whichever install path your Claude Code build supports.

### Path A: Claude Code plugin marketplace

From an interactive Claude Code session:

```text
/plugin marketplace add anthropics/skills
/plugin install document-skills@anthropic-agent-skills
```

### Path B: `mdskills` CLI

If `mdskills` is available on your machine:

```bash
npx mdskills install anthropics/docx-documents
```

Both paths are version-dependent; if one is not available in your
Claude Code build, try the other.

### Verify

1. From an interactive Claude Code session, ask Claude whether the
   DOCX / document skill is available, or run a stable listing command
   if your build supports one:

   ```text
   /plugin list
   ```

2. Run a tiny DOCX generation test inside Claude Code and confirm the
   resulting `.docx` opens with proper headings and bullets — not a
   single wall of plain text.

3. Run an end-to-end tailoring job through the backend and open
   `runs/<run_id>/output/tailored_resume.docx`. It should look like a
   real Word document.

See [`docs/claude_docx_skill_setup.md`](claude_docx_skill_setup.md)
for deeper details.

## 7. Office Word MCP Setup

The auto tailoring path prefers the Office Word MCP server
(`word-document-server`) for DOCX work because it exposes a real
`python-docx`-backed toolset (headings, bullets, styles, tables,
tracked changes) rather than plain-text assembly.

The reliable local install path is the `frastlin` fork registered as
an MCP server in Claude Code.

### Use a dedicated Python interpreter

The Office Word MCP server is a Python program. Claude Code must
launch it with an **explicit, deterministic Python interpreter** —
not the ambiguous system `python` or `python3` on `PATH`. Two
supported approaches:

```text
Option A: virtualenv (.venv inside the cloned MCP repo)
Option B: conda (a dedicated `word-mcp` environment)
```

Do not rely on:

```text
python
python3
```

unless there is no better option (and document the risk inline if you
must). PATH-dependent interpreters silently change when shells
restart, when other Python toolchains are installed, or when an
unrelated virtualenv is active — Claude Code will then launch the
MCP with the wrong dependency set and `/mcp` will show `failed`.

Use a dedicated environment such as `word-mcp`. Do not reuse the
JobApplicator backend env unless you are intentionally maintaining
them together.

The instructions below use these portable placeholders/variables:

```text
<WORD_MCP_DIR>      cloned Office-Word-MCP-Server directory
<WORD_MCP_PYTHON>   explicit Python interpreter for the MCP server
<WORD_MCP_SERVER>   absolute path to word_mcp_server.py
```

In examples we resolve them into shell variables (`$WORD_MCP_DIR`,
`$WORD_MCP_PYTHON`, `$WORD_MCP_SERVER` on Linux/macOS, the same names
on PowerShell). Examples may show `$HOME/code/mcp/...`-style
locations; primary commands stay portable, no hardcoded
`/home/<user>/...` or `C:\Users\<You>\...` paths.

### Option A — virtualenv

Linux / macOS:

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

Windows PowerShell:

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

If PowerShell blocks `Activate.ps1` with an execution-policy error,
run once per user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Option B — conda

Linux / macOS:

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

Windows PowerShell:

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

### Locate the server entrypoint

The frastlin fork's entrypoint is committed at the repository root:

```text
$WORD_MCP_DIR/word_mcp_server.py
```

The `test -f "$WORD_MCP_SERVER"` / `Test-Path $WORD_MCP_SERVER` step
above confirms it.

### Register with Claude Code

Pass the resolved `$WORD_MCP_PYTHON` and `$WORD_MCP_SERVER` so Claude
Code launches the MCP with the explicit Python interpreter — never a
PATH-derived `python` or `python3`.

Linux / macOS:

```bash
claude mcp add word-document-server -- \
  "$WORD_MCP_PYTHON" \
  "$WORD_MCP_SERVER"
```

If your Claude Code build does not accept the explicit `--` separator,
try the same command without it:

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

Run `claude mcp add --help` to confirm the exact flag style your
build supports (some versions require `--scope`, `--transport stdio`,
or a different positional layout).

Restart Claude Code so it picks up the new MCP entry.

### Verify

In an interactive Claude Code session:

```text
/mcp
```

Confirm the entry under "Local MCPs":

```text
word-document-server   connected
```

The observed working state on this project is:

```text
word-document-server connected · 82 tools
```

The exact tool count can vary with upstream changes. See
[`docs/office_word_mcp_setup.md`](office_word_mcp_setup.md) for the
deeper reference (expected tool list, common failure causes).

## 8. Smithery Troubleshooting

The Smithery one-click installer was not reliable for this MCP
locally. Both of these attempts failed:

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

Recommendation: use the manual `frastlin` clone + Claude Code MCP
registration in section 7 above. The Smithery packages may work in
other environments, but they have not worked here.

## 9. Verification Checklist

Automated:

```bash
# Backend tests (from repo root, with backend venv active)
cd backend
pytest

# Frontend build
cd frontend
npm run build
```

Manual:

```text
- Open the frontend at http://localhost:5173.
- Open Claude Code and run /mcp; confirm word-document-server connected.
- Run one auto tailoring job through the cockpit.
- Confirm runs/<run_id>/output/tailored_resume.docx exists.
- Open the DOCX in Word/LibreOffice and confirm headings, bullets,
  and spacing are formatted (not a plain-text wall).
```

## 10. Platform Notes

### Linux

```text
- Activate venvs with `source .venv/bin/activate`.
- Paths look like /home/<user>/...
- LibreOffice is the typical way to open generated DOCX files.
```

### macOS

```text
- Use `python3` if `python` is not on PATH.
- Activate venvs with `source .venv/bin/activate`.
- Claude Desktop config (if you also use Claude Desktop) lives under
  ~/Library/Application Support/Claude/.
```

### Windows

```text
- Use PowerShell, not cmd.exe, for the commands in this guide.
- Activate venvs with `.venv\Scripts\Activate.ps1`.
- If PowerShell blocks the activation script with an execution-policy
  error, run once per user:
      Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
- Virtualenv Python lives at `.venv\Scripts\python.exe`.
- Set frontend env vars with `$env:VITE_API_BASE="..."` before
  running `npm run dev`.
```

## 11. Optional Gmail Read-Only Connection

The backend ships an optional read-only Gmail integration (task 082)
that lets the cockpit check whether Gmail is connected and run a
small, capped test search. **No** email is ever sent, archived,
deleted, labeled, or otherwise modified — see
[`docs/contracts/gmail_integration.md`](contracts/gmail_integration.md)
for the full contract and safety rules.

If you do not want Gmail integration, skip this section entirely;
nothing else in the backend depends on it.

### Install the optional extras

The google client libraries are an optional extras group so the
default install stays small:

```bash
cd backend
source .venv/bin/activate
pip install -e .[gmail]
```

### Create a Google OAuth client

1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create (or reuse) a project, then go to **APIs & Services →
   Credentials**.
3. Create an **OAuth client ID** of type **Web application**.
4. Under **Authorized redirect URIs**, add the URI that matches the
   `GOOGLE_REDIRECT_URI` env var you will set below. The default is:

   ```
   http://localhost:8000/gmail/oauth/callback
   ```

5. Enable the **Gmail API** for the project under **APIs &
   Services → Library**.

### Set the env vars

```bash
export GOOGLE_CLIENT_ID="<your client id>.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="<your client secret>"
export GOOGLE_REDIRECT_URI="http://localhost:8000/gmail/oauth/callback"
# Optional; defaults to candidate_context/gmail/token.json
export GMAIL_TOKEN_PATH="$PWD/candidate_context/gmail/token.json"
```

The token file is excluded from git via `.gitignore` and holds a
plain-text refresh token — treat it as a secret.

### Connect and verify

1. Start the backend:

   ```bash
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. Confirm disconnected:

   ```bash
   curl http://localhost:8000/gmail/status
   ```

3. Get the consent URL:

   ```bash
   curl http://localhost:8000/gmail/auth-url
   ```

4. Open the returned `auth_url` in a browser, complete Google
   consent, and let the browser follow the redirect back to
   `/gmail/oauth/callback`.

5. Confirm connected:

   ```bash
   curl http://localhost:8000/gmail/status
   ```

6. Run a safe test search:

   ```bash
   curl -X POST http://localhost:8000/gmail/test-search \
     -H 'Content-Type: application/json' \
     -d '{"query":"newer_than:7d","max_results":5}'
   ```

   The response includes only message metadata (id, subject, from,
   date, snippet) — no body, no html, no attachments.
