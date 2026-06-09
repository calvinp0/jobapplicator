"""Unit tests for the resume suggestions module + prompt contract (task 113).

Covers schema validation (accept valid / reject missing-required), the
accepted-suggestion apply logic that rebuilds a renderable working resume,
evidence + ATS-keyword preservation, and the tailoring/revision prompt
requirements for ``output/resume_suggestions.json``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.resume_suggestions import (
    SuggestionError,
    apply_accepted,
    find_suggestion,
    validate_suggestions_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid_suggestion(**overrides):
    base = {
        "id": "sug_001",
        "section_id": "professional_summary",
        "section_heading": "PROFESSIONAL SUMMARY",
        "operation": "replace_section_text",
        "current_text": "Old summary.",
        "suggested_text": "New summary emphasizing distributed systems.",
        "reason": "Aligns the summary with the target role.",
        "evidence_refs": [
            {"source": "vtrace evidence", "quote": "Built a code intelligence engine."}
        ],
        "ats_keywords": ["distributed systems", "developer tooling"],
        "confidence": 0.86,
        "risk": "low",
        "status": "pending",
    }
    base.update(overrides)
    return base


def _doc(*suggestions):
    return {
        "target_company": "Amazon",
        "target_job_title": "SDE",
        "suggestions": list(suggestions),
    }


# ---- Schema validation -----------------------------------------------------


def test_validate_accepts_valid_suggestions():
    doc = validate_suggestions_payload(_doc(_valid_suggestion()))
    assert doc["target_company"] == "Amazon"
    assert len(doc["suggestions"]) == 1
    sug = doc["suggestions"][0]
    assert sug["operation"] == "replace_section_text"
    assert sug["status"] == "pending"
    assert sug["confidence"] == 0.86
    assert sug["risk"] == "low"


def test_validate_defaults_status_and_risk_when_omitted():
    sug = _valid_suggestion()
    sug.pop("status")
    sug.pop("risk")
    sug.pop("confidence")
    doc = validate_suggestions_payload(_doc(sug))
    assert doc["suggestions"][0]["status"] == "pending"
    assert doc["suggestions"][0]["risk"] == "medium"
    assert doc["suggestions"][0]["confidence"] is None


@pytest.mark.parametrize("missing", ["id", "section_id", "operation", "reason"])
def test_validate_rejects_missing_required_field(missing):
    sug = _valid_suggestion()
    sug.pop(missing)
    with pytest.raises(SuggestionError) as exc:
        validate_suggestions_payload(_doc(sug))
    assert missing in str(exc.value)


def test_validate_rejects_unknown_operation():
    with pytest.raises(SuggestionError, match="operation"):
        validate_suggestions_payload(_doc(_valid_suggestion(operation="nuke_resume")))


def test_validate_rejects_out_of_range_confidence():
    with pytest.raises(SuggestionError, match="between 0 and 1"):
        validate_suggestions_payload(_doc(_valid_suggestion(confidence=1.5)))


def test_validate_rejects_duplicate_ids():
    with pytest.raises(SuggestionError, match="duplicate"):
        validate_suggestions_payload(
            _doc(_valid_suggestion(), _valid_suggestion())
        )


def test_validate_rejects_non_object_root():
    with pytest.raises(SuggestionError):
        validate_suggestions_payload([])


def test_evidence_refs_and_ats_keywords_preserved():
    doc = validate_suggestions_payload(_doc(_valid_suggestion()))
    sug = doc["suggestions"][0]
    assert sug["evidence_refs"] == [
        {"source": "vtrace evidence", "quote": "Built a code intelligence engine."}
    ]
    assert sug["ats_keywords"] == ["distributed systems", "developer tooling"]


# ---- find_suggestion -------------------------------------------------------


def test_find_suggestion_by_id():
    doc = _doc(_valid_suggestion(id="a"), _valid_suggestion(id="b"))
    assert find_suggestion(doc, "b")["id"] == "b"
    assert find_suggestion(doc, "missing") is None


# ---- apply_accepted --------------------------------------------------------


def _base_resume():
    return {
        "header": {"name": "Test Candidate", "contact_items": []},
        "sections": [
            {
                "type": "summary",
                "heading": "PROFESSIONAL SUMMARY",
                "paragraphs": ["Old summary."],
            },
            {
                "type": "skills",
                "heading": "SKILLS",
                "groups": [{"label": "Languages", "items": ["Python"]}],
            },
            {
                "type": "experience",
                "heading": "EXPERIENCE",
                "entries": [
                    {
                        "title": "Engineer",
                        "organization": "Acme",
                        "bullets": ["Did a thing."],
                    }
                ],
            },
        ],
        "metadata": {},
    }


def test_apply_replace_section_text_only_when_accepted():
    base = _base_resume()
    sug = _valid_suggestion(status="accepted")
    working = apply_accepted(base, [sug])
    assert working["sections"][0]["paragraphs"] == [
        "New summary emphasizing distributed systems."
    ]
    # Base is not mutated.
    assert base["sections"][0]["paragraphs"] == ["Old summary."]


def test_apply_skips_pending_and_rejected():
    base = _base_resume()
    working = apply_accepted(
        base,
        [
            _valid_suggestion(id="a", status="pending"),
            _valid_suggestion(id="b", status="rejected"),
        ],
    )
    assert working["sections"][0]["paragraphs"] == ["Old summary."]


def test_apply_rewrite_bullet():
    base = _base_resume()
    sug = _valid_suggestion(
        id="b1",
        section_id="experience",
        operation="rewrite_bullet",
        current_text="Did a thing.",
        suggested_text="Shipped a measurable thing.",
        status="accepted",
    )
    working = apply_accepted(base, [sug])
    bullets = working["sections"][2]["entries"][0]["bullets"]
    assert bullets == ["Shipped a measurable thing."]


def test_apply_insert_bullet():
    base = _base_resume()
    sug = _valid_suggestion(
        id="b2",
        section_id="experience",
        operation="insert_bullet",
        current_text="",
        suggested_text="Added a brand new bullet.",
        status="accepted",
    )
    working = apply_accepted(base, [sug])
    bullets = working["sections"][2]["entries"][0]["bullets"]
    assert "Added a brand new bullet." in bullets
    assert len(bullets) == 2


def test_apply_add_skill():
    base = _base_resume()
    sug = _valid_suggestion(
        id="s1",
        section_id="skills",
        operation="add_skill",
        current_text="",
        suggested_text="Rust",
        status="accepted",
    )
    working = apply_accepted(base, [sug])
    items = working["sections"][1]["groups"][0]["items"]
    assert "Rust" in items


def test_apply_unmatched_section_is_skipped():
    base = _base_resume()
    sug = _valid_suggestion(
        id="x", section_id="nonexistent_section", status="accepted"
    )
    working = apply_accepted(base, [sug])
    # Unchanged summary, no crash.
    assert working["sections"][0]["paragraphs"] == ["Old summary."]


# ---- Prompt contract -------------------------------------------------------


def test_tailoring_prompt_requests_resume_suggestions():
    body = (REPO_ROOT / "runtime_prompts" / "resume_tailoring.md").read_text(
        encoding="utf-8"
    )
    assert "output/resume_suggestions.json" in body
    assert "Structured Resume Suggestions" in body
    # The reviewable-suggestion fields are spelled out.
    for token in ("operation", "evidence references", "confidence", "risk"):
        assert token in body


def test_tailoring_prompt_discourages_unsupported_claims():
    body = (REPO_ROOT / "runtime_prompts" / "resume_tailoring.md").read_text(
        encoding="utf-8"
    )
    assert "Do not suggest unsupported claims." in body
    assert "weak or user-provided evidence" in body
    assert "Avoid rewriting the whole resume as one giant suggestion." in body


def test_revision_prompt_requests_resume_suggestions():
    body = (REPO_ROOT / "runtime_prompts" / "resume_revision.md").read_text(
        encoding="utf-8"
    )
    assert "output/resume_suggestions.json" in body
