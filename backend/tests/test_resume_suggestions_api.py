"""HTTP-layer tests for the interactive resume suggestion review endpoints
(task 113).

Seeds a completed run whose outputs include a multi-suggestion
``resume_suggestions.json``, imports it into a ResumeVersion, then exercises
the list / accept / reject / revise / apply-suggestions endpoints under
``/resume-versions/{id}``.
"""

from __future__ import annotations

import json
from pathlib import Path


CANDIDATE_FILES = (
    "candidate_profile.md",
    "project_notes.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)

BASE_RESUME_JSON = json.dumps(
    {
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
        ],
        "metadata": {"target_company": "Acme", "target_job_title": "ML Engineer"},
    }
)

SUGGESTIONS_DOC = {
    "target_company": "Acme",
    "target_job_title": "ML Engineer",
    "suggestions": [
        {
            "id": "sug_001",
            "section_id": "professional_summary",
            "section_heading": "PROFESSIONAL SUMMARY",
            "operation": "replace_section_text",
            "current_text": "Old summary.",
            "suggested_text": "Sharper summary emphasizing distributed systems.",
            "reason": "Aligns with the role.",
            "evidence_refs": [
                {"source": "master resume", "quote": "Built distributed systems."}
            ],
            "ats_keywords": ["distributed systems", "developer tooling"],
            "confidence": 0.9,
            "risk": "low",
            "status": "pending",
        },
        {
            "id": "sug_002",
            "section_id": "skills",
            "section_heading": "SKILLS",
            "operation": "add_skill",
            "current_text": "",
            "suggested_text": "Rust",
            "reason": "Job lists Rust as preferred.",
            "evidence_refs": [],
            "ats_keywords": ["Rust"],
            "confidence": 0.6,
            "risk": "medium",
            "status": "pending",
        },
    ],
}


