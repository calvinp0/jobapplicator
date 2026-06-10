"""Shared helpers for importing user files into app-managed folders.

Task 121 replaces the manual ``Source Path`` text fields in Settings with
a real file upload flow. Browsers do not reliably expose a full local
source path for security reasons, so the contract is:

    choose file -> upload bytes -> backend copies into a managed folder

This module owns the security-sensitive parts of that copy: extension
validation, filename sanitization (defeating path traversal), and
collision-safe naming. The routers handle HTTP plumbing and turning the
saved file into a discovery record.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Extensions we can actually read downstream. PDF is intentionally absent:
# the discovery/extraction layers (``master_resume_discovery`` /
# ``evidence_source_discovery``) only understand ``.docx``/``.md``/``.txt``,
# so accepting a ``.pdf`` would copy a file tailoring runs could never use.
MASTER_RESUME_EXTENSIONS: tuple[str, ...] = (".docx", ".md", ".txt")
EVIDENCE_EXTENSIONS: tuple[str, ...] = (".md", ".txt", ".docx")


class FileImportError(ValueError):
    """Raised when an upload is rejected (bad extension, unsafe name)."""


@dataclass(frozen=True)
class ImportedFile:
    """Result of copying an uploaded file into a managed folder."""

    name: str
    stored_path: Path
    source_format: str
    original_filename: str


def sanitize_filename(
    original: str, allowed_extensions: Iterable[str]
) -> tuple[str, str]:
    """Return a safe ``(filename, extension)`` pair or raise ``FileImportError``.

    Strips any directory components (so ``../../etc/passwd`` cannot escape
    the managed folder), lower-cases and validates the extension against
    ``allowed_extensions``, and slugifies the stem to ASCII-safe
    characters. The returned extension keeps its leading dot.
    """
    allowed = tuple(e.lower() for e in allowed_extensions)
    # Normalize both separator styles, then take only the final component.
    base = os.path.basename(str(original).replace("\\", "/")).strip()
    if not base or base in {".", ".."}:
        raise FileImportError("Invalid filename.")

    stem, ext = os.path.splitext(base)
    ext = ext.lower()
    if ext not in allowed:
        pretty = ", ".join(allowed)
        raise FileImportError(
            f"Unsupported file type '{ext or base}'. Allowed: {pretty}."
        )

    # Collapse anything that is not a safe filename character into "_".
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not slug:
        slug = "import"
    return f"{slug}{ext}", ext


def unique_target_path(directory: Path, safe_name: str) -> Path:
    """Return a non-colliding path under ``directory`` for ``safe_name``.

    Appends ``_2``, ``_3``, … before the extension if needed so an import
    never silently overwrites an existing file.
    """
    target = directory / safe_name
    if not target.exists():
        return target
    stem, ext = os.path.splitext(safe_name)
    counter = 2
    while True:
        candidate = directory / f"{stem}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def save_imported_file(
    directory: Path,
    original_filename: str,
    data: bytes,
    allowed_extensions: Iterable[str],
) -> ImportedFile:
    """Validate and copy ``data`` into ``directory`` under a safe name."""
    safe_name, ext = sanitize_filename(original_filename, allowed_extensions)
    directory.mkdir(parents=True, exist_ok=True)
    target = unique_target_path(directory, safe_name)
    target.write_bytes(data)
    # Preserve the user-facing original name (basename only) as metadata.
    display_original = (
        os.path.basename(str(original_filename).replace("\\", "/")).strip()
        or safe_name
    )
    return ImportedFile(
        name=target.name,
        stored_path=target,
        source_format=ext.lstrip("."),
        original_filename=display_original,
    )
