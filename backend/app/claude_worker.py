from __future__ import annotations

import io
import os
import re
import subprocess
import threading
import time
import zipfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .docx_extract import (
    EXTRACTED_FILENAME as EXTRACTED_RESUME_FILENAME,
    EXTRACTION_ERROR_FILENAME as EXTRACTION_ERROR_RESUME_FILENAME,
    ExtractionResult,
    extract_master_resume_if_present,
)
from .llm_providers import (
    DEFAULT_PROVIDER_ID,
    LLMProvider,
    get_provider,
    resolve_binary,
)
from .models import ClaudeRun
from .resume_docx_renderer import (
    RendererError,
    TAILORED_RESUME_DOCX_FILENAME,
    TAILORED_RESUME_JSON_FILENAME,
    TEMPLATE_FIDELITY_AUDIT_FILENAME as RENDERER_TEMPLATE_FIDELITY_AUDIT_FILENAME,
    render_resume_from_run,
)
from .resume_suggestions import (
    RESUME_SUGGESTIONS_FILENAME,
    SuggestionError,
    load_suggestions_json,
    validate_suggestions_payload,
)
from .run_directory import EXPECTED_OUTPUTS


CLAUDE_BINARY_ENV = "JOBAPPLY_CLAUDE_BINARY"
CLAUDE_DRY_RUN_ENV = "JOBAPPLY_CLAUDE_DRY_RUN"
CLAUDE_EXTRA_ARGS_ENV = "JOBAPPLY_CLAUDE_EXTRA_ARGS"
CLAUDE_PERMISSION_MODE_ENV = "JOBAPPLY_CLAUDE_PERMISSION_MODE"
PROGRESS_HEARTBEAT_ENV = "JOBAPPLY_PROGRESS_HEARTBEAT_SECONDS"

# Default permission mode for the non-interactive backend run. ``acceptEdits``
# auto-approves file writes inside the subprocess cwd (the run directory) so
# Claude can produce ``output/`` without operator approval. The write scope is
# bounded by ``cwd=<run_dir>``; Claude Code does not write outside cwd unless
# given ``--add-dir``, which the worker does not pass.
DEFAULT_PERMISSION_MODE = "acceptEdits"

RUN_LOG_FILENAME = "run.log"
PROMPT_RELPATH = Path("input") / "tailoring_prompt.md"
INPUT_DIRNAME = "input"
OUTPUT_DIRNAME = "output"
# Output produced by the deterministic backend renderer (task 111). The
# worker calls ``render_resume_from_run`` after Claude finishes, which
# reads ``output/tailored_resume.json`` and produces both
# ``output/tailored_resume.docx`` and this audit file. The audit was
# previously requested from Claude (task 107) and lives at the same path
# so existing operator tooling continues to work.
TEMPLATE_FIDELITY_AUDIT_FILENAME = RENDERER_TEMPLATE_FIDELITY_AUDIT_FILENAME
# Optional output (not in EXPECTED_OUTPUTS) — the runtime prompt asks
# Claude to also produce a recruiter/hiring-manager review of the
# tailored resume (task 108). To avoid breaking existing dry-run /
# import tests that wrote the original output set, this file is
# requested but not strictly required by the worker; the warning line
# surfaces missed reviews so the operator can spot regressions.
RECRUITER_REVIEW_FILENAME = "recruiter_review.md"
PROGRESS_DIRNAME = "progress"
PROGRESS_LOG_FILENAME = "progress.log"
PROGRESS_RELPATH = Path(PROGRESS_DIRNAME) / PROGRESS_LOG_FILENAME

# Default cap on lines returned by ``read_recent_log_lines`` and on bytes read
# from the log file. Keeps the response small for the polling UI and bounds
# memory use if a runaway Claude run produces a giant log.
DEFAULT_LOG_TAIL_LINES = 40
LOG_READ_MAX_BYTES = 256 * 1024

# Heartbeat tick interval for the worker's fallback progress writer (seconds).
# A value of 0 disables the heartbeat entirely (used by tests that don't want
# the extra thread).
DEFAULT_PROGRESS_HEARTBEAT_SECONDS = 15.0

