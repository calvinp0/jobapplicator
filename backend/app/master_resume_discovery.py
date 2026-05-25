"""Discovery of master resume files stored under ``candidate_context/master_resumes/``.

The repository ships ``MasterResume`` rows in SQLite (the seeded demo
resume) but real users keep their actual resumes as files on disk —
typically a ``.docx`` exported from Word, but ``.md`` and ``.txt`` are
also supported. This module is the bridge: it scans a directory, returns
discovered files as ``FilesystemMasterResume`` records, and resolves a
stable id back to the originating file.

The list endpoint combines these filesystem-backed records with the
database-backed ``MasterResume`` rows so the frontend selector shows
both. Filesystem entries carry a synthetic ``fs:<hash>`` id; the runs
router recognizes the prefix and stages the discovered file into the
run's ``input/`` directory.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# File extensions we treat as readable master resumes. Anything else
# under the directory is ignored.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".docx", ".md", ".txt")

# Filename patterns we always skip — Word lock files, AppleDouble
# metadata, and similar transient junk that would otherwise pollute the
# selector.
HIDDEN_PREFIXES: tuple[str, ...] = (".~lock", "~$", "._")
HIDDEN_EXACT: frozenset[str] = frozenset({".DS_Store", "Thumbs.db"})

FILESYSTEM_ID_PREFIX = "fs:"


@dataclass(frozen=True)
class FilesystemMasterResume:
    """A master resume discovered from the filesystem.

    ``id`` is a stable synthetic id derived from the file's relative
    path. ``absolute_path`` is the real on-disk location; the API never
    surfaces it. ``source_path`` is the project-relative form returned
    to clients. ``source_format`` is the lowercase extension without
    the leading dot.
    """

    id: str
    name: str
    source_path: str
    source_format: str
    absolute_path: Path
    updated_at: datetime


class MasterResumeDiscoveryError(ValueError):
    """Raised when a filesystem master resume cannot be resolved or read."""


def default_master_resumes_root() -> Path:
    """Where master resume files live by default.

    Override with ``JOBAPPLY_MASTER_RESUMES_ROOT`` for tests. Falls back
    to ``candidate_context/master_resumes`` under the
    ``JOBAPPLY_CANDIDATE_CONTEXT_ROOT`` (or the repository default).
    """
    explicit = os.environ.get("JOBAPPLY_MASTER_RESUMES_ROOT")
    if explicit:
        return Path(explicit)
    candidate_root = os.environ.get("JOBAPPLY_CANDIDATE_CONTEXT_ROOT")
    if candidate_root:
        return Path(candidate_root) / "master_resumes"
    # backend/app/master_resume_discovery.py -> backend/app -> backend -> repo
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "candidate_context" / "master_resumes"


def _is_hidden(name: str) -> bool:
    if name in HIDDEN_EXACT:
        return True
    for prefix in HIDDEN_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _stable_id_for(relative_path: str) -> str:
    """Return a stable, opaque id for a relative path.

    The hash is short but deterministic — repeated list calls on an
    unchanged directory return the same id. A move/rename produces a
    new id, which matches the intuition that the file's identity is
    its path under the master resumes root.
    """
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"{FILESYSTEM_ID_PREFIX}{digest}"


def _project_relative_source_path(absolute_path: Path) -> str:
    """Return a project-relative path string for the discovered file.

    Walks up looking for a ``candidate_context`` ancestor so the value
    reads the same on any machine. Falls back to the absolute path's
    final two components if that segment can't be located, which keeps
    the API non-empty even in unusual test layouts.
    """
    parts = absolute_path.parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "candidate_context":
            return "/".join(parts[i:])
    # Fallback: trim to the master_resumes/<file> tail.
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return absolute_path.name


def _build_record(root: Path, file_path: Path) -> Optional[FilesystemMasterResume]:
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return None
    if _is_hidden(file_path.name):
        return None
    try:
        relative = file_path.relative_to(root).as_posix()
    except ValueError:
        relative = file_path.name
    fs_id = _stable_id_for(relative)
    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return FilesystemMasterResume(
        id=fs_id,
        name=file_path.name,
        source_path=_project_relative_source_path(file_path),
        source_format=suffix.lstrip("."),
        absolute_path=file_path,
        updated_at=updated_at,
    )


def list_filesystem_master_resumes(
    root: Optional[Path] = None,
) -> list[FilesystemMasterResume]:
    """Return all supported master resume files under ``root``.

    Returns an empty list if the directory does not exist — a fresh
    checkout that hasn't created the folder yet should still serve a
    working API, just with no filesystem-backed entries.
    """
    target = Path(root) if root is not None else default_master_resumes_root()
    if not target.is_dir():
        return []
    records: list[FilesystemMasterResume] = []
    # Non-recursive — only files directly under master_resumes/. Nested
    # folders are reserved for future grouping and intentionally ignored.
    for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file():
            continue
        record = _build_record(target, entry)
        if record is not None:
            records.append(record)
    return records


def is_filesystem_id(resume_id: str) -> bool:
    return resume_id.startswith(FILESYSTEM_ID_PREFIX)


def resolve_filesystem_master_resume(
    resume_id: str, root: Optional[Path] = None
) -> Optional[FilesystemMasterResume]:
    """Return the discovered resume for ``resume_id`` or ``None``.

    A scan-on-resolve implementation keeps the lookup honest if files
    change between list and resolve — callers always see the current
    on-disk state rather than a cached snapshot.
    """
    if not is_filesystem_id(resume_id):
        return None
    for record in list_filesystem_master_resumes(root=root):
        if record.id == resume_id:
            return record
    return None


def load_filesystem_master_resume_text(
    record: FilesystemMasterResume,
) -> str:
    """Return the resume content as markdown text.

    For ``.md`` / ``.txt`` files this is the raw bytes decoded as
    UTF-8. For ``.docx`` the document is run through ``docx_extract``
    and the body blocks are joined into a single markdown string — no
    wrapper, since callers stage the result as ``master_resume.md``.
    """
    suffix = record.source_format.lower()
    if suffix in ("md", "txt"):
        return record.absolute_path.read_text(encoding="utf-8")
    if suffix == "docx":
        return _extract_docx_body_markdown(record.absolute_path)
    raise MasterResumeDiscoveryError(
        f"unsupported master resume format: {record.source_format!r}"
    )


def _extract_docx_body_markdown(docx_path: Path) -> str:
    """Render a DOCX as plain markdown using the project's docx_extract.

    Reuses ``docx_extract._extract_body_blocks`` so paragraph/table
    rendering matches what the worker would otherwise produce as
    ``master_resume_extracted.md``. Import is deferred so importing
    this module doesn't pull in python-docx for callers that only
    need discovery (the list endpoint, tests, etc.).
    """
    from docx import Document  # type: ignore[import-not-found]

    from .docx_extract import _extract_body_blocks

    document = Document(str(docx_path))
    blocks = _extract_body_blocks(document)
    return "\n\n".join(blocks).rstrip() + ("\n" if blocks else "")


def filter_unique_by_id(
    records: Iterable[FilesystemMasterResume],
) -> list[FilesystemMasterResume]:
    """De-duplicate records by id, preserving first-seen order.

    Currently the discovery path can only produce one record per
    relative path, so this is a defensive helper for tests that
    construct records directly.
    """
    seen: set[str] = set()
    out: list[FilesystemMasterResume] = []
    for r in records:
        if r.id in seen:
            continue
        seen.add(r.id)
        out.append(r)
    return out
