from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .run_directory import (
    METADATA_FILENAME,
    TAILORING_METHOD_WORD_HANDOFF,
    set_run_status,
    set_tailoring_method,
)

# Layout inside ``runs/<run_id>/word_handoff/``. The numeric prefixes are
# intentional — the directory is opened by a human, and the prefix makes the
# intended reading order obvious.
WORD_HANDOFF_DIRNAME = "word_handoff"
RESUME_DOCX_FILENAME = "01_resume_for_claude_word.docx"
PROMPT_FILENAME = "02_prompt_for_claude_word.txt"
JOB_DESCRIPTION_FILENAME = "03_job_description.txt"
INSTRUCTIONS_FILENAME = "04_instructions.md"

RUN_LOG_FILENAME = "run.log"

WORD_HANDOFF_STATUS = "word_handoff_ready"

# Where the user is asked to save the Claude for Word output. Relative to the
# run directory; surfaced to the operator via 04_instructions.md and the run
# log so the import step (a follow-up task) knows where to look.
EXPECTED_WORD_OUTPUT_RELPATH = "output/word_tailored_resume.docx"

# Accepted source resume DOCX names, searched in order inside ``input/``.
# ``master_resume.docx`` matches the project's existing input naming; the
# others cover common alternatives an operator might use locally.
ACCEPTED_RESUME_DOCX_NAMES: tuple[str, ...] = (
    "master_resume.docx",
    "resume.docx",
    "base_resume.docx",
    "original_resume.docx",
)

ACCEPTED_RESUME_MD_NAMES: tuple[str, ...] = (
    "master_resume.md",
    "resume.md",
    "base_resume.md",
    "original_resume.md",
)

ACCEPTED_JOB_DESCRIPTION_NAMES: tuple[str, ...] = (
    "job_description.md",
    "job_description.txt",
    "jd.md",
    "jd.txt",
)


class WordHandoffError(ValueError):
    """Raised when a Word handoff package cannot be assembled."""


@dataclass(frozen=True)
class WordHandoffInfo:
    run_dir: Path
    handoff_dir: Path
    resume_docx_copied: bool
    resume_markdown_included: bool


def _find_first_existing(input_dir: Path, names: tuple[str, ...]) -> Optional[Path]:
    for name in names:
        candidate = input_dir / name
        if candidate.is_file():
            return candidate
    return None


def _append_run_log(run_dir: Path, message: str) -> None:
    """Append a worker-style ``jobapply:`` progress line to ``run.log``.

    Best-effort — handoff creation must not fail because of a log write.
    """
    log_path = run_dir / RUN_LOG_FILENAME
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"jobapply: {message}\n")
    except OSError:
        pass


def _render_prompt(
    job_description: str,
    *,
    resume_markdown: Optional[str] = None,
) -> str:
    parts = [
        "Use this document as the source resume and tailor it for the target job.",
        "",
        "Preserve the existing Word formatting:",
        "- Keep fonts, margins, section spacing, headings, bullets, and page layout.",
        "- Edit inside the resume rather than rebuilding the document from scratch.",
        "- Use tracked changes if available.",
        "- Do not invent employers, dates, degrees, technologies, metrics, "
        "publications, awards, responsibilities, or credentials.",
        "- Only strengthen claims that are supported by the original resume.",
        "- Prefer concise, high-signal bullets.",
        "",
        "Edit these areas first:",
        "1. Summary",
        "2. Skills",
        "3. Most relevant experience bullets",
        "4. Project bullets if they match the job",
        "",
        "After editing, add or update these sections at the end of the document:",
        "CHANGE LOG",
        "CLAIM AUDIT",
        "",
        "## Target Job Description",
        "",
        job_description.rstrip(),
        "",
    ]
    if resume_markdown is not None:
        parts.extend(
            [
                "## Resume Markdown (fallback context)",
                "",
                resume_markdown.rstrip(),
                "",
            ]
        )
    return "\n".join(parts)