# Cap user-facing progress lines so a runaway Claude write doesn't bloat the
# poll response. The runtime prompt asks for <=120 chars per line; this is a
# defensive hard cap on top of that.
PROGRESS_LINE_MAX_CHARS = 200

# Strip the common subset of ANSI escape codes (CSI/SGR) that Claude's stdout
# may carry. We intentionally do not parse OSC sequences — the simple regex
# below is enough to keep recent-activity lines readable in the UI.
_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def read_recent_log_lines(
    log_path: Path,
    *,
    max_lines: int = DEFAULT_LOG_TAIL_LINES,
    max_bytes: int = LOG_READ_MAX_BYTES,
) -> tuple[list[str], bool]:
    """Return the last ``max_lines`` non-empty lines from ``log_path``.

    Returns ``([], False)`` when the file does not exist. ``truncated`` is
    ``True`` when the file is larger than ``max_bytes`` (we only read the
    tail) or when more than ``max_lines`` non-empty lines exist.
    """
    if not log_path.is_file():
        return [], False
    size = log_path.stat().st_size
    truncated = size > max_bytes
    with log_path.open("rb") as f:
        if truncated:
            f.seek(size - max_bytes)
            # Drop a likely-partial first line after seeking mid-file.
            f.readline()
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    tail: deque[str] = deque(maxlen=max_lines)
    total_nonempty = 0
    for line in text.splitlines():
        cleaned = _ANSI_ESCAPE_RE.sub("", line).rstrip()
        if not cleaned:
            continue
        total_nonempty += 1
        tail.append(cleaned)
    if total_nonempty > max_lines:
        truncated = True
    return list(tail), truncated


def read_progress_lines(
    progress_path: Path,
    *,
    max_lines: int = DEFAULT_LOG_TAIL_LINES,
    max_bytes: int = LOG_READ_MAX_BYTES,
) -> tuple[list[str], bool]:
    """Return the last ``max_lines`` user-facing progress lines.

    Mirrors ``read_recent_log_lines`` but targets ``progress/progress.log``,
    which contains plain user-facing one-liners (no ``jobapply:`` prefix and
    no ANSI). Returns ``([], False)`` when the file does not yet exist so the
    polling UI can stay quiet before the first event.
    """
    if not progress_path.is_file():
        return [], False
    size = progress_path.stat().st_size
    truncated = size > max_bytes
    with progress_path.open("rb") as f:
        if truncated:
            f.seek(size - max_bytes)
            f.readline()
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lines.append(cleaned)
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    return lines, truncated


def _heartbeat_interval_seconds() -> float:
    """Return the heartbeat tick interval, or 0 to disable.

    ``0`` disables the heartbeat thread entirely (used by tests where the
    fake binary completes faster than any reasonable tick anyway).
    """
    raw = os.environ.get(PROGRESS_HEARTBEAT_ENV, "").strip()
    if not raw:
        return DEFAULT_PROGRESS_HEARTBEAT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_PROGRESS_HEARTBEAT_SECONDS
    return max(0.0, value)


def _append_progress_line(progress_path: Path, message: str) -> None:
    """Append one user-facing progress line. Best-effort: errors swallowed.

    The progress file is shared between the worker (heartbeats, dry-run) and
    Claude Code (phase events). Each writer opens-append-closes so a partial
    write never blocks the other writer for long.
    """
    text = message.replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return
    if len(text) > PROGRESS_LINE_MAX_CHARS:
        text = text[:PROGRESS_LINE_MAX_CHARS]
    try:
        with progress_path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


class ClaudeWorkerError(RuntimeError):
    """Raised when the worker cannot even attempt to invoke Claude Code.

    Process-level failures (non-zero exit, missing binary) are recorded on
    the ``ClaudeRun`` row instead of raising.
    """


def _resolve_run_provider(run: ClaudeRun) -> LLMProvider:
    """Look up the run's persisted provider, falling back to the default.

    A run can carry an unknown id only if the row was written by a build
    that knew about more providers than this one (rolling-rollback safety).
    In that case we surface the unknown id by raising — the worker treats
    it like a configuration error rather than silently substituting the
    default, which would hide drift between code and data.
    """
    provider_id = (run.llm_provider or DEFAULT_PROVIDER_ID).strip() or DEFAULT_PROVIDER_ID
    provider = get_provider(provider_id)
    if provider is None:
        raise ClaudeWorkerError(
            f"unknown llm_provider on run {run.id}: {provider_id!r}"
        )
    return provider