def _seed_imported_version(client, tmp_path: Path, monkeypatch) -> dict:
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\nbody\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# Prompt\nDo the thing.\n", encoding="utf-8"
    )
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    monkeypatch.setenv("JOBAPPLY_CANDIDATE_CONTEXT_ROOT", str(candidate_root))
    monkeypatch.setenv("JOBAPPLY_RUNTIME_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))

    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build things",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()
    run = client.post(
        "/runs",
        json={"job_id": job["id"], "master_resume_id": resume["id"]},
    ).json()

    out = Path(run["run_dir"]) / "output"
    out.mkdir(parents=True, exist_ok=True)
    for name in (
        "change_log.md",
        "claim_audit.md",
        "ats_audit.md",
        "recruiter_review.md",
    ):
        (out / name).write_bytes(f"content for {name}\n".encode("utf-8"))
    (out / "tailored_resume.md").write_bytes(b"content for tailored_resume.md\n")
    (out / "tailored_resume.docx").write_bytes(b"docx\n")
    (out / "tailored_resume.json").write_text(BASE_RESUME_JSON, encoding="utf-8")
    (out / "resume_suggestions.json").write_text(
        json.dumps(SUGGESTIONS_DOC), encoding="utf-8"
    )

    from app.db import SessionLocal
    from app.models import ClaudeRun

    db = SessionLocal()
    try:
        row = db.get(ClaudeRun, run["id"])
        row.status = "completed"
        db.commit()
    finally:
        db.close()

    version = client.post(f"/runs/{run['id']}/import").json()
    return version


def test_import_stores_suggestions(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    resp = client.get(f"/resume-versions/{version['id']}/suggestions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["resume_version_id"] == version["id"]
    assert body["target_company"] == "Acme"
    assert len(body["suggestions"]) == 2
    assert all(s["status"] == "pending" for s in body["suggestions"])
    assert body["has_working_resume"] is False
    assert body["applied_at"] is None


def test_suggestions_expose_base_structured_resume(client, tmp_path, monkeypatch):
    """Task 114: the review workspace renders a document preview, so the
    listing must return the structured ``base_resume`` captured at import."""
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    body = client.get(f"/resume-versions/{version['id']}/suggestions").json()
    base = body["base_resume"]
    assert base is not None
    assert base["header"]["name"] == "Test Candidate"
    assert base["sections"][0]["heading"] == "PROFESSIONAL SUMMARY"
    # No suggestions applied yet -> no working resume.
    assert body["working_resume"] is None


def test_suggestions_expose_working_resume_after_apply(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    client.post(f"/resume-versions/{version['id']}/suggestions/sug_001/accept")
    client.post(f"/resume-versions/{version['id']}/apply-suggestions")
    body = client.get(f"/resume-versions/{version['id']}/suggestions").json()
    working = body["working_resume"]
    assert working is not None
    assert working["sections"][0]["paragraphs"] == [
        "Sharper summary emphasizing distributed systems."
    ]


def test_suggestion_evidence_and_ats_keywords_preserved(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    body = client.get(f"/resume-versions/{version['id']}/suggestions").json()
    first = next(s for s in body["suggestions"] if s["id"] == "sug_001")
    assert first["evidence_refs"] == [
        {"source": "master resume", "quote": "Built distributed systems."}
    ]
    assert first["ats_keywords"] == ["distributed systems", "developer tooling"]
    assert first["reason"] == "Aligns with the role."


def test_accept_endpoint_marks_accepted(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    resp = client.post(
        f"/resume-versions/{version['id']}/suggestions/sug_001/accept"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    # Persisted.
    body = client.get(f"/resume-versions/{version['id']}/suggestions").json()
    statuses = {s["id"]: s["status"] for s in body["suggestions"]}
    assert statuses == {"sug_001": "accepted", "sug_002": "pending"}


def test_reject_endpoint_marks_rejected(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    resp = client.post(
        f"/resume-versions/{version['id']}/suggestions/sug_002/reject"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"


def test_revise_endpoint_stores_instruction(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    resp = client.post(
        f"/resume-versions/{version['id']}/suggestions/sug_001/revise",
        json={"instruction": "Make this more backend-systems focused."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "revised"
    assert body["revision_instruction"] == "Make this more backend-systems focused."


def test_revise_endpoint_requires_instruction(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    resp = client.post(
        f"/resume-versions/{version['id']}/suggestions/sug_001/revise",
        json={"instruction": ""},
    )
    assert resp.status_code == 422, resp.text


def test_apply_suggestions_builds_working_resume(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    # Accept the summary replacement and the skill add.
    client.post(f"/resume-versions/{version['id']}/suggestions/sug_001/accept")
    client.post(f"/resume-versions/{version['id']}/suggestions/sug_002/accept")

    resp = client.post(f"/resume-versions/{version['id']}/apply-suggestions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted_count"] == 2
    assert body["applied_at"]
    working = body["working_resume"]
    assert working["sections"][0]["paragraphs"] == [
        "Sharper summary emphasizing distributed systems."
    ]
    assert "Rust" in working["sections"][1]["groups"][0]["items"]

    # Review state now reports an applied working resume.
    listing = client.get(f"/resume-versions/{version['id']}/suggestions").json()
    assert listing["has_working_resume"] is True
    assert listing["applied_at"] is not None


def test_apply_only_applies_accepted(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    # Reject the summary change; leave the skill add pending.
    client.post(f"/resume-versions/{version['id']}/suggestions/sug_001/reject")

    resp = client.post(f"/resume-versions/{version['id']}/apply-suggestions")
    assert resp.status_code == 200, resp.text
    working = resp.json()["working_resume"]
    # Nothing accepted -> base summary preserved, no Rust added.
    assert working["sections"][0]["paragraphs"] == ["Old summary."]
    assert "Rust" not in working["sections"][1]["groups"][0]["items"]
    assert resp.json()["accepted_count"] == 0


def test_endpoints_404_for_unknown_version(client):
    assert client.get("/resume-versions/nope/suggestions").status_code == 404
    assert (
        client.post("/resume-versions/nope/suggestions/sug_001/accept").status_code
        == 404
    )
    assert client.post("/resume-versions/nope/apply-suggestions").status_code == 404


def test_accept_404_for_unknown_suggestion(client, tmp_path, monkeypatch):
    version = _seed_imported_version(client, tmp_path, monkeypatch)
    resp = client.post(
        f"/resume-versions/{version['id']}/suggestions/sug_999/accept"
    )
    assert resp.status_code == 404
