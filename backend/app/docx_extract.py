"""Backend-side DOCX-to-markdown extraction for tailoring runs.

When a run's ``input/`` directory carries a source resume as a ``.docx``
file (rather than only as ``master_resume.md``), the worker needs a
deterministic, plain-text projection of the document before invoking
Claude. The DOCX is preserved as the formatting source; the extracted
markdown serves as the evidence source the runtime prompt can quote from.

This module is intentionally narrow: it inspects ``input/`` for a known
DOCX filename, extracts visible paragraphs and tables in document order
with ``python-docx``, and writes the result to
``input/master_resume_extracted.md``. Failures produce
``input/master_resume_extraction_error.md`` so the worker can decide
whether to continue (another resume source exists) or fail the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

EXTRACTED_FILENAME = "master_resume_extracted.md"
EXTRACTION_ERROR_FILENAME = "master_resume_extraction_error.md"

# Accepted source resume DOCX names, searched in order inside ``input/``.
# Mirrors ``word_handoff.ACCEPTED_RESUME_DOCX_NAMES`` so the auto path and
# the word-handoff path agree on what counts as a source DOCX.
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


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of an extraction attempt on a run input directory.

    ``docx_path`` is the source DOCX that was inspected (``None`` when no
    accepted DOCX filename was present). ``extracted_path`` is set when
    extraction succeeded and the markdown projection was written.
    ``error_path``/``error_message`` are set when a DOCX existed but
    extraction failed; the worker uses ``has_other_resume_source`` to
    decide whether to continue or fail the run.
    """

    docx_path: Optional[Path] = None
    extracted_path: Optional[Path] = None
    error_path: Optional[Path] = None
    error_message: Optional[str] = None
    has_other_resume_source: bool = False

    @property
    def docx_found(self) -> bool:
        return self.docx_path is not None

    @property
    def extracted(self) -> bool:
        return self.extracted_path is not None

    @property
    def failed(self) -> bool:
        return self.error_message is not None


def _find_first_existing(
    input_dir: Path, names: tuple[str, ...]
) -> Optional[Path]:
    for name in names:
        candidate = input_dir / name
        if candidate.is_file():
            return candidate
    return None


def find_source_resume_docx(input_dir: Path) -> Optional[Path]:
    """Return the first accepted DOCX filename present in ``input_dir``."""
    return _find_first_existing(Path(input_dir), ACCEPTED_RESUME_DOCX_NAMES)


def find_source_resume_markdown(input_dir: Path) -> Optional[Path]:
    """Return the first accepted markdown resume filename present in ``input_dir``."""
    return _find_first_existing(Path(input_dir), ACCEPTED_RESUME_MD_NAMES)


def _heading_level(style_name: Optional[str]) -> Optional[int]:
    """Return the markdown heading level for a Word paragraph style.

    ``Heading 1``..``Heading 9`` map to ``#``..``#########``. ``Title``
    is treated as level 1 since most resumes use it for the candidate
    name. Anything else returns ``None`` (render as a regular paragraph).
    """
    if not style_name:
        return None
    name = style_name.strip()
    if name == "Title":
        return 1
    if name.startswith("Heading "):
        tail = name[len("Heading "):].strip()
        if tail.isdigit():
            level = int(tail)
            if 1 <= level <= 6:
                return level
            # Word allows Heading 7-9; clamp so we still produce valid HTML-ish
            # markdown rather than dropping the heading entirely.
            return 6
    return None


def _render_paragraph(text: str, style_name: Optional[str]) -> str:
    text = text.rstrip()
    if not text:
        return ""
    level = _heading_level(style_name)
    if level is not None:
        return f"{'#' * level} {text}"
    # Bulleted list paragraphs in Word carry a style name like
    # ``List Bullet`` / ``List Bullet 2`` — best-effort detect a few
    # common variants and emit a markdown bullet.
    if style_name and "List" in style_name and "Bullet" in style_name:
        return f"- {text}"
    if style_name and "List" in style_name and "Number" in style_name:
        return f"1. {text}"
    return text


def _render_table(rows: list[list[str]]) -> str:
    """Render a Word table as a readable markdown-like block.

    Uses a pipe-separated layout with a header separator when the table
    has more than one row, so the result reads cleanly in plain markdown
    viewers.
    """
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [
        [cell.replace("\n", " ").replace("|", "\\|").strip() for cell in row]
        + [""] * (width - len(row))
        for row in rows
    ]
    lines = ["| " + " | ".join(row) + " |" for row in normalized]
    if len(lines) > 1:
        sep = "| " + " | ".join(["---"] * width) + " |"
        lines.insert(1, sep)
    return "\n".join(lines)