def is_dry_run() -> bool:
    return os.environ.get(CLAUDE_DRY_RUN_ENV, "").lower() in {"1", "true", "yes", "on"}


def _extra_args() -> list[str]:
    raw = os.environ.get(CLAUDE_EXTRA_ARGS_ENV, "").strip()
    return raw.split() if raw else []


def _permission_mode() -> str:
    raw = os.environ.get(CLAUDE_PERMISSION_MODE_ENV, "").strip()
    return raw or DEFAULT_PERMISSION_MODE


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_failure(db: Session, run: ClaudeRun, message: str) -> ClaudeRun:
    run.status = "failed"
    run.error_message = message
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def _extract_master_resume_docx(
    run_dir: Path, log_path: Path
) -> ExtractionResult:
    """Run pre-tailoring DOCX extraction and emit ``jobapply:`` log lines.

    The worker logs whether a DOCX was found, the relative path it
    extracted from, and the destination markdown path — or a clear
    failure line when ``python-docx`` rejects the file. The caller
    decides whether the run can continue (see ``invoke_claude_run``).
    """
    input_dir = run_dir / INPUT_DIRNAME
    _append_progress(log_path, "checking for master resume DOCX")
    result = extract_master_resume_if_present(input_dir)
    if not result.docx_found:
        return result

    relpath = f"{INPUT_DIRNAME}/{result.docx_path.name}"
    _append_progress(log_path, f"found source resume DOCX={relpath}")
    # When a master DOCX is present, the tailoring contract treats it as
    # both the evidence source (via the extracted markdown projection) and
    # the formatting/style template for output/tailored_resume.docx. Log
    # the style-preservation contract so the operator can see in the run
    # log that Claude was asked to keep the master's visual styling
    # (colored headings, fonts, spacing, bullet indentation, etc.).
    _append_progress(
        log_path, "source DOCX style preservation requested"
    )
    _append_progress(
        log_path, "master resume DOCX staged as formatting source"
    )
    _append_progress(
        log_path,
        "template fidelity audit expected at output/template_fidelity_audit.md",
    )
    if result.extracted:
        _append_progress(
            log_path,
            "extracted source resume DOCX to "
            f"{INPUT_DIRNAME}/{EXTRACTED_RESUME_FILENAME}",
        )
    else:
        _append_progress(log_path, "failed to extract source resume DOCX")
        _append_progress(
            log_path,
            "wrote extraction error to "
            f"{INPUT_DIRNAME}/{EXTRACTION_ERROR_RESUME_FILENAME}",
        )
    return result


def _missing_outputs(run_dir: Path) -> list[str]:
    """Return relative paths of required output files that are absent."""
    output_dir = run_dir / OUTPUT_DIRNAME
    missing: list[str] = []
    for filename in EXPECTED_OUTPUTS:
        if not (output_dir / filename).is_file():
            missing.append(f"{OUTPUT_DIRNAME}/{filename}")
    return missing


