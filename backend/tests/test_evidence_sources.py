"""Tests for evidence source discovery, listing, and run staging.

Covers task 090 acceptance criteria: candidate-context subfolders are
scanned for ``.md``/``.txt``/``.docx`` files, the listing endpoint
combines them with seeded DB evidence banks, the demo seed does not
hide real files, IDs are stable, and run creation accepts multiple
evidence sources (via either the new ``evidence_source_ids`` field or
the legacy single ``evidence_bank_id`` field).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from .test_run_directory import CANDIDATE_FILES, _make_docx_file


def _prime_run_layout(tmp_path: Path, monkeypatch) -> Path:
    """Build a minimal candidate_context/runtime_prompts/runs layout.

    Returns the candidate_context path so the caller can drop evidence
    files into its subfolders.
    """
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\n", encoding="utf-8")
    (candidate_root / "project_notes.md").write_text("notes\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# prompt\n", encoding="utf-8"
    )
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    monkeypatch.setenv("JOBAPPLY_CANDIDATE_CONTEXT_ROOT", str(candidate_root))
    monkeypatch.setenv("JOBAPPLY_RUNTIME_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))
    return candidate_root


# ---- discovery module ----

def test_discovery_lists_md_txt_and_docx_files(tmp_path):
    from app.evidence_source_discovery import list_filesystem_evidence_sources

    root = tmp_path / "candidate_context"
    (root / "evidence_banks").mkdir(parents=True)
    (root / "project_notes").mkdir()
    (root / "resume_variants").mkdir()

    (root / "evidence_banks" / "rmg.md").write_text("rmg\n", encoding="utf-8")
    (root / "project_notes" / "arc.md").write_text("arc\n", encoding="utf-8")
    (root / "project_notes" / "publications.txt").write_text(
        "pubs\n", encoding="utf-8"
    )
    _make_docx_file(root / "resume_variants" / "qchem.docx", body="QCHEMBODY")

    records = list_filesystem_evidence_sources(candidate_root=root)
    by_name = {r.name: r for r in records}
    assert {"rmg.md", "arc.md", "publications.txt", "qchem.docx"} <= set(
        by_name
    )
    assert by_name["rmg.md"].source_type == "evidence_bank"
    assert by_name["arc.md"].source_type == "project_note"
    assert by_name["publications.txt"].source_type == "project_note"
    assert by_name["qchem.docx"].source_type == "resume_variant"
    assert by_name["qchem.docx"].source_format == "docx"
    # Each id is a stable filesystem id; reading twice returns the same value.
    again = list_filesystem_evidence_sources(candidate_root=root)
    assert {r.id for r in again} == {r.id for r in records}


def test_discovery_skips_unsupported_and_hidden_files(tmp_path):
    from app.evidence_source_discovery import list_filesystem_evidence_sources

    root = tmp_path / "candidate_context"
    (root / "evidence_banks").mkdir(parents=True)
    (root / "evidence_banks" / "ok.md").write_text("ok", encoding="utf-8")
    (root / "evidence_banks" / "binary.pdf").write_bytes(b"%PDF-")
    (root / "evidence_banks" / ".DS_Store").write_text("noise", encoding="utf-8")
    (root / "evidence_banks" / ".~lock.foo.docx#").write_text(
        "lock", encoding="utf-8"
    )
    (root / "evidence_banks" / "~$temp.docx").write_text("tmp", encoding="utf-8")

    records = list_filesystem_evidence_sources(candidate_root=root)
    names = {r.name for r in records}
    assert names == {"ok.md"}


def test_discovery_returns_empty_when_root_missing(tmp_path):
    from app.evidence_source_discovery import list_filesystem_evidence_sources

    missing = tmp_path / "does_not_exist"
    assert list_filesystem_evidence_sources(candidate_root=missing) == []


def test_resolve_filesystem_evidence_round_trips(tmp_path):
    from app.evidence_source_discovery import (
        list_filesystem_evidence_sources,
        resolve_filesystem_evidence_source,
    )

    root = tmp_path / "candidate_context"
    (root / "project_notes").mkdir(parents=True)
    (root / "project_notes" / "arc.md").write_text("arc body", encoding="utf-8")

    records = list_filesystem_evidence_sources(candidate_root=root)
    assert len(records) == 1
    resolved = resolve_filesystem_evidence_source(
        records[0].id, candidate_root=root
    )
    assert resolved is not None
    assert resolved.absolute_path == records[0].absolute_path


# ---- /evidence-sources endpoint ----

def test_list_evidence_sources_combines_db_and_filesystem(
    client, tmp_path, monkeypatch
):
    candidate_root = tmp_path / "candidate_context"
    (candidate_root / "evidence_banks").mkdir(parents=True)
    (candidate_root / "project_notes").mkdir()
    (candidate_root / "evidence_banks" / "rmg.md").write_text(
        "rmg evidence", encoding="utf-8"
    )
    (candidate_root / "project_notes" / "arc.md").write_text(
        "arc notes", encoding="utf-8"
    )
    monkeypatch.setenv("JOBAPPLY_CANDIDATE_CONTEXT_ROOT", str(candidate_root))

    # Seed a non-demo DB evidence bank and the demo one.
    client.post(
        "/evidence-banks",
        json={"name": "Real bank", "content_markdown": "real"},
    )
    client.post(
        "/evidence-banks",
        json={"name": "Demo Evidence Bank", "content_markdown": "demo"},
    )

    resp = client.get("/evidence-sources")
    assert resp.status_code == 200
    body = resp.json()
    names = [item["name"] for item in body]
    # Filesystem entries come first, then non-demo DB rows, then the demo
    # row last. That keeps real files at the top of the picker as soon as
    # the user drops any into candidate_context/.
    assert names[:2] == ["arc.md", "rmg.md"] or names[:2] == ["rmg.md", "arc.md"]
    fs_names = [n for n in names if n in ("arc.md", "rmg.md")]
    assert sorted(fs_names) == ["arc.md", "rmg.md"]
    assert names[-1] == "Demo Evidence Bank"
    assert names[-2] == "Real bank"

    # Shape: every entry carries the same minimum surface.
    for item in body:
        assert {"id", "name", "source_type", "source", "updated_at"} <= set(item)


def test_list_evidence_sources_serves_when_no_subfolders_exist(client):
    # The default conftest layout has no candidate_context subfolders;
    # the endpoint should still respond with just the DB seeds (or an
    # empty list if none).
    resp = client.get("/evidence-sources")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---- run creation: multi-source staging ----

def test_post_run_with_multiple_evidence_sources_stages_each_file(
    client, tmp_path, monkeypatch
):
    candidate_root = _prime_run_layout(tmp_path, monkeypatch)
    (candidate_root / "evidence_banks").mkdir()
    (candidate_root / "project_notes").mkdir(exist_ok=True)
    (candidate_root / "resume_variants").mkdir()

    (candidate_root / "evidence_banks" / "rmg.md").write_text(
        "RMG_EVIDENCE_SENTINEL", encoding="utf-8"
    )
    (candidate_root / "project_notes" / "arc.md").write_text(
        "ARC_NOTE_SENTINEL", encoding="utf-8"
    )
    _make_docx_file(
        candidate_root / "resume_variants" / "qchem.docx",
        body="QCHEM_DOCX_SENTINEL",
    )

    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()

    sources = client.get("/evidence-sources").json()
    assert len(sources) == 3
    ids = [s["id"] for s in sources]

    resp = client.post(
        "/runs",
        json={
            "job_id": job["id"],
            "master_resume_id": resume["id"],
            "evidence_source_ids": ids,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body["evidence_source_ids"]) == set(ids)
    run_dir = Path(body["run_dir"])

    sources_dir = run_dir / "input" / "evidence_sources"
    assert sources_dir.is_dir()
    staged_names = sorted(p.name for p in sources_dir.iterdir())
    # One markdown per source, plus the docx sibling for the docx source.
    md_files = [n for n in staged_names if n.endswith(".md")]
    docx_files = [n for n in staged_names if n.endswith(".docx")]
    assert len(md_files) == 3
    assert len(docx_files) == 1

    bodies = "\n".join(
        (sources_dir / n).read_text(encoding="utf-8") for n in md_files
    )
    assert "RMG_EVIDENCE_SENTINEL" in bodies
    assert "ARC_NOTE_SENTINEL" in bodies
    assert "QCHEM_DOCX_SENTINEL" in bodies

    index = (run_dir / "input" / "evidence_sources_index.md").read_text(
        encoding="utf-8"
    )
    assert "# Evidence Sources" in index
    # Index names every staged source.
    assert "rmg.md" in index
    assert "arc.md" in index
    assert "qchem.docx" in index
    assert "input/evidence_sources/" in index

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert set(metadata["evidence_source_ids"]) == set(ids)

    shutil.rmtree(run_dir, ignore_errors=True)


def test_post_run_legacy_single_evidence_bank_still_works(
    client, tmp_path, monkeypatch
):
    _prime_run_layout(tmp_path, monkeypatch)
    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()
    bank = client.post(
        "/evidence-banks",
        json={"name": "legacy", "content_markdown": "LEGACY_BANK_SENTINEL"},
    ).json()

    resp = client.post(
        "/runs",
        json={
            "job_id": job["id"],
            "master_resume_id": resume["id"],
            "evidence_bank_id": bank["id"],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["evidence_bank_id"] == bank["id"]
    # Legacy id is folded into evidence_source_ids so the staged set is
    # uniform regardless of which field the caller used.
    assert body["evidence_source_ids"] == [bank["id"]]
    run_dir = Path(body["run_dir"])
    # The legacy file is still written for back-compat with the existing
    # contract; the new staged file is also present.
    assert (run_dir / "input" / "evidence_bank.md").read_text(
        encoding="utf-8"
    ).strip() == "LEGACY_BANK_SENTINEL"
    sources_dir = run_dir / "input" / "evidence_sources"
    assert sources_dir.is_dir()
    md_files = list(sources_dir.glob("*.md"))
    assert len(md_files) == 1
    assert "LEGACY_BANK_SENTINEL" in md_files[0].read_text(encoding="utf-8")

    shutil.rmtree(run_dir, ignore_errors=True)


def test_post_run_with_no_evidence_writes_empty_index(
    client, tmp_path, monkeypatch
):
    """The index file is always written so the prompt never 404s on read."""
    _prime_run_layout(tmp_path, monkeypatch)
    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()

    resp = client.post(
        "/runs",
        json={"job_id": job["id"], "master_resume_id": resume["id"]},
    )
    assert resp.status_code == 201, resp.text
    run_dir = Path(resp.json()["run_dir"])
    index = (run_dir / "input" / "evidence_sources_index.md").read_text(
        encoding="utf-8"
    )
    assert "Evidence Sources" in index
    assert "(none provided)" in index
    # No staged sources directory needed for a run with zero selections.
    assert not (run_dir / "input" / "evidence_sources").exists()

    shutil.rmtree(run_dir, ignore_errors=True)


def test_post_run_with_unknown_evidence_source_id_returns_404(
    client, tmp_path, monkeypatch
):
    _prime_run_layout(tmp_path, monkeypatch)
    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()
    resp = client.post(
        "/runs",
        json={
            "job_id": job["id"],
            "master_resume_id": resume["id"],
            "evidence_source_ids": ["fs:bogus0000000000"],
        },
    )
    assert resp.status_code == 404
    assert "evidence source" in resp.json()["detail"].lower()


# ---- prompt distinguishes primary resume from evidence sources ----

def test_runtime_prompt_references_evidence_sources_index():
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "runtime_prompts"
        / "resume_tailoring.md"
    )
    text = prompt_path.read_text(encoding="utf-8")
    assert "input/evidence_sources_index.md" in text
    # The prompt must distinguish primary resume from evidence sources.
    assert "Primary Resume" in text or "primary resume" in text
    assert "evidence sources" in text.lower()
    # It must describe the DOCX evidence fallback path.
    assert "input/evidence_sources/" in text