def _extract_body_blocks(document) -> list[str]:
    """Iterate the document body in order and render paragraphs + tables.

    Returns a list of markdown blocks (paragraphs, headings, bullets,
    rendered tables). Blank paragraphs are dropped so the output reads
    cleanly without long runs of empty lines.
    """
    from docx.oxml.ns import qn  # type: ignore[import-not-found]
    from docx.table import Table  # type: ignore[import-not-found]
    from docx.text.paragraph import Paragraph  # type: ignore[import-not-found]

    blocks: list[str] = []
    body = document.element.body
    para_tag = qn("w:p")
    tbl_tag = qn("w:tbl")
    for child in body.iterchildren():
        if child.tag == para_tag:
            para = Paragraph(child, document)
            style_name = para.style.name if para.style is not None else None
            rendered = _render_paragraph(para.text, style_name)
            if rendered:
                blocks.append(rendered)
        elif child.tag == tbl_tag:
            table = Table(child, document)
            rows: list[list[str]] = []
            for row in table.rows:
                rows.append([cell.text for cell in row.cells])
            rendered = _render_table(rows)
            if rendered:
                blocks.append(rendered)
    return blocks


def _render_extracted_markdown(docx_relpath: str, blocks: list[str]) -> str:
    body = "\n\n".join(blocks).rstrip()
    if not body:
        body = "(no extractable text)"
    return (
        "# Extracted Master Resume\n"
        "\n"
        f"Source DOCX: {docx_relpath}\n"
        "\n"
        "## Extracted Text\n"
        "\n"
        f"{body}\n"
    )


def _render_extraction_error(docx_relpath: str, message: str) -> str:
    return (
        "# Master Resume Extraction Error\n"
        "\n"
        f"Source DOCX: {docx_relpath}\n"
        "\n"
        f"Reason: {message}\n"
    )


def extract_docx_to_markdown(docx_path: Path, dest_path: Path) -> None:
    """Extract paragraphs and tables from ``docx_path`` into ``dest_path``.

    Raises any ``python-docx`` error encountered while opening or reading
    the file; the caller is responsible for surfacing the failure (e.g.
    writing the ``master_resume_extraction_error.md`` sibling).
    """
    from docx import Document  # type: ignore[import-not-found]

    document = Document(str(docx_path))
    blocks = _extract_body_blocks(document)
    relpath = f"input/{docx_path.name}"
    dest_path.write_text(
        _render_extracted_markdown(relpath, blocks), encoding="utf-8"
    )


def extract_master_resume_if_present(input_dir: Path) -> ExtractionResult:
    """Look for a source DOCX in ``input_dir`` and extract it if found.

    Side effects:

    - On success: writes ``master_resume_extracted.md`` next to the DOCX
      and removes any stale ``master_resume_extraction_error.md``.
    - On failure: writes ``master_resume_extraction_error.md`` (with the
      DOCX path and exception message) and removes any stale extracted
      markdown so a partial previous run does not look authoritative.
    - When no DOCX is found: makes no filesystem changes and returns a
      result with ``docx_path=None``.

    The function never raises; the caller inspects ``ExtractionResult``
    to decide whether to continue.
    """
    input_dir = Path(input_dir)
    extracted_path = input_dir / EXTRACTED_FILENAME
    error_path = input_dir / EXTRACTION_ERROR_FILENAME

    docx_path = find_source_resume_docx(input_dir)
    md_path = find_source_resume_markdown(input_dir)
    has_other = md_path is not None

    if docx_path is None:
        return ExtractionResult(has_other_resume_source=has_other)

    try:
        extract_docx_to_markdown(docx_path, extracted_path)
    except Exception as exc:  # pragma: no cover - exact type varies by failure mode
        message = f"{type(exc).__name__}: {exc}"
        error_path.write_text(
            _render_extraction_error(f"input/{docx_path.name}", message),
            encoding="utf-8",
        )
        # Drop any stale extracted file so a previous successful run does
        # not silently masquerade as the current source of truth.
        try:
            extracted_path.unlink()
        except FileNotFoundError:
            pass
        return ExtractionResult(
            docx_path=docx_path,
            error_path=error_path,
            error_message=message,
            has_other_resume_source=has_other,
        )

    try:
        error_path.unlink()
    except FileNotFoundError:
        pass

    return ExtractionResult(
        docx_path=docx_path,
        extracted_path=extracted_path,
        has_other_resume_source=has_other,
    )
