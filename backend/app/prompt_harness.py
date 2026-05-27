"""Prompt harness service (task 098).

Manages the runtime prompts the resume tailoring/revision workers ship
to Claude Code. Two prompt ids are exposed today:

- ``resume_tailoring`` — first-draft tailoring runs.
- ``resume_revision``  — follow-up runs that apply user feedback.

Each id resolves to a default markdown file under
``runtime_prompts/`` and an optional local override under
``candidate_context/settings/prompt_overrides/``. The override is
read-write from the UI; the default is shipped with the repo and is
not mutated by this module. The "effective" prompt is the override
when present, otherwise the default.

The module is intentionally small. It does NOT:

- expose arbitrary file reads or writes — only the registered prompt
  ids can be touched, and the override path is resolved by id so a
  caller cannot escape the settings directory.
- store overrides in the database — overrides are local-machine
  settings and stay on disk so an operator can also edit them by hand
  if they want.
- validate prompt content strictly — validation surfaces *warnings*
  about missing required contract elements; it does not reject saves
  because operators may want to iterate on prompts mid-development.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---- Registry ---------------------------------------------------------

PROMPT_ID_RESUME_TAILORING = "resume_tailoring"
PROMPT_ID_RESUME_REVISION = "resume_revision"


@dataclass(frozen=True)
class PromptHarnessDefinition:
    """Registry entry for a single prompt id.

    ``default_filename`` is the on-disk basename inside
    ``runtime_prompts/``. It doubles as the override filename inside
    ``candidate_context/settings/prompt_overrides/`` so the override
    layout mirrors the default layout — easier for an operator to
    eyeball.
    """

    id: str
    label: str
    description: str
    default_filename: str


PROMPT_REGISTRY: tuple[PromptHarnessDefinition, ...] = (
    PromptHarnessDefinition(
        id=PROMPT_ID_RESUME_TAILORING,
        label="Resume Tailoring",
        description=(
            "Prompt used to create a first-draft tailored resume from a "
            "job description, master resume, and evidence sources. Drives "
            "ATS optimization, claim auditing, and DOCX/Word output."
        ),
        default_filename="resume_tailoring.md",
    ),
    PromptHarnessDefinition(
        id=PROMPT_ID_RESUME_REVISION,
        label="Resume Revision",
        description=(
            "Prompt used on follow-up runs that apply user feedback to a "
            "prior tailored draft. Honors the same evidence and output "
            "contracts as the tailoring prompt."
        ),
        default_filename="resume_revision.md",
    ),
)


def list_prompts() -> list[PromptHarnessDefinition]:
    return list(PROMPT_REGISTRY)


def get_prompt_definition(prompt_id: str) -> PromptHarnessDefinition:
    for entry in PROMPT_REGISTRY:
        if entry.id == prompt_id:
            return entry
    raise UnknownPromptError(f"unknown prompt id: {prompt_id!r}")


class UnknownPromptError(ValueError):
    """Raised when a caller references a prompt id that is not registered."""


class PromptHarnessError(ValueError):
    """Raised for prompt-harness errors that are not unknown-id failures.

    Examples: an empty override body, a missing default prompt file,
    or a path that would escape the overrides directory.
    """


# ---- Path resolution --------------------------------------------------


def _project_root() -> Path:
    # backend/app/prompt_harness.py -> backend/app -> backend -> project root
    return Path(__file__).resolve().parents[2]


def default_runtime_prompts_root() -> Path:
    return Path(
        os.environ.get(
            "JOBAPPLY_RUNTIME_PROMPTS_ROOT",
            str(_project_root() / "runtime_prompts"),
        )
    )


def default_prompt_overrides_root() -> Path:
    return Path(
        os.environ.get(
            "JOBAPPLY_PROMPT_OVERRIDES_ROOT",
            str(_project_root() / "candidate_context" / "settings" / "prompt_overrides"),
        )
    )


def _resolve_default_path(
    definition: PromptHarnessDefinition,
    runtime_prompts_root: Path,
) -> Path:
    return Path(runtime_prompts_root) / definition.default_filename


def _resolve_override_path(
    definition: PromptHarnessDefinition,
    overrides_root: Path,
) -> Path:
    """Resolve the override path for ``definition`` under ``overrides_root``.

    The override filename comes from the registry, never from caller
    input, so the resolved path is always a direct child of
    ``overrides_root``. As a defense-in-depth check the resolved path is
    compared against the (resolved) overrides root and rejected if it
    falls outside.
    """
    overrides_root = Path(overrides_root)
    candidate = overrides_root / definition.default_filename
    # ``Path.resolve(strict=False)`` collapses ``..`` segments without
    # requiring the file to exist, which is exactly what we need to
    # catch a registry entry that tries to climb out of the overrides
    # root. Compare against the resolved root so symlinks on either
    # side don't cause a false negative.
    resolved_root = overrides_root.resolve()
    resolved_candidate = candidate.resolve()
    if not _is_within(resolved_candidate, resolved_root):
        raise PromptHarnessError(
            f"override path escapes overrides root: {candidate}"
        )
    return candidate


def _is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).relative_to(root)
        return True
    except ValueError:
        return False


# ---- Hashing ----------------------------------------------------------


def compute_prompt_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---- Read / write -----------------------------------------------------


@dataclass(frozen=True)
class PromptHarnessSummary:
    id: str
    label: str
    description: str
    default_path: str
    has_override: bool
    effective_source: str  # "default" | "override"
    updated_at: Optional[str]


@dataclass(frozen=True)
class PromptHarnessDetail:
    id: str
    label: str
    description: str
    default_path: str
    has_override: bool
    effective_source: str
    default_content: str
    override_content: Optional[str]
    effective_content: str
    effective_hash: str
    updated_at: Optional[str]


def _stat_updated_at(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return ts.isoformat()


def read_default(
    definition: PromptHarnessDefinition,
    *,
    runtime_prompts_root: Optional[Path] = None,
) -> str:
    """Return the markdown body of the default prompt file.

    Raises :class:`PromptHarnessError` if the file is missing — the
    registry promises a default for every id, so an absent file is a
    misconfigured install.
    """
    root = Path(runtime_prompts_root) if runtime_prompts_root else default_runtime_prompts_root()
    path = _resolve_default_path(definition, root)
    if not path.is_file():
        raise PromptHarnessError(
            f"default prompt file not found: {path}"
        )
    return path.read_text(encoding="utf-8")


def read_override(
    definition: PromptHarnessDefinition,
    *,
    overrides_root: Optional[Path] = None,
) -> Optional[str]:
    root = Path(overrides_root) if overrides_root else default_prompt_overrides_root()
    path = _resolve_override_path(definition, root)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def read_effective(
    definition: PromptHarnessDefinition,
    *,
    runtime_prompts_root: Optional[Path] = None,
    overrides_root: Optional[Path] = None,
) -> tuple[str, str]:
    """Return ``(content, source)`` where source is ``"override"`` or ``"default"``."""
    override = read_override(definition, overrides_root=overrides_root)
    if override is not None:
        return override, "override"
    return read_default(definition, runtime_prompts_root=runtime_prompts_root), "default"


def save_override(
    definition: PromptHarnessDefinition,
    content: str,
    *,
    overrides_root: Optional[Path] = None,
) -> Path:
    """Persist ``content`` as the local override for ``definition``.

    Empty bodies are rejected — the worker requires a real prompt, and
    an empty file would mask the default without offering anything to
    replace it.
    """
    if not content or not content.strip():
        raise PromptHarnessError("override content is empty")
    root = Path(overrides_root) if overrides_root else default_prompt_overrides_root()
    root.mkdir(parents=True, exist_ok=True)
    path = _resolve_override_path(definition, root)
    path.write_text(content, encoding="utf-8")
    return path


def delete_override(
    definition: PromptHarnessDefinition,
    *,
    overrides_root: Optional[Path] = None,
) -> bool:
    """Remove the override file. Returns True if a file was deleted."""
    root = Path(overrides_root) if overrides_root else default_prompt_overrides_root()
    path = _resolve_override_path(definition, root)
    if not path.is_file():
        return False
    path.unlink()
    return True


# ---- Summaries --------------------------------------------------------


def build_summary(
    definition: PromptHarnessDefinition,
    *,
    runtime_prompts_root: Optional[Path] = None,
    overrides_root: Optional[Path] = None,
) -> PromptHarnessSummary:
    root = Path(runtime_prompts_root) if runtime_prompts_root else default_runtime_prompts_root()
    override_root = Path(overrides_root) if overrides_root else default_prompt_overrides_root()
    override_path = _resolve_override_path(definition, override_root)
    has_override = override_path.is_file()
    return PromptHarnessSummary(
        id=definition.id,
        label=definition.label,
        description=definition.description,
        default_path=str(
            _resolve_default_path(definition, root).relative_to(_project_root())
        )
        if _is_within(_resolve_default_path(definition, root), _project_root())
        else str(_resolve_default_path(definition, root)),
        has_override=has_override,
        effective_source="override" if has_override else "default",
        updated_at=_stat_updated_at(override_path) if has_override else None,
    )


def build_detail(
    definition: PromptHarnessDefinition,
    *,
    runtime_prompts_root: Optional[Path] = None,
    overrides_root: Optional[Path] = None,
) -> PromptHarnessDetail:
    default_content = read_default(
        definition, runtime_prompts_root=runtime_prompts_root
    )
    override_content = read_override(definition, overrides_root=overrides_root)
    has_override = override_content is not None
    effective_content = override_content if has_override else default_content
    effective_source = "override" if has_override else "default"
    summary = build_summary(
        definition,
        runtime_prompts_root=runtime_prompts_root,
        overrides_root=overrides_root,
    )
    return PromptHarnessDetail(
        id=definition.id,
        label=definition.label,
        description=definition.description,
        default_path=summary.default_path,
        has_override=has_override,
        effective_source=effective_source,
        default_content=default_content,
        override_content=override_content,
        effective_content=effective_content,
        effective_hash=compute_prompt_hash(effective_content),
        updated_at=summary.updated_at,
    )


# ---- Validation -------------------------------------------------------


@dataclass(frozen=True)
class PromptValidationResult:
    valid: bool
    warnings: list[str]


# Each required-element list documents the contract elements the
# downstream worker expects to find anywhere in the prompt body. The
# matches are case-insensitive substring checks — we do not try to
# parse the markdown — and missing entries surface as warnings rather
# than hard failures so operators can iterate on wording without
# fighting the validator.
_TAILORING_REQUIRED_ELEMENTS: tuple[str, ...] = (
    "non-interactive backend job",
    "do not ask clarifying questions",
    "tailored_resume.md",
    "tailored_resume.docx",
    "change_log.md",
    "claim_audit.md",
    "ats_audit.md",
    "recruiter_review.md",
    "ATS",
    "evidence",
)

_REVISION_REQUIRED_ELEMENTS: tuple[str, ...] = (
    "current tailored",
    "revision",
    "master_resume",
    "evidence",
    "do not invent",
    "tailored_resume.md",
    "tailored_resume.docx",
    "change_log.md",
    "claim_audit.md",
    "ats_audit.md",
    "recruiter_review.md",
)


def _required_elements(prompt_id: str) -> tuple[str, ...]:
    if prompt_id == PROMPT_ID_RESUME_TAILORING:
        return _TAILORING_REQUIRED_ELEMENTS
    if prompt_id == PROMPT_ID_RESUME_REVISION:
        return _REVISION_REQUIRED_ELEMENTS
    return ()


def validate_prompt_content(
    prompt_id: str,
    content: str,
) -> PromptValidationResult:
    elements = _required_elements(prompt_id)
    warnings: list[str] = []
    lowered = content.lower()
    for element in elements:
        if element.lower() not in lowered:
            warnings.append(
                f"Prompt does not mention required element: {element!r}"
            )
    return PromptValidationResult(valid=not warnings, warnings=warnings)