_INSTRUCTIONS_BODY = """\
# Claude for Word Handoff Instructions

1. Open 01_resume_for_claude_word.docx in Microsoft Word.
2. Open Claude for Word.
3. Paste the contents of 02_prompt_for_claude_word.txt.
4. Ask Claude to edit using tracked changes.
5. Save the completed file as ../output/word_tailored_resume.docx.
6. Return to JobApplicator and import the Word result.
"""


def create_word_handoff_package(
    run_dir: Path,
    *,
    now: Optional[datetime] = None,
) -> WordHandoffInfo:
    """Assemble the Claude for Word handoff package for an existing run.

    Reads source resume + job description from ``<run_dir>/input/`` (accepted
    names listed above), copies the DOCX into ``word_handoff/`` when present,
    writes the prompt / job description / instructions files, and transitions
    metadata to ``tailoring_method=word_handoff`` and
    ``status=word_handoff_ready``.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise WordHandoffError(f"run directory does not exist: {run_dir}")

    input_dir = run_dir / "input"
    if not input_dir.is_dir():
        raise WordHandoffError(
            f"run input directory does not exist: {input_dir}"
        )

    if not (run_dir / METADATA_FILENAME).is_file():
        raise WordHandoffError(
            f"metadata.json not found in run directory: {run_dir}"
        )

    jd_src = _find_first_existing(input_dir, ACCEPTED_JOB_DESCRIPTION_NAMES)
    if jd_src is None:
        raise WordHandoffError(
            "no job description found in run input "
            f"(expected one of: {list(ACCEPTED_JOB_DESCRIPTION_NAMES)})"
        )

    docx_src = _find_first_existing(input_dir, ACCEPTED_RESUME_DOCX_NAMES)
    md_src = _find_first_existing(input_dir, ACCEPTED_RESUME_MD_NAMES)
    if docx_src is None and md_src is None:
        raise WordHandoffError(
            "no source resume found in run input "
            f"(expected one of: "
            f"{list(ACCEPTED_RESUME_DOCX_NAMES + ACCEPTED_RESUME_MD_NAMES)})"
        )

    handoff_dir = run_dir / WORD_HANDOFF_DIRNAME
    handoff_dir.mkdir(parents=True, exist_ok=True)

    resume_docx_copied = False
    if docx_src is not None:
        shutil.copyfile(docx_src, handoff_dir / RESUME_DOCX_FILENAME)
        resume_docx_copied = True

    jd_text = jd_src.read_text(encoding="utf-8")
    resume_md_text: Optional[str] = None
    if md_src is not None:
        resume_md_text = md_src.read_text(encoding="utf-8")

    prompt_text = _render_prompt(jd_text, resume_markdown=resume_md_text)
    (handoff_dir / PROMPT_FILENAME).write_text(prompt_text, encoding="utf-8")
    (handoff_dir / JOB_DESCRIPTION_FILENAME).write_text(jd_text, encoding="utf-8")
    (handoff_dir / INSTRUCTIONS_FILENAME).write_text(
        _INSTRUCTIONS_BODY, encoding="utf-8"
    )

    # Persist the workflow transition atomically-enough: both metadata writes
    # happen here so a caller never sees ``tailoring_method=word_handoff``
    # without ``status=word_handoff_ready``.
    set_tailoring_method(run_dir, TAILORING_METHOD_WORD_HANDOFF, now=now)
    set_run_status(run_dir, WORD_HANDOFF_STATUS, now=now)

    _append_run_log(run_dir, "created Claude for Word handoff package")
    _append_run_log(run_dir, f"handoff_dir={handoff_dir}")
    _append_run_log(
        run_dir, f"expected Word output={EXPECTED_WORD_OUTPUT_RELPATH}"
    )

    return WordHandoffInfo(
        run_dir=run_dir,
        handoff_dir=handoff_dir,
        resume_docx_copied=resume_docx_copied,
        resume_markdown_included=resume_md_text is not None,
    )
