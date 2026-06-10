"""Human-readable resume exports (task 122).

Tailoring runs keep stable, machine-validated artifact names on disk
(``runs/<run_id>/output/tailored_resume.docx`` and friends — see
``docs/contracts/claude_run_directory.md``). Those names are great for
workers and tests and terrible for a human staring at their Downloads
folder. This module bridges the two worlds:

* :func:`build_resume_export_filename` turns ``(candidate, company, job,
  date, run_id, ext)`` into a safe, descriptive download name such as
  ``Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx``.
* :func:`resolve_output_artifact` resolves a *known* artifact name to a
  path inside a run's ``output/`` directory, refusing anything outside
  the allow-list or that escapes the directory (path-traversal guard).
* :func:`export_run` copies a run's final artifacts into a managed
  ``candidate_context/exports/<dir>/`` folder, renaming the DOCX to the
  human-readable name and never overwriting an existing export.

Nothing here mutates the internal run artifacts — exports are copies.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .run_directory import default_candidate_context_root


# Artifacts a user is allowed to download / export. Every entry lives at
# ``output/<name>`` inside a run directory; the allow-list is what keeps a
# user-supplied ``artifact_name`` from being used to read arbitrary files.
DOWNLOADABLE_ARTIFACTS: tuple[str, ...] = (
    "tailored_resume.docx",
    "tailored_resume.md",
    "claim_audit.md",
    "ats_audit.md",
    "recruiter_review.md",
    "template_fidelity_audit.md",
    "change_log.md",
)

# The DOCX is the headline artifact and the only one renamed to the
# human-readable filename on export; the rest keep their stable names so a
# folder of exports stays self-describing.
RESUME_DOCX_ARTIFACT = "tailored_resume.docx"

OUTPUT_DIRNAME = "output"

_DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_MEDIA_TYPES = {
    ".docx": _DOCX_MEDIA_TYPE,
    ".md": "text/markdown; charset=utf-8",
}

# Cap each filename component so a pathological company/title cannot push
# the final name past common filesystem limits (255 bytes per component).
_MAX_COMPONENT_LEN = 64
# Characters allowed verbatim in a component. Spaces and everything else
# collapse to ``_``; ``-`` survives so ISO dates stay readable.
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9-]+")


class ResumeExportError(ValueError):
    """Raised for an unknown artifact, a traversal attempt, or a failed export."""


def _sanitize_component(value: str, *, max_len: int = _MAX_COMPONENT_LEN) -> str:
    """Return a filesystem-safe, collapsed version of ``value``.

    Unsafe characters (including path separators and shell metacharacters)
    and whitespace runs collapse to single underscores; leading/trailing
    separators are trimmed and the result is capped at ``max_len``.
    Returns ``""`` when nothing printable survives.
    """
    if not value:
        return ""
    cleaned = _UNSAFE_RE.sub("_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].strip("_-")
    return cleaned


def _date_str(created_at: Union[datetime, str, None]) -> str:
    """Render ``created_at`` as ``YYYY-MM-DD``.

    Accepts a ``datetime``, an ISO-8601 string (the shape persisted in
    metadata.json and on the ``ClaudeRun`` row), or ``None``. An
    unparseable value yields ``""`` so the caller still produces a name.
    """
    if created_at is None:
        return ""
    if isinstance(created_at, datetime):
        return created_at.date().isoformat()
    text = str(created_at).strip()
    if not text:
        return ""
    try:
        # ``fromisoformat`` handles the ``...+00:00`` offsets we persist;
        # normalize a trailing ``Z`` it does not accept on older Pythons.
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        return datetime.fromisoformat(normalized).date().isoformat()
    except ValueError:
        # Fall back to the leading ``YYYY-MM-DD`` if the value at least
        # starts with a date; otherwise give up gracefully.
        return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else ""


def _normalize_ext(ext: str) -> str:
    """Return a safe, dot-prefixed, lowercase extension (``"docx"`` → ``".docx"``)."""
    cleaned = _UNSAFE_RE.sub("", (ext or "").strip().lstrip(".")).lower()
    return f".{cleaned}" if cleaned else ""


def _short_run_id(run_id: Optional[str]) -> str:
    """First 8 hex-ish chars of ``run_id`` with dashes stripped, for uniqueness."""
    if not run_id:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", run_id)[:8]


def build_resume_export_filename(
    candidate_name: Optional[str],
    company: Optional[str],
    job_title: Optional[str],
    created_at: Union[datetime, str, None],
    run_id: Optional[str],
    ext: str,
) -> str:
    """Build a safe, descriptive download filename for a tailored resume.

    Produces e.g.
    ``Calvin_Pieters__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__2026-05-27.docx``.
    When the candidate name is unavailable the lead component falls back to
    ``Resume`` (``Resume__Company__Job_Title__Date.docx``). Components that
    sanitize to empty are dropped. A short ``run_id`` suffix is appended
    only when company *and* job title are both missing, so otherwise-bare
    ``Resume__<date>`` names still stay unique across runs.

    The result is deterministic for a given run and contains no path
    separators or shell-special characters.
    """
    parts: list[str] = []

    candidate = _sanitize_component(candidate_name or "")
    parts.append(candidate or "Resume")

    company_part = _sanitize_component(company or "")
    if company_part:
        parts.append(company_part)
    job_part = _sanitize_component(job_title or "")
    if job_part:
        parts.append(job_part)

    date_part = _date_str(created_at)
    if date_part:
        parts.append(date_part)

    # Guarantee uniqueness for the otherwise-degenerate "Resume__<date>"
    # case where we have neither company nor title to distinguish runs.
    if not company_part and not job_part:
        short = _short_run_id(run_id)
        if short:
            parts.append(short)

    stem = "__".join(p for p in parts if p)
    return f"{stem}{_normalize_ext(ext)}"


def build_export_dir_name(
    company: Optional[str],
    job_title: Optional[str],
    created_at: Union[datetime, str, None],
    run_id: Optional[str],
) -> str:
    """Build the per-run export subfolder name.

    Leads with the date so a chronological listing sorts naturally, e.g.
    ``2026-05-27__Example_Aero_Labs__Scientific_Machine_Learning_Engineer__d6df714b``.
    The short run id keeps two runs for the same company/title from
    colliding on the same day.
    """
    parts: list[str] = []
    date_part = _date_str(created_at)
    if date_part:
        parts.append(date_part)
    company_part = _sanitize_component(company or "")
    if company_part:
        parts.append(company_part)
    job_part = _sanitize_component(job_title or "")
    if job_part:
        parts.append(job_part)
    short = _short_run_id(run_id)
    if short:
        parts.append(short)
    name = "__".join(p for p in parts if p)
    return name or "export"


def download_filename_for(
    artifact_name: str,
    candidate_name: Optional[str],
    company: Optional[str],
    job_title: Optional[str],
    created_at: Union[datetime, str, None],
    run_id: Optional[str],
) -> str:
    """Human-readable download name for any allowed artifact.

    The DOCX gets the full resume filename; every other artifact keeps its
    stable basename but is prefixed with the same descriptive stem so a pile
    of downloads stays attributable, e.g.
    ``Calvin_Pieters__Acme__SDE__2026-05-27__claim_audit.md``.
    """
    ext = Path(artifact_name).suffix
    if artifact_name == RESUME_DOCX_ARTIFACT:
        return build_resume_export_filename(
            candidate_name, company, job_title, created_at, run_id, ext
        )
    stem = build_resume_export_filename(
        candidate_name, company, job_title, created_at, run_id, ""
    )
    return f"{stem}__{artifact_name}"


def media_type_for(artifact_name: str) -> str:
    """MIME type for an artifact, defaulting to ``application/octet-stream``."""
    return _MEDIA_TYPES.get(Path(artifact_name).suffix.lower(), "application/octet-stream")


def _resolve_inside(base: Path, relative: str) -> Path:
    """Resolve ``relative`` under ``base`` and assert it stays inside.

    Mirrors ``run_import._resolve_inside`` — guards against symlinks or
    ``..`` components that would escape ``base``.
    """
    base_resolved = base.resolve()
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ResumeExportError(
            f"path resolves outside the allowed directory: {relative}"
        ) from exc
    return candidate


def resolve_output_artifact(run_dir: Path, artifact_name: str) -> Path:
    """Resolve a known artifact to its path under ``run_dir/output``.

    Rejects any name not in :data:`DOWNLOADABLE_ARTIFACTS` and any name that
    would escape the output directory. The returned path is not guaranteed
    to exist — the caller decides whether absence is a 404.
    """
    if artifact_name not in DOWNLOADABLE_ARTIFACTS:
        raise ResumeExportError(f"unknown artifact: {artifact_name!r}")
    return _resolve_inside(Path(run_dir) / OUTPUT_DIRNAME, artifact_name)


# --- managed export folder -------------------------------------------------


def _project_root() -> Path:
    # backend/app/resume_export.py -> backend/app -> backend -> project root
    return Path(__file__).resolve().parents[2]


def default_exports_root() -> Path:
    """Managed exports root, ``candidate_context/exports/`` by default.

    Overridable via ``JOBAPPLY_EXPORTS_ROOT`` (used by tests to keep
    exports out of the repo).
    """
    override = os.environ.get("JOBAPPLY_EXPORTS_ROOT")
    if override:
        return Path(override)
    return default_candidate_context_root() / "exports"


def project_relative_path(path: Path) -> str:
    """Return ``path`` relative to the project root when possible, else absolute."""
    try:
        return str(Path(path).resolve().relative_to(_project_root()))
    except ValueError:
        return str(path)


def discover_candidate_name(candidate_context_root: Path) -> Optional[str]:
    """Best-effort candidate name from ``candidate_profile.md``.

    Looks for a ``name:`` value in YAML-style frontmatter, a ``Name: ...``
    line (optionally markdown-bold), or a first-level heading that is not
    the placeholder ``Candidate Profile``. Returns ``None`` when no real
    name is present so callers fall back to the ``Resume__...`` form.
    """
    profile = Path(candidate_context_root) / "candidate_profile.md"
    try:
        text = profile.read_text(encoding="utf-8")
    except OSError:
        return None

    name_line = re.compile(r"^\**\s*name\s*\**\s*:\s*(.+?)\s*$", re.IGNORECASE)
    heading = re.compile(r"^#\s+(.+?)\s*$")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = name_line.match(line)
        if m:
            candidate = m.group(1).strip().strip("*").strip()
            if candidate:
                return candidate
        h = heading.match(line)
        if h:
            candidate = h.group(1).strip()
            if candidate.lower() not in {"candidate profile", "profile"}:
                return candidate
    return None


@dataclass(frozen=True)
class ExportedFile:
    name: str
    source: str


@dataclass(frozen=True)
class ExportResult:
    export_dir: Path
    files: list[ExportedFile]


def _unique_export_dir(exports_root: Path, dir_name: str) -> Path:
    """Pick a non-colliding export directory, suffixing ``-2``, ``-3`` … .

    Never overwrites an existing export. The returned path is guaranteed to
    resolve inside ``exports_root``.
    """
    base = _resolve_inside(exports_root, dir_name)
    if not base.exists():
        return base
    for n in range(2, 1000):
        candidate = _resolve_inside(exports_root, f"{dir_name}-{n}")
        if not candidate.exists():
            return candidate
    raise ResumeExportError(f"too many existing exports for {dir_name!r}")


def export_run(
    run_dir: Path,
    exports_root: Path,
    *,
    candidate_name: Optional[str],
    company: Optional[str],
    job_title: Optional[str],
    created_at: Union[datetime, str, None],
    run_id: Optional[str],
) -> ExportResult:
    """Copy a run's final artifacts into a managed export subfolder.

    Creates ``exports_root/<date>__<company>__<job>__<run>/`` (never
    overwriting an existing folder), copies the DOCX under its human-readable
    name and the markdown/audit artifacts under their stable names, and
    returns the export directory plus the list of copied files. Raises
    :class:`ResumeExportError` when no exportable artifact exists.

    Only files inside ``run_dir/output`` are read and only files inside
    ``exports_root`` are written — both sides are traversal-guarded.
    """
    run_dir = Path(run_dir)
    exports_root = Path(exports_root)

    # Gather the artifacts that actually exist on disk before creating any
    # folder, so a run with nothing to export does not leave an empty dir.
    available: list[tuple[str, Path, str]] = []  # (dest_name, source_path, source_rel)
    for artifact in DOWNLOADABLE_ARTIFACTS:
        try:
            source = resolve_output_artifact(run_dir, artifact)
        except ResumeExportError:
            continue
        if not source.is_file():
            continue
        if artifact == RESUME_DOCX_ARTIFACT:
            dest_name = build_resume_export_filename(
                candidate_name, company, job_title, created_at, run_id, ".docx"
            )
        else:
            dest_name = artifact
        available.append((dest_name, source, project_relative_path(source)))

    if not available:
        raise ResumeExportError(
            f"no exportable artifacts found under {run_dir / OUTPUT_DIRNAME}"
        )

    exports_root.mkdir(parents=True, exist_ok=True)
    dir_name = build_export_dir_name(company, job_title, created_at, run_id)
    export_dir = _unique_export_dir(exports_root, dir_name)
    export_dir.mkdir(parents=True)

    copied: list[ExportedFile] = []
    for dest_name, source, source_rel in available:
        dest = _resolve_inside(export_dir, dest_name)
        shutil.copy2(source, dest)
        copied.append(ExportedFile(name=dest_name, source=source_rel))

    return ExportResult(export_dir=export_dir, files=copied)
