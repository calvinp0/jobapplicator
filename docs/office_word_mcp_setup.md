# Office Word MCP Setup

As of task 111, the auto tailoring path produces
`output/tailored_resume.docx` deterministically from
`output/tailored_resume.json` via the backend renderer at
`backend/app/resume_docx_renderer.py`. Office Word MCP / Claude for
Word is **no longer the primary formatting path**; it remains
available as:

- a manual or experimental fallback when the deterministic renderer
  cannot capture a particular visual identity;
- a human-in-the-loop editor for reviewer-driven changes that are
  easier to make inside Word than as JSON edits;
- a tool for inspecting `input/master_resume.docx` when an operator
  wants to compare visual fidelity by hand.

When Claude Code does use the Office Word MCP server
(`word-document-server`) as a fallback, the server gives it direct,
in-process access to Word document operations — opening, copying,
editing headings, paragraphs, bullets, styles, tables, comments, and
tracked changes — rather than relying on plain-text DOCX assembly.

This document describes how to install and verify the local MCP
server for that fallback use.

## Why this helps DOCX tailoring

A resume DOCX produced from scratch by stringing text together tends to
lose Word styling: heading levels collapse, bullet indentation drifts,
fonts default, and the result is effectively a plain-text dump inside a
`.docx`. The Office Word MCP exposes a real `python-docx`-backed
toolset, so Claude can:

- copy a source DOCX as the editable base (`copy_document`) and edit
  text in place;
- preserve the original margins, fonts, heading styles, bullet
  indentation, and spacing rather than recomputing them;
- use `search_and_replace`, `format_text`, `add_heading`,
  `add_paragraph`, `add_table`, and related tools to make focused edits;
- optionally apply `replace_with_track_changes` /
  `insert_*_with_track_changes` when a reviewable revision history is
  useful.

For resume application artifacts the primary target is DOCX (and PDF
exported from it), so Office Word MCP is the better first integration
than Google Docs (see "Google Docs note" below).

## Expected server in Claude Code

After installation, the Claude Code `/mcp` panel should show:

```text
word-document-server   connected
~82 tools
```

The exact tool count may vary by upstream version, but representative
tools include:

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

## Installing the frastlin fork locally

Locally, the `frastlin/Office-Word-MCP-Server` fork has been the
reliable install path. The published Smithery options were not stable
in our environment:

- `@GongRzhe/Office-Word-MCP-Server` failed with "no connection
  configuration".
- `@frastlin/Office-Word-MCP-Server` (via Smithery) failed with
  "404 server not found".

The working pattern is a manual fork install + explicit Claude Code
MCP registration. Use a **dedicated Python environment** (a venv
inside the cloned repo, or a `word-mcp` conda env) so Claude Code
launches the MCP with a deterministic interpreter rather than a
PATH-dependent `python` / `python3`.

The instructions below use these portable placeholders:

```text
<WORD_MCP_DIR>      cloned Office-Word-MCP-Server directory
<WORD_MCP_PYTHON>   explicit Python interpreter for the MCP server
<WORD_MCP_SERVER>   absolute path to word_mcp_server.py
```

Primary commands use shell variables (`$WORD_MCP_DIR`,
`$WORD_MCP_PYTHON`, `$WORD_MCP_SERVER`) rather than hardcoded
user-specific paths like `/home/<user>/...` or
`C:\Users\<You>\...`.

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

### Why an explicit interpreter

Do not rely on:

```text
python
python3
```

from `PATH` to launch the MCP. PATH-dependent interpreters silently
change between shells, between machines, and when other Python
toolchains are installed — Claude Code will then launch the MCP
server with the wrong dependency set and `/mcp` will list it as
`failed` or `disconnected`.

Use a dedicated environment such as `word-mcp` (Option B) or the
in-repo `.venv` (Option A). Do not reuse the JobApplicator backend
env unless you are intentionally maintaining both together.

### Register with Claude Code

Use the resolved `$WORD_MCP_PYTHON` and `$WORD_MCP_SERVER` (or the
explicit absolute paths) in `claude mcp add`. The exact flag style
varies by Claude Code build; try both forms below if the first is
rejected.

Linux / macOS:

```bash
claude mcp add word-document-server -- \
  "$WORD_MCP_PYTHON" \
  "$WORD_MCP_SERVER"
```

or, without the explicit `--` separator (older Claude Code builds):

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

Run `claude mcp add --help` to confirm the supported flags for your
build. Some versions require `--scope` or `--transport stdio`.

Restart Claude Code (or the relevant session) so it picks up the new
MCP entry.

## Verifying installation

From an interactive Claude Code session, run:

```text
/mcp
```

The "Local MCPs" section should list:

```text
word-document-server   connected   ~82 tools
```

If the entry shows `failed` or `disconnected`, the most common causes
are:

- the virtualenv path in the registration command is stale;
- `requirements.txt` was not installed inside the same virtualenv whose
  `python` is being invoked;
- Claude Code was not restarted after registration.

## Worker behavior

The backend worker (`backend/app/claude_worker.py`) does not attempt to
prove the MCP server is reachable. It logs that Word/DOCX tooling was
requested:

```text
jobapply: Word/DOCX tooling requested for DOCX generation
jobapply: Office Word MCP server requested if available
jobapply: DOCX skill requested if available
jobapply: Office Word MCP availability unknown
jobapply: DOCX skill availability unknown
```

The runtime prompt (`runtime_prompts/resume_tailoring.md`) tells Claude
Code to prefer the Office Word MCP first, fall back to the DOCX skill
when the MCP is unavailable, and fall back again to existing DOCX
generation behavior if neither is available. The worker's
post-invocation output validation is what ultimately decides whether
the run produced a valid DOCX.

## How this differs from Claude for Word

Claude for Word is a separate path (`tailoring_method = word_handoff`)
that packages inputs for a manual or semi-automated edit performed by
the user inside Word's Claude integration. It does not run
non-interactively in the backend; the user copies the prompt into
Claude for Word, accepts edits in Word, and re-imports the result.

The Office Word MCP, by contrast, runs *inside* the non-interactive
`auto` tailoring path. The user does not touch Word during the run.

## How this differs from Google Docs

Google Docs MCP is not part of the core `auto` DOCX path.

Google Docs may be useful later for:

- collaborative review
- cloud storage
- comments
- sharing drafts
- exporting reviewed documents

But for resume application artifacts, DOCX/PDF remains the primary
target, so Office Word MCP is the better first integration. A future
task may add Google Docs support for review/share workflows; this task
does not.

## Known limitations

- **No automatic detection.** The worker logs that the MCP was
  requested but cannot reliably probe Claude Code's MCP registry from
  outside an interactive session. Treat availability as `unknown` in
  logs.
- **Smithery installs are unreliable locally.** Stick with the
  `frastlin` fork install above. The Smithery-listed packages may work
  in other environments, but they have not worked here.
- **`convert_to_pdf` is optional.** The MCP exposes a PDF export, but
  the auto path's required outputs do not include a PDF. The PDF
  export is available for downstream tasks that want it.
- **Tracked-changes tools are optional.** `replace_with_track_changes`
  and the `insert_*_with_track_changes` family are useful when a
  human-reviewable revision history matters, but the auto path does
  not require track changes by default.
