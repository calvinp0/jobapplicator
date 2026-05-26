"""Discovery of evidence source files stored under ``candidate_context/``.

Evidence sources are any supporting factual file the user wants Claude to
read alongside the primary master resume. The repository ships a small
seeded ``EvidenceBank`` DB row plus a handful of markdown files on disk;
real users typically grow this set with additional resume variants,
project notes, publication lists, and so on. This module scans the
relevant ``candidate_context/`` subfolders, returns each discovery as an
``EvidenceSourceFile`` record with a stable ``fs:`` id, and resolves a
discovered id back to its on-disk path for staging.

Combine these filesystem-backed records with the database-backed
``EvidenceBank`` rows at the API layer (see
``app/routers/evidence_sources.py``) — there is intentionally no shared
DB table, since the file-on-disk shape and the seeded singleton are
served from different storage and a migration would buy nothing.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# File extensions we treat as readable evidence sources. Anything else
# under the discovered folders is ignored.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".md", ".txt", ".docx")

# Filename patterns we always skip — Word lock files, AppleDouble
# metadata, and similar transient junk.
HIDDEN_PREFIXES: tuple[str, ...] = (".~lock", "~$", "._")
HIDDEN_EXACT: frozenset[str] = frozenset({".DS_Store", "Thumbs.db"})

FILESYSTEM_ID_PREFIX = "fs:"

# Subfolders of ``candidate_context/`` we scan, paired with the
# ``source_type`` we tag discovered files with. Files in the root of
# ``candidate_context/`` are intentionally not scanned — they are the
# stable per-candidate context files (``candidate_profile.md`` etc.)
# already staged into every run as named inputs.
SUBFOLDER_SOURCE_TYPES: tuple[tuple[str, str], ...] = (
    ("evidence_banks", "evidence_bank"),
    ("project_notes", "project_note"),
    ("resume_variants", "resume_variant"),
    ("master_resumes", "master_resume"),
)


@dataclass(frozen=True)
class EvidenceSourceFile:
    """An evidence source discovered from the filesystem.

    ``id`` is a stable synthetic id derived from the file's
    candidate-context-relative path. ``absolute_path`` is the real
    on-disk location; the API never surfaces it. ``source_path`` is the
    project-relative form returned to clients. ``source_format`` is the
    lowercase extension without the leading dot. ``source_type`` reflects
    which subfolder the file was discovered in.
    """

    id: str
    name: str
    source_type: str
    source_format: str
    source_path: str
    absolute_path: Path
    updated_at: datetime


class EvidenceSourceDiscoveryError(ValueError):
    """Raised when a filesystem evidence source cannot be resolved or read."""


def default_candidate_context_root() -> Path:
    """Where candidate context lives by default.

    Mirrors ``run_directory.default_candidate_context_root`` so a test or
    deployment that overrides ``JOBAPPLY_CANDIDATE_CONTEXT_ROOT`` picks
    up evidence discoveries from the same place.
    """
    explicit = os.environ.get("JOBAPPLY_CANDIDATE_CONTEXT_ROOT")
    if explicit:
        return Path(explicit)
    # backend/app/evidence_source_discovery.py -> backend/app -> backend -> repo
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "candidate_context"


def _is_hidden(name: str) -> bool:
    if name in HIDDEN_EXACT:
        return True
    for prefix in HIDDEN_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _stable_id_for(relative_path: str) -> str:
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"{FILESYSTEM_ID_PREFIX}{digest}"


def _project_relative_source_path(absolute_path: Path) -> str:
    parts = absolute_path.parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "candidate_context":
            return "/".join(parts[i:])
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return absolute_path.name


def _build_record(
    candidate_root: Path,
    file_path: Path,
    source_type: str,
) -> Optional[EvidenceSourceFile]:
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return None
    if _is_hidden(file_path.name):
        return None
    try:
        relative = file_path.relative_to(candidate_root).as_posix()
    except ValueError:
        relative = file_path.name
    fs_id = _stable_id_for(relative)
    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return EvidenceSourceFile(
        id=fs_id,
        name=file_path.name,
        source_type=source_type,
        source_format=suffix.lstrip("."),
        source_path=_project_relative_source_path(file_path),
        absolute_path=file_path,
        updated_at=updated_at,
    )


def list_filesystem_evidence_sources(
    candidate_root: Optional[Path] = None,
) -> list[EvidenceSourceFile]:
    """Return all supported evidence files under ``candidate_root`` subfolders.

    Returns an empty list when ``candidate_root`` does not exist. Each
    configured subfolder is scanned non-recursively; missing subfolders
    are skipped silently so a fresh repo with only one or two of the
    folders still works.
    """
    root = Path(candidate_root) if candidate_root is not None else default_candidate_context_root()
    if not root.is_dir():
        return []
    records: list[EvidenceSourceFile] = []
    seen_ids: set[str] = set()
    for subfolder, source_type in SUBFOLDER_SOURCE_TYPES:
        sub = root / subfolder
        if not sub.is_dir():
            continue
        for entry in sorted(sub.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file():
                continue
            record = _build_record(root, entry, source_type)
            if record is None:
                continue
            if record.id in seen_ids:
                continue
            seen_ids.add(record.id)
            records.append(record)
    return records


def is_filesystem_id(source_id: str) -> bool:
    return source_id.startswith(FILESYSTEM_ID_PREFIX)


def resolve_filesystem_evidence_source(
    source_id: str, candidate_root: Optional[Path] = None
) -> Optional[EvidenceSourceFile]:
    """Return the discovered evidence source for ``source_id`` or ``None``."""
    if not is_filesystem_id(source_id):
        return None
    for record in list_filesystem_evidence_sources(candidate_root=candidate_root):
        if record.id == source_id:
            return record
    return None


def load_filesystem_evidence_text(record: EvidenceSourceFile) -> str:
    """Return the evidence source as text.

    ``.md`` / ``.txt`` files return their raw UTF-8 content. ``.docx``
    files are run through the project's DOCX extractor so the staged
    sibling can carry a markdown projection.
    """
    suffix = record.source_format.lower()
    if suffix in ("md", "txt"):
        return record.absolute_path.read_text(encoding="utf-8")
    if suffix == "docx":
        return _extract_docx_body_markdown(record.absolute_path)
    raise EvidenceSourceDiscoveryError(
        f"unsupported evidence source format: {record.source_format!r}"
    )


def _extract_docx_body_markdown(docx_path: Path) -> str:
    """Render a DOCX as plain markdown using the project's docx_extract.

    Reuses ``docx_extract._extract_body_blocks`` so the projection is
    consistent with the master-resume extraction path. Import is deferred
    so callers that only need discovery do not pay python-docx import
    cost on every list call.
    """
    from docx import Document  # type: ignore[import-not-found]

    from .docx_extract import _extract_body_blocks

    document = Document(str(docx_path))
    blocks = _extract_body_blocks(document)
    return "\n\n".join(blocks).rstrip() + ("\n" if blocks else "")