def _render_docx_from_structured_json(
    run_dir: Path,
    log_path: Path,
    *,
    extraction_docx_relpath: Optional[str],
) -> None:
    """Validate the structured resume JSON and render the deterministic DOCX.

    Raises :class:`RendererError` when the JSON file is missing or
    invalid so the caller can mark the run failed with a clear error
    message. On success, ``output/tailored_resume.docx`` and
    ``output/template_fidelity_audit.md`` exist regardless of whether
    Claude produced them, and the worker has logged the rendering
    pipeline transitions.
    """
    output_dir = run_dir / OUTPUT_DIRNAME
    json_path = output_dir / TAILORED_RESUME_JSON_FILENAME

    _append_progress(
        log_path,
        "structured resume JSON expected at "
        f"{OUTPUT_DIRNAME}/{TAILORED_RESUME_JSON_FILENAME}",
    )
    if not json_path.is_file():
        message = (
            "expected output file missing: "
            f"{OUTPUT_DIRNAME}/{TAILORED_RESUME_JSON_FILENAME}"
        )
        _append_progress(log_path, message)
        raise RendererError(message)

    _append_progress(log_path, "validating structured resume JSON")
    _append_progress(
        log_path,
        "rendering DOCX deterministically from structured resume JSON",
    )
    try:
        result = render_resume_from_run(
            run_dir,
            source_docx_relpath=extraction_docx_relpath,
        )
    except RendererError as exc:
        message = f"invalid tailored resume JSON: {exc}"
        _append_progress(log_path, message)
        raise RendererError(message) from exc

    _append_progress(
        log_path,
        f"rendered {OUTPUT_DIRNAME}/{TAILORED_RESUME_DOCX_FILENAME}",
    )
    _append_progress(
        log_path,
        "wrote deterministic template fidelity audit at "
        f"{OUTPUT_DIRNAME}/{TEMPLATE_FIDELITY_AUDIT_FILENAME}",
    )
    # Result is recorded for the operator in run.log; the renderer itself
    # writes the structured audit file so we just confirm the section /
    # bullet counts here.
    _append_progress(
        log_path,
        f"deterministic render produced {result.section_count} sections, "
        f"{result.bullet_count} bullets",
    )


def _validate_resume_suggestions(run_dir: Path, log_path: Path) -> None:
    """Validate ``output/resume_suggestions.json`` against the schema (task 113).

    Presence is enforced separately by :func:`_missing_outputs`; this step
    guards the *shape* so a malformed suggestions file fails the run with a
    clear message instead of silently importing junk. Mirrors how the
    deterministic renderer validates ``tailored_resume.json``.
    """
    suggestions_path = run_dir / OUTPUT_DIRNAME / RESUME_SUGGESTIONS_FILENAME
    if not suggestions_path.is_file():
        # Missing-file reporting is owned by ``_missing_outputs``; nothing to
        # validate here.
        return
    _append_progress(log_path, "validating resume suggestions JSON")
    try:
        payload = validate_suggestions_payload(load_suggestions_json(suggestions_path))
    except SuggestionError as exc:
        message = f"invalid resume suggestions JSON: {exc}"
        _append_progress(log_path, message)
        raise RendererError(message) from exc
    _append_progress(
        log_path,
        f"resume suggestions valid: {len(payload['suggestions'])} suggestion(s)",
    )


def _write_dry_run_outputs(run_dir: Path) -> None:
    """Populate ``output/`` with placeholder files so a dry-run is importable.

    Markdown placeholders are plain text; the DOCX is a minimal valid Word
    package so the open-file flow can hand it to the host application without
    a corrupt-file error.
    """
    output_dir = run_dir / OUTPUT_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "tailored_resume.md").write_text(
        "# Dry-run tailored resume\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    (output_dir / "change_log.md").write_text(
        "# Change log\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    (output_dir / "claim_audit.md").write_text(
        "# Claim audit\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    (output_dir / "ats_audit.md").write_text(
        "# ATS Audit\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    (output_dir / RECRUITER_REVIEW_FILENAME).write_text(
        "# Recruiter Review\n\n(placeholder generated by dry-run worker)\n",
        encoding="utf-8",
    )
    # Minimal structured JSON so the dry-run satisfies the post-Claude
    # contract that the deterministic renderer reads. Kept tiny so the
    # placeholder DOCX render is fast and obviously a smoke-test artifact.
    (output_dir / TAILORED_RESUME_JSON_FILENAME).write_text(
        '{\n'
        '  "header": {"name": "Dry-run Candidate", "contact_items": []},\n'
        '  "sections": [\n'
        '    {"type": "summary", "heading": "SUMMARY",\n'
        '     "paragraphs": ["Placeholder summary generated by the dry-run worker."]}\n'
        '  ],\n'
        '  "metadata": {"target_company": "(dry-run)", "target_job_title": "(dry-run)"}\n'
        '}\n',
        encoding="utf-8",
    )
    # Task 113: a valid (empty-list) suggestions document so the dry-run
    # satisfies the required-output contract and the review surface loads.
    (output_dir / RESUME_SUGGESTIONS_FILENAME).write_text(
        '{\n'
        '  "target_company": "(dry-run)",\n'
        '  "target_job_title": "(dry-run)",\n'
        '  "suggestions": []\n'
        '}\n',
        encoding="utf-8",
    )
    # The deterministic renderer will overwrite this minimal DOCX with a
    # real python-docx render once the worker calls it. We still write a
    # minimal valid Word package here so any code path that opens the
    # file before the renderer runs (e.g. legacy tests) gets a parseable
    # zip instead of an empty file.
    _write_minimal_docx(output_dir / "tailored_resume.docx")


