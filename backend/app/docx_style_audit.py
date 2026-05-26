"""Lightweight deterministic DOCX style inspection for the fidelity audit.

The tailoring contract treats ``input/master_resume.docx`` as the
formatting/template source of truth. Claude is asked to produce
``output/tailored_resume.docx`` that preserves the master's visual
identity (centered header, colored headings, bullet lists, separators).
This module gives the backend a *coarse* deterministic view of the DOCX
so tests and future validation can spot the obvious regressions (lost
centered header, dropped bullets, stripped heading color) without
requiring Microsoft Word or implementing a full visual diff.

Use ``python-docx``; do not require any new dependency. Coverage is
intentionally narrow — anything beyond the audit checklist belongs in
the LLM-produced ``output/template_fidelity_audit.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Paragraphs above this index are considered part of the header/contact
# block for the "centered header" check. A typical resume header runs 1–4
# paragraphs (name, title/contact line, links), so 4 is a generous window.
HEADER_PARAGRAPH_LOOKAHEAD = 4


@dataclass(frozen=True)
class DocxStyleSummary:
    """Coarse style summary of a single DOCX.

    Every field is deliberately a simple ``bool`` or ``int`` so the
    summary can be compared between source and tailored output with a
    plain equality check or a small diff.
    """

    header_centered: bool
    contact_centered: bool
    colored_heading_count: int
    bullet_paragraph_count: int
    numbered_paragraph_count: int
    total_paragraph_count: int

    @property
    def has_colored_headings(self) -> bool:
        return self.colored_heading_count > 0

    @property
    def has_bullets(self) -> bool:
        return self.bullet_paragraph_count > 0


def _alignment_is_center(paragraph) -> bool:
    """Return True when the paragraph's effective alignment is centered.

    ``paragraph.alignment`` is a ``WD_ALIGN_PARAGRAPH`` enum on
    python-docx. ``CENTER`` has int value 1; we compare via the enum
    name to stay tolerant of python-docx version drift without importing
    the constant at module top level.
    """
    alignment = getattr(paragraph, "alignment", None)
    if alignment is None:
        return False
    name = getattr(alignment, "name", None) or str(alignment)
    return name.upper() == "CENTER"


def _style_name(paragraph) -> Optional[str]:
    style = getattr(paragraph, "style", None)
    if style is None:
        return None
    return getattr(style, "name", None)


def _style_is_heading(style_name: Optional[str]) -> bool:
    if not style_name:
        return False
    name = style_name.strip()
    return name == "Title" or name.startswith("Heading ")


def _paragraph_has_color(paragraph) -> bool:
    """Return True when any run in the paragraph carries an explicit color.

    A heading style with the Word default "Automatic" color is not
    enough to count as "colored" — we need an explicit RGB on at least
    one run so a black-on-white heading does not register as colored.
    """
    for run in paragraph.runs:
        font = getattr(run, "font", None)
        if font is None:
            continue
        color = getattr(font, "color", None)
        if color is None:
            continue
        rgb = getattr(color, "rgb", None)
        if rgb is None:
            continue
        return True
    return False


def _is_list_paragraph(style_name: Optional[str], kind: str) -> bool:
    """Detect ``List Bullet`` / ``List Number`` style families.

    Word allows numbered variants (``List Bullet 2``, ``List Number 3``)
    that the extractor's existing heuristic also tolerates. ``kind`` is
    ``"bullet"`` or ``"number"``.
    """
    if not style_name:
        return False
    if "List" not in style_name:
        return False
    if kind == "bullet" and "Bullet" in style_name:
        return True
    if kind == "number" and ("Number" in style_name or "Numbered" in style_name):
        return True
    return False


def summarize_docx_style(path: Path) -> DocxStyleSummary:
    """Open ``path`` with python-docx and return a ``DocxStyleSummary``.

    Raises any error python-docx encounters while opening the file —
    the caller is responsible for surfacing a missing or corrupt DOCX,
    since this helper is also useful in tests where a clear failure is
    preferable to a silently empty summary.
    """
    from docx import Document  # type: ignore[import-not-found]

    document = Document(str(path))
    paragraphs = list(document.paragraphs)

    header_centered = False
    contact_centered = False
    colored_heading_count = 0
    bullet_paragraph_count = 0
    numbered_paragraph_count = 0

    # First non-empty paragraph -> header. Next non-empty centered paragraph
    # within the lookahead window -> contact line.
    seen_header = False
    for idx, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        if not seen_header:
            header_centered = _alignment_is_center(paragraph)
            seen_header = True
            continue
        if not contact_centered and idx < HEADER_PARAGRAPH_LOOKAHEAD:
            if _alignment_is_center(paragraph):
                contact_centered = True

    for paragraph in paragraphs:
        style_name = _style_name(paragraph)
        if _style_is_heading(style_name) and _paragraph_has_color(paragraph):
            colored_heading_count += 1
        if _is_list_paragraph(style_name, "bullet"):
            bullet_paragraph_count += 1
        elif _is_list_paragraph(style_name, "number"):
            numbered_paragraph_count += 1

    return DocxStyleSummary(
        header_centered=header_centered,
        contact_centered=contact_centered,
        colored_heading_count=colored_heading_count,
        bullet_paragraph_count=bullet_paragraph_count,
        numbered_paragraph_count=numbered_paragraph_count,
        total_paragraph_count=sum(1 for p in paragraphs if p.text.strip()),
    )


@dataclass(frozen=True)
class FidelityIssue:
    """One observed regression between source and tailored DOCX."""

    feature: str
    detail: str


def compare_template_fidelity(
    source: DocxStyleSummary, output: DocxStyleSummary
) -> list[FidelityIssue]:
    """Compare a source and output style summary and return regressions.

    Only the obvious "source had it, output dropped it" cases are
    flagged. Cases where the output adds styling the source did not have
    are ignored — that is a stylistic choice, not a fidelity regression.
    """
    issues: list[FidelityIssue] = []
    if source.header_centered and not output.header_centered:
        issues.append(
            FidelityIssue(
                feature="centered header",
                detail="source resume centered the name/header block but "
                "the tailored output did not",
            )
        )
    if source.contact_centered and not output.contact_centered:
        issues.append(
            FidelityIssue(
                feature="centered contact",
                detail="source resume centered the contact line but the "
                "tailored output did not",
            )
        )
    if source.has_colored_headings and not output.has_colored_headings:
        issues.append(
            FidelityIssue(
                feature="colored section headings",
                detail="source resume used colored section headings but the "
                "tailored output uses default heading color",
            )
        )
    if source.has_bullets and not output.has_bullets:
        issues.append(
            FidelityIssue(
                feature="bullet lists",
                detail="source resume used bullet list paragraphs but the "
                "tailored output has none",
            )
        )
    return issues
