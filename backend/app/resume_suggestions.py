"""Structured resume suggestions (task 113).

The tailoring run now produces ``output/resume_suggestions.json`` alongside
``output/tailored_resume.json``. Where the tailored JSON is the *finalized*
structured resume (source of truth for the deterministic DOCX renderer),
the suggestions file is a list of section-level, reviewable edits that the
user can accept / reject / revise before the resume state is rebuilt.

This module owns three concerns:

* validation of the suggestions document shape (mirrors the permissive-on-
  optionals / strict-on-structure style of ``resume_docx_renderer``),
* the per-suggestion review status vocabulary,
* applying the *accepted* suggestions onto a base tailored-resume JSON to
  build a new "working resume" state. The output of :func:`apply_accepted`
  is the same schema the renderer consumes, so an applied state stays
  renderable.

Schema (see ``docs/contracts/claude_run_directory.md`` for the full spec):

```json
{
  "target_company": "Amazon",
  "target_job_title": "Software Development Engineer",
  "suggestions": [
    {
      "id": "sug_001",
      "section_id": "professional_summary",
      "section_heading": "PROFESSIONAL SUMMARY",
      "operation": "replace_section_text",
      "current_text": "...",
      "suggested_text": "...",
      "reason": "Why this improves the resume.",
      "evidence_refs": [{"source": "vtrace evidence", "quote": "..."}],
      "ats_keywords": ["agentic AI", "distributed systems"],
      "confidence": 0.86,
      "risk": "low",
      "status": "pending"
    }
  ]
}
```

Only ``id``, ``section_id``, ``operation`` and ``reason`` are strictly
required per suggestion; every other field is optional and defaults to a
sensible empty value so a sparse-but-honest suggestion still validates.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional


RESUME_SUGGESTIONS_FILENAME = "resume_suggestions.json"

# Operations the tailoring prompt may emit. The first four are the ones the
# apply step rebuilds the working resume from; the rest are accepted and
# round-tripped through review but are not yet wired into apply (kept in the
# vocabulary so the prompt + UI can use them and a later task fills in apply).
SUPPORTED_OPERATIONS = (
    "replace_section_text",
    "rewrite_bullet",
    "insert_bullet",
    "delete_bullet",
    "reorder_bullets",
    "add_skill",
    "remove_skill",
    "rewrite_entry",
)
# Operations that :func:`apply_accepted` actually rebuilds the resume from.
APPLIED_OPERATIONS = (
    "replace_section_text",
    "rewrite_bullet",
    "insert_bullet",
    "add_skill",
)

# Per-suggestion review lifecycle. ``pending`` is the import-time default;
# the accept/reject/revise endpoints move a suggestion to a terminal-ish
# state. ``revised`` means the user asked for a revision instruction to be
# applied on a future revision run — it is not auto-applied here.
SUGGESTION_STATUSES = ("pending", "accepted", "rejected", "revised")

RISK_LEVELS = ("low", "medium", "high")


class SuggestionError(ValueError):
    """Raised when the suggestions JSON is missing or structurally invalid."""


def _require_dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SuggestionError(
            f"{where} must be an object, got {type(value).__name__}"
        )
    return value


def _require_list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise SuggestionError(
            f"{where} must be an array, got {type(value).__name__}"
        )
    return value


def _require_nonempty_str(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuggestionError(f"{where} must be a non-empty string")
    return value


def _optional_str(value: Any, where: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SuggestionError(f"{where} must be a string, got {type(value).__name__}")
    return value


def _string_list(value: Any, where: str) -> list[str]:
    if value is None:
        return []
    items = _require_list(value, where)
    result: list[str] = []
    for idx, item in enumerate(items):
        if not isinstance(item, str):
            raise SuggestionError(
                f"{where}[{idx}] must be a string, got {type(item).__name__}"
            )
        result.append(item)
    return result


def _evidence_refs(value: Any, where: str) -> list[dict[str, str]]:
    if value is None:
        return []
    items = _require_list(value, where)
    result: list[dict[str, str]] = []
    for idx, ref in enumerate(items):
        rwhere = f"{where}[{idx}]"
        rdict = _require_dict(ref, rwhere)
        result.append(
            {
                "source": _optional_str(rdict.get("source"), f"{rwhere}.source"),
                "quote": _optional_str(rdict.get("quote"), f"{rwhere}.quote"),
            }
        )
    return result


def _confidence(value: Any, where: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SuggestionError(f"{where} must be a number between 0 and 1")
    num = float(value)
    if not 0.0 <= num <= 1.0:
        raise SuggestionError(f"{where} must be between 0 and 1, got {num}")
    return num


def _risk(value: Any, where: str) -> str:
    if value is None:
        return "medium"
    risk = _require_nonempty_str(value, where).strip().lower()
    if risk not in RISK_LEVELS:
        raise SuggestionError(
            f"{where} {risk!r} is not one of {list(RISK_LEVELS)}"
        )
    return risk


def _status(value: Any, where: str) -> str:
    if value is None:
        return "pending"
    status = _require_nonempty_str(value, where).strip().lower()
    if status not in SUGGESTION_STATUSES:
        raise SuggestionError(
            f"{where} {status!r} is not one of {list(SUGGESTION_STATUSES)}"
        )
    return status


def validate_suggestion(raw: Any, where: str) -> dict[str, Any]:
    """Validate one suggestion and return it normalized to canonical keys."""
    sug = _require_dict(raw, where)
    operation = _require_nonempty_str(sug.get("operation"), f"{where}.operation")
    if operation not in SUPPORTED_OPERATIONS:
        raise SuggestionError(
            f"{where}.operation {operation!r} is not one of {list(SUPPORTED_OPERATIONS)}"
        )
    return {
        "id": _require_nonempty_str(sug.get("id"), f"{where}.id"),
        "section_id": _require_nonempty_str(
            sug.get("section_id"), f"{where}.section_id"
        ),
        "section_heading": _optional_str(
            sug.get("section_heading"), f"{where}.section_heading"
        ),
        "operation": operation,
        "current_text": _optional_str(sug.get("current_text"), f"{where}.current_text"),
        "suggested_text": _optional_str(
            sug.get("suggested_text"), f"{where}.suggested_text"
        ),
        "reason": _require_nonempty_str(sug.get("reason"), f"{where}.reason"),
        "evidence_refs": _evidence_refs(
            sug.get("evidence_refs"), f"{where}.evidence_refs"
        ),
        "ats_keywords": _string_list(sug.get("ats_keywords"), f"{where}.ats_keywords"),
        "confidence": _confidence(sug.get("confidence"), f"{where}.confidence"),
        "risk": _risk(sug.get("risk"), f"{where}.risk"),
        "status": _status(sug.get("status"), f"{where}.status"),
        # Free-text instruction captured by the "Ask to revise" action. Not
        # produced by the prompt; populated by the revise endpoint.
        "revision_instruction": _optional_str(
            sug.get("revision_instruction"), f"{where}.revision_instruction"
        ),
    }


def validate_suggestions_payload(data: Any) -> dict[str, Any]:
    """Validate the whole suggestions document and return it normalized.

    Raises :class:`SuggestionError` with a clear, location-tagged message
    when a required field is missing or a field has the wrong type, so the
    worker can fail the run and the operator can see which suggestion was
    malformed.
    """
    obj = _require_dict(data, f"{RESUME_SUGGESTIONS_FILENAME} root")
    raw_suggestions = _require_list(obj.get("suggestions"), "suggestions")
    suggestions = [
        validate_suggestion(item, f"suggestions[{idx}]")
        for idx, item in enumerate(raw_suggestions)
    ]
    seen: set[str] = set()
    for sug in suggestions:
        if sug["id"] in seen:
            raise SuggestionError(f"duplicate suggestion id: {sug['id']!r}")
        seen.add(sug["id"])
    return {
        "target_company": _optional_str(
            obj.get("target_company"), "target_company"
        ),
        "target_job_title": _optional_str(
            obj.get("target_job_title"), "target_job_title"
        ),
        "suggestions": suggestions,
    }


def find_suggestion(
    doc: dict[str, Any], suggestion_id: str
) -> Optional[dict[str, Any]]:
    """Return the suggestion with ``id == suggestion_id`` from ``doc``, or None."""
    for sug in doc.get("suggestions") or []:
        if isinstance(sug, dict) and sug.get("id") == suggestion_id:
            return sug
    return None


def load_suggestions_json(path: Path) -> dict[str, Any]:
    """Read and JSON-parse ``path``; raise :class:`SuggestionError` on failure."""
    if not path.is_file():
        raise SuggestionError(
            f"expected output file missing: output/{path.name}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise SuggestionError(f"failed to read {path.name}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SuggestionError(
            f"invalid resume suggestions JSON: {exc.msg} (line {exc.lineno})"
        ) from exc


# ---------------------------------------------------------------------------
# Applying accepted suggestions onto a base resume
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.strip().lower())


def _section_matches(section: dict[str, Any], section_id: str) -> bool:
    """Decide whether ``section`` is the target of a suggestion's ``section_id``.

    Suggestions reference sections by a stable-ish id like
    ``professional_summary`` while the renderer schema keys sections by
    ``type`` (``summary``) and ``heading`` (``PROFESSIONAL SUMMARY``). We
    accept a match on the type, the slugified heading, or either being a
    substring of the other so the prompt and the renderer schema do not have
    to agree on an exact id vocabulary.
    """
    target = _slug(section_id)
    candidates = {
        _slug(str(section.get("type") or "")),
        _slug(str(section.get("heading") or "")),
    }
    candidates.discard("")
    if target in candidates:
        return True
    return any(target in cand or cand in target for cand in candidates)


def _find_section(
    sections: list[dict[str, Any]], section_id: str
) -> Optional[dict[str, Any]]:
    for section in sections:
        if isinstance(section, dict) and _section_matches(section, section_id):
            return section
    return None


def _apply_replace_section_text(section: dict[str, Any], suggested: str) -> bool:
    """Replace the primary text of a section with ``suggested``."""
    if not suggested.strip():
        return False
    kind = section.get("type")
    if kind == "summary" or "paragraphs" in section:
        section["paragraphs"] = [suggested]
        return True
    if kind in {"publications", "projects", "certifications", "awards", "other"} or (
        "items" in section
    ):
        section["items"] = [suggested]
        return True
    # Fall back to a paragraphs body so the renderer still shows the text.
    section["paragraphs"] = [suggested]
    return True


def _iter_bullets(section: dict[str, Any]):
    """Yield ``(entry, index)`` for every bullet in an experience-like section."""
    for entry in section.get("entries", []) or []:
        if not isinstance(entry, dict):
            continue
        bullets = entry.get("bullets")
        if isinstance(bullets, list):
            for idx in range(len(bullets)):
                yield entry, idx


def _apply_rewrite_bullet(
    section: dict[str, Any], current: str, suggested: str
) -> bool:
    if not suggested.strip():
        return False
    current_norm = current.strip()
    # Prefer an exact (whitespace-normalized) match on the current bullet.
    for entry, idx in _iter_bullets(section):
        if entry["bullets"][idx].strip() == current_norm and current_norm:
            entry["bullets"][idx] = suggested
            return True
    # Fall back to the first bullet of the first entry when the current text
    # could not be located (the prompt may paraphrase the original).
    for entry in section.get("entries", []) or []:
        if isinstance(entry, dict) and isinstance(entry.get("bullets"), list) and entry["bullets"]:
            entry["bullets"][0] = suggested
            return True
    return False


def _apply_insert_bullet(section: dict[str, Any], suggested: str) -> bool:
    if not suggested.strip():
        return False
    entries = section.get("entries")
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        target = entries[0]
        bullets = target.setdefault("bullets", [])
        if isinstance(bullets, list):
            bullets.append(suggested)
            return True
    return False


def _apply_add_skill(section: dict[str, Any], suggested: str) -> bool:
    if not suggested.strip():
        return False
    skill = suggested.strip()
    groups = section.get("groups")
    if not isinstance(groups, list):
        groups = []
        section["groups"] = groups
    if groups and isinstance(groups[0], dict):
        items = groups[0].setdefault("items", [])
        if isinstance(items, list):
            if skill not in items:
                items.append(skill)
            return True
    groups.append({"label": "Additional", "items": [skill]})
    return True


def apply_accepted(
    base_resume: dict[str, Any], suggestions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return a deep copy of ``base_resume`` with accepted suggestions applied.

    Only suggestions whose ``status`` is ``accepted`` and whose ``operation``
    is one of :data:`APPLIED_OPERATIONS` change the document. The returned
    object keeps the renderer schema (``header`` + ``sections``) so it can be
    fed straight back into ``resume_docx_renderer``. Unmatched suggestions are
    skipped silently — the caller already has the per-suggestion status to
    explain why a change may not be visible.
    """
    working = copy.deepcopy(base_resume) if isinstance(base_resume, dict) else {}
    sections = working.get("sections")
    if not isinstance(sections, list):
        return working

    for sug in suggestions:
        if sug.get("status") != "accepted":
            continue
        operation = sug.get("operation")
        if operation not in APPLIED_OPERATIONS:
            continue
        section = _find_section(sections, sug.get("section_id", ""))
        if section is None:
            continue
        suggested = sug.get("suggested_text", "") or ""
        current = sug.get("current_text", "") or ""
        if operation == "replace_section_text":
            _apply_replace_section_text(section, suggested)
        elif operation == "rewrite_bullet":
            _apply_rewrite_bullet(section, current, suggested)
        elif operation == "insert_bullet":
            _apply_insert_bullet(section, suggested)
        elif operation == "add_skill":
            _apply_add_skill(section, suggested)
    return working