def _write_minimal_docx(path: Path) -> None:
    """Write a minimal Word-openable .docx (a zip with the three required parts)."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/>'
        '</Relationships>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>Dry-run placeholder tailored resume.</w:t></w:r></w:p></w:body>'
        '</w:document>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    path.write_bytes(buf.getvalue())


def _run_heartbeat(
    progress_path: Path,
    stop_event: threading.Event,
    interval_seconds: float,
) -> None:
    """Write periodic 'still running' lines to ``progress/progress.log``.

    Runs on a background thread alongside the Claude subprocess. Stops as
    soon as the parent sets ``stop_event`` (which it does when the process
    exits). The first tick fires after ``interval_seconds`` so a fast run
    that completes inside the first interval gets no heartbeat lines at all.
    """
    start = time.monotonic()
    while not stop_event.wait(interval_seconds):
        elapsed = int(time.monotonic() - start)
        _append_progress_line(
            progress_path,
            f"Claude Code is running — {elapsed} seconds elapsed",
        )


def _append_progress(log_path: Path, message: str) -> None:
    """Append a worker-owned progress line to ``run.log``.

    These ``jobapply:`` lines interleave with the raw Claude subprocess output
    so the frontend can show meaningful progress even when Claude is silent.
    Failures to write are swallowed — progress logging must not affect run
    lifecycle.
    """
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"jobapply: {message}\n")
    except OSError:
        pass


def invoke_claude_run(
    run_id: str,
    db: Session,
    *,
    claude_binary: Optional[str] = None,
) -> ClaudeRun:
    """Invoke Claude Code synchronously for a previously created run.

    The backend records lifecycle (status, started_at, completed_at,
    error_message) on the ``ClaudeRun`` row. The subprocess only sees the
    run directory as its working directory and must not touch the DB.
    """
    run = db.get(ClaudeRun, run_id)
    if run is None:
        raise ClaudeWorkerError(f"claude run not found: {run_id}")

    run_dir = Path(run.run_dir)
    if not run_dir.is_dir():
        return _record_failure(
            db,
            run,
            f"run directory does not exist: {run_dir}",
        )

    prompt_file = run_dir / PROMPT_RELPATH
    if not prompt_file.is_file():
        return _record_failure(
            db,
            run,
            f"tailoring prompt not found: {prompt_file}",
        )

    output_dir = run_dir / OUTPUT_DIRNAME
    # Defensive: create_run_directory already mkdir's this, but ensure it
    # exists at launch time so Claude can write outputs even if the directory
    # was removed between create and invoke. The cwd=run_dir + acceptEdits
    # combination only auto-approves writes; it does not create directories.
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_dir / RUN_LOG_FILENAME
    # Truncate any prior log so progress lines start fresh per invocation.
    log_path.write_text("", encoding="utf-8")
    _append_progress(log_path, "preparing tailoring inputs")

    # Per docs/contracts/claude_run_directory.md the user-facing progress feed
    # lives at ``progress/progress.log``. The directory is (re-)created and the
    # file truncated on every invocation so the UI starts from a clean slate.
    progress_dir = run_dir / PROGRESS_DIRNAME
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / PROGRESS_LOG_FILENAME
    progress_path.write_text("", encoding="utf-8")

    run.status = "running"
    run.started_at = _now()
    run.completed_at = None
    run.error_message = None
    db.commit()

    extraction = _extract_master_resume_docx(run_dir, log_path)
    if extraction.failed and not extraction.has_other_resume_source:
        # The DOCX could not be projected to markdown and no fallback
        # markdown resume is on disk — there is no usable evidence source
        # for tailoring, so the run is failed loudly rather than letting
        # Claude run blind. The extraction error file (written by the
        # extractor) preserves the diagnostic for the operator.
        return _record_failure(
            db,
            run,
            "failed to extract source resume DOCX and no markdown resume present: "
            f"{extraction.error_message}",
        )

    if is_dry_run():
        _append_progress(log_path, "dry-run mode: skipping Claude subprocess")
        # Mirror the user-facing phases so the UI's progress panel still has
        # something meaningful to show during a dry-run smoke test.
        for line in (
            "Preparing tailoring inputs",
            "Writing placeholder tailored resume",
            "Validating required outputs",
        ):
            _append_progress_line(progress_path, line)
        _write_dry_run_outputs(run_dir)
        # Dry-run still exercises the deterministic renderer so the
        # placeholder JSON → DOCX pipeline is smoke-tested end-to-end.
        try:
            _render_docx_from_structured_json(
                run_dir, log_path, extraction_docx_relpath=None
            )
            _validate_resume_suggestions(run_dir, log_path)
        except RendererError as exc:
            return _record_failure(db, run, str(exc))
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"[dry-run] skipped Claude subprocess at {_now().isoformat()}\n"
                "[dry-run] wrote placeholder output files\n"
            )
        _append_progress(log_path, "validating output files")
        _append_progress(log_path, "output contract satisfied")
        run.status = "completed"
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
        return run

    try:
        provider = _resolve_run_provider(run)
    except ClaudeWorkerError as exc:
        _append_progress(log_path, str(exc))
        _append_progress(log_path, "marking run failed")
        return _record_failure(db, run, str(exc))

    # Override priority: explicit kwarg > provider env var > provider default.
    # The kwarg path stays for callers that want to inject a binary without
    # touching the environment (tests historically used the env var).
    binary = claude_binary or resolve_binary(provider)
    permission_mode = _permission_mode()
    # The argv is built by the provider's registry entry. The prompt body
    # itself is delivered over stdin (see PROMPT_DELIVERY_STDIN in
    # llm_providers.py); passing the prompt file path as a positional
    # argument made Claude Code treat it as a conversational starter, and
    # large prompts can exceed ARG_MAX, so the body never enters argv.
    argv = [*provider.build_argv(binary, permission_mode), *_extra_args()]

    try:
        prompt_text = prompt_file.read_text(encoding="utf-8")
    except OSError as exc:
        _append_progress(log_path, f"failed to read prompt file: {exc}")
        _append_progress(log_path, "marking run failed")
        return _record_failure(
            db,
            run,
            f"failed to read prompt file {prompt_file}: {exc}",
        )

    _append_progress(log_path, "launching Claude Code in non-interactive mode")
    _append_progress(log_path, f"prompt file={PROMPT_RELPATH}")
    _append_progress(log_path, f"launching Claude Code with cwd={run_dir}")
    _append_progress(log_path, f"permission mode={permission_mode}")
    _append_progress(log_path, f"output directory={output_dir}")
    # The runtime prompt asks Claude to use the Office Word MCP server
    # (word-document-server) and/or the DOCX / Word document skill when
    # generating output/tailored_resume.docx. The worker has no stable
    # cross-version way to verify either capability is actually installed,
    # so it records that usage was requested and leaves availability as
    # ``unknown``. Output validation (post-invocation) is what ultimately
    # decides whether the run produced a valid DOCX.
    _append_progress(log_path, "Word/DOCX tooling requested for DOCX generation")
    _append_progress(log_path, "Office Word MCP server requested if available")
    _append_progress(log_path, "DOCX skill requested if available")
    _append_progress(log_path, "Office Word MCP availability unknown")
    _append_progress(log_path, "DOCX skill availability unknown")
    # ATS optimization is part of the tailoring contract: the prompt asks
    # Claude to extract ATS keywords from the job description and emit a
    # structured audit at output/ats_audit.md. Record the request here so
    # the UI/log makes the contract visible even though detection of
    # whether Claude actually performed the work happens at output
    # validation time.
    _append_progress(log_path, "ATS optimization requested")
    _append_progress(log_path, "ATS audit expected at output/ats_audit.md")
    # Recruiter review (task 108): the runtime prompt asks Claude to
    # also produce a simulated recruiter/hiring-manager review of the
    # tailored resume. Surfacing the request in the run log makes the
    # contract visible even though detection of whether Claude wrote
    # the file happens at output validation time below.
    _append_progress(log_path, "recruiter review requested")
    _append_progress(
        log_path,
        "recruiter review expected at output/recruiter_review.md",
    )
    heartbeat_interval = _heartbeat_interval_seconds()
    heartbeat_stop = threading.Event()
    heartbeat_thread: Optional[threading.Thread] = None
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(
                f"$ {' '.join(argv)}  (cwd={run_dir})\n"
            )
            log.flush()
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=str(run_dir),
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            except FileNotFoundError as exc:
                _append_progress(
                    log_path,
                    f"provider {provider.id!r} binary not found: {binary}",
                )
                _append_progress(log_path, "marking run failed")
                return _record_failure(
                    db,
                    run,
                    f"provider {provider.id!r} binary not found: {binary} ({exc})",
                )
            except OSError as exc:
                _append_progress(
                    log_path,
                    f"failed to launch provider {provider.id!r} binary {binary}",
                )
                _append_progress(log_path, "marking run failed")
                return _record_failure(
                    db,
                    run,
                    f"failed to launch provider {provider.id!r} binary {binary}: {exc}",
                )
            _append_progress(log_path, "Claude Code process started")
            # Feed the prompt to Claude via stdin and close it immediately so
            # Claude knows there's no more input coming. Large prompts can
            # exceed ARG_MAX if passed as argv, and stdin keeps the prompt out
            # of the process listing. A BrokenPipe means Claude exited before
            # reading the full prompt — recoverable, the wait() below records
            # the exit code.
            if process.stdin is not None:
                try:
                    process.stdin.write(prompt_text.encode("utf-8"))
                except (BrokenPipeError, OSError):
                    pass
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            if heartbeat_interval > 0:
                heartbeat_thread = threading.Thread(
                    target=_run_heartbeat,
                    args=(progress_path, heartbeat_stop, heartbeat_interval),
                    daemon=True,
                )
                heartbeat_thread.start()
            try:
                returncode = process.wait()
            finally:
                heartbeat_stop.set()
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=2.0)
    except OSError as exc:
        _append_progress(log_path, f"failed to write run log: {exc}")
        _append_progress(log_path, "marking run failed")
        return _record_failure(
            db,
            run,
            f"failed to write run log: {exc}",
        )

    _append_progress(
        log_path, f"Claude Code process exited with code {returncode}"
    )

    if returncode != 0:
        _append_progress(log_path, "marking run failed")
        run.status = "failed"
        run.error_message = (
            f"claude exited with code {returncode}; see {log_path}"
        )
    else:
        extraction_docx_relpath: Optional[str] = (
            f"{INPUT_DIRNAME}/{extraction.docx_path.name}"
            if extraction.docx_found
            else None
        )
        try:
            _render_docx_from_structured_json(
                run_dir, log_path, extraction_docx_relpath=extraction_docx_relpath
            )
            _validate_resume_suggestions(run_dir, log_path)
        except RendererError as exc:
            _append_progress(log_path, "marking run failed")
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = _now()
            db.commit()
            db.refresh(run)
            return run

        _append_progress(log_path, "validating output files")
        missing = _missing_outputs(run_dir)
        if missing:
            for path in missing:
                _append_progress(log_path, f"missing expected output file: {path}")
            _append_progress(log_path, "marking run failed")
            run.status = "failed"
            run.error_message = "expected output file missing: " + ", ".join(missing)
        else:
            _append_progress(log_path, "output contract satisfied")
            run.status = "completed"
            run.error_message = None
        # Optional recruiter review (task 108). Always expected — the
        # review is independent of whether a DOCX was staged.
        recruiter_review_path = (
            run_dir / OUTPUT_DIRNAME / RECRUITER_REVIEW_FILENAME
        )
        if not recruiter_review_path.is_file():
            _append_progress(
                log_path,
                "warning: recruiter review missing at "
                f"{OUTPUT_DIRNAME}/{RECRUITER_REVIEW_FILENAME}",
            )
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run
