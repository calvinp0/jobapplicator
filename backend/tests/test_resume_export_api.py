from __future__ import annotations

from pathlib import Path


def _seed_run_with_outputs(client, tmp_path, monkeypatch, *, write_outputs=True):
    """Create a run and (optionally) populate its ``output/`` artifacts.

    Returns the run JSON. The candidate profile carries a real ``Name:`` line
    so the download/export filenames exercise the candidate-name path, and
    the exports root is redirected into ``tmp_path`` so nothing lands in the
    repo's ``candidate_context/exports/``.
    """
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    (candidate_root / "candidate_profile.md").write_text(
        "# Candidate Profile\n\nName: Calvin Pieters\n", encoding="utf-8"
    )
    for name in (
        "project_notes.md",
        "skills_inventory.md",
        "tailoring_preferences.md",
        "resume_dos_and_donts.md",
    ):
        (candidate_root / name).write_text(f"# {name}\nbody\n", encoding="utf-8")

    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# Prompt\nDo the thing.\n", encoding="utf-8"
    )
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    exports_root = tmp_path / "exports"

    monkeypatch.setenv("JOBAPPLY_CANDIDATE_CONTEXT_ROOT", str(candidate_root))
    monkeypatch.setenv("JOBAPPLY_RUNTIME_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("JOBAPPLY_EXPORTS_ROOT", str(exports_root))

    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Example Aero Labs",
            "title": "Scientific Machine Learning Engineer",
            "description_text": "Build ML systems.",
        },
    ).json()
    resume = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\nExperience\n"},
    ).json()
    resp = client.post(
        "/runs",
        json={"job_id": job["id"], "master_resume_id": resume["id"]},
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()

    if write_outputs:
        output = Path(run["run_dir"]) / "output"
        output.mkdir(parents=True, exist_ok=True)
        for name in (
            "tailored_resume.docx",
            "tailored_resume.md",
            "claim_audit.md",
            "ats_audit.md",
            "recruiter_review.md",
        ):
            (output / name).write_text(f"contents of {name}\n", encoding="utf-8")

    return run


def test_download_resume_returns_attachment_with_readable_name(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch)

    resp = client.get(f"/runs/{run['id']}/download-resume")
    assert resp.status_code == 200, resp.text

    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition.lower()
    # Human-readable, not the internal artifact name.
    assert "tailored_resume.docx" not in disposition
    assert "Calvin_Pieters__Example_Aero_Labs" in disposition
    assert disposition.endswith('.docx"') or disposition.endswith(".docx")
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_download_artifact_markdown(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch)

    resp = client.get(f"/runs/{run['id']}/artifacts/claim_audit.md/download")
    assert resp.status_code == 200, resp.text
    assert "attachment" in resp.headers["content-disposition"].lower()
    assert "claim_audit.md" in resp.headers["content-disposition"]


def test_download_missing_artifact_returns_404(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch, write_outputs=False)

    resp = client.get(f"/runs/{run['id']}/download-resume")
    assert resp.status_code == 404, resp.text


def test_download_unknown_artifact_rejected(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch)

    resp = client.get(f"/runs/{run['id']}/artifacts/secrets.txt/download")
    assert resp.status_code == 400, resp.text


def test_download_unknown_run_returns_404(client, tmp_path, monkeypatch):
    _seed_run_with_outputs(client, tmp_path, monkeypatch)
    resp = client.get("/runs/does-not-exist/download-resume")
    assert resp.status_code == 404, resp.text


def test_export_creates_folder_and_copies_artifacts(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch)

    resp = client.post(f"/runs/{run['id']}/export")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True

    export_dir = tmp_path / "exports"
    subfolders = list(export_dir.iterdir())
    assert len(subfolders) == 1
    folder = subfolders[0]
    # The export folder is date-led: <YYYY-MM-DD>__Company__Job__<run>.
    assert folder.name.split("__")[0].count("-") == 2

    docx_name = (
        "Calvin_Pieters__Example_Aero_Labs__"
        "Scientific_Machine_Learning_Engineer"
    )
    docx = [p for p in folder.iterdir() if p.name.startswith(docx_name)]
    assert docx, list(folder.iterdir())
    assert (folder / "tailored_resume.md").is_file()
    assert (folder / "claim_audit.md").is_file()

    # The response lists the copied files with provenance.
    names = {f["name"] for f in body["files"]}
    assert any(n.endswith(".docx") for n in names)


def test_export_missing_outputs_returns_400(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch, write_outputs=False)
    resp = client.post(f"/runs/{run['id']}/export")
    assert resp.status_code == 400, resp.text


def test_export_does_not_overwrite_existing_folder(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch)

    first = client.post(f"/runs/{run['id']}/export")
    second = client.post(f"/runs/{run['id']}/export")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["export_dir"] != second.json()["export_dir"]

    export_dir = tmp_path / "exports"
    assert len(list(export_dir.iterdir())) == 2


def test_export_settings_endpoint_reports_path(client, tmp_path, monkeypatch):
    _seed_run_with_outputs(client, tmp_path, monkeypatch)
    resp = client.get("/settings/exports")
    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == str(tmp_path / "exports")


def test_internal_artifact_remains_after_export(client, tmp_path, monkeypatch):
    run = _seed_run_with_outputs(client, tmp_path, monkeypatch)
    client.post(f"/runs/{run['id']}/export")
    # Exporting copies — the internal run artifact is untouched.
    internal = Path(run["run_dir"]) / "output" / "tailored_resume.docx"
    assert internal.is_file()
