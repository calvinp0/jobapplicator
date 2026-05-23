from __future__ import annotations

from pathlib import Path


def _setup_roots(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    rv_root = tmp_path / "resume_versions"
    rv_root.mkdir()
    monkeypatch.setenv("JOBAPPLY_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("JOBAPPLY_RESUME_VERSIONS_ROOT", str(rv_root))
    return runs_root, rv_root


def _patch_spawn(monkeypatch) -> list[Path]:
    """Replace ``_spawn_open_command`` so tests don't launch a GUI app."""
    calls: list[Path] = []
    import app.routers.files as files_mod

    def fake_spawn(path: Path) -> None:
        calls.append(path)

    monkeypatch.setattr(files_mod, "_spawn_open_command", fake_spawn)
    return calls


def test_open_path_inside_runs_root_succeeds(client, tmp_path, monkeypatch):
    runs_root, _ = _setup_roots(tmp_path, monkeypatch)
    calls = _patch_spawn(monkeypatch)

    target = runs_root / "run-x" / "output" / "tailored_resume.docx"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"docx bytes")

    r = client.post("/files/open", json={"path": str(target)})
    assert r.status_code == 204, r.text

    assert calls == [target.resolve()]


def test_open_path_outside_roots_is_rejected(client, tmp_path, monkeypatch):
    _setup_roots(tmp_path, monkeypatch)
    calls = _patch_spawn(monkeypatch)

    escape = tmp_path / "escape.docx"
    escape.write_bytes(b"nope")

    r = client.post("/files/open", json={"path": str(escape)})
    assert r.status_code == 400, r.text
    assert "outside" in r.json()["detail"].lower()
    assert calls == []


def test_open_path_via_symlink_escape_is_rejected(client, tmp_path, monkeypatch):
    runs_root, _ = _setup_roots(tmp_path, monkeypatch)
    calls = _patch_spawn(monkeypatch)

    # Real file outside roots; symlink inside runs_root pointing at it.
    real = tmp_path / "secret.docx"
    real.write_bytes(b"secret")
    link = runs_root / "run-x" / "tailored_resume.docx"
    link.parent.mkdir(parents=True)
    link.symlink_to(real)

    r = client.post("/files/open", json={"path": str(link)})
    assert r.status_code == 400, r.text
    assert calls == []


def test_open_missing_file_returns_404(client, tmp_path, monkeypatch):
    runs_root, _ = _setup_roots(tmp_path, monkeypatch)
    _patch_spawn(monkeypatch)

    # Path is inside roots, but the file does not exist.
    missing = runs_root / "run-x" / "missing.docx"

    r = client.post("/files/open", json={"path": str(missing)})
    assert r.status_code == 404, r.text


def test_open_resume_version_resolves_docx_path(client, tmp_path, monkeypatch):
    runs_root, _ = _setup_roots(tmp_path, monkeypatch)
    calls = _patch_spawn(monkeypatch)

    # Seed a job + master resume + a ResumeVersion row whose docx_path lives
    # inside runs_root.
    job = client.post(
        "/jobs",
        json={
            "source_platform": "linkedin",
            "company": "Acme",
            "title": "ML Engineer",
            "description_text": "build things",
        },
    ).json()
    master = client.post(
        "/master-resumes",
        json={"name": "main", "content_markdown": "# resume\n"},
    ).json()

    docx_path = runs_root / "run-y" / "output" / "tailored_resume.docx"
    docx_path.parent.mkdir(parents=True)
    docx_path.write_bytes(b"version docx")

    from app.db import SessionLocal
    from app.models import ResumeVersion

    db = SessionLocal()
    try:
        version = ResumeVersion(
            job_id=job["id"],
            master_resume_id=master["id"],
            version_number=1,
            docx_path=str(docx_path),
            source="claude_run",
        )
        db.add(version)
        db.commit()
        db.refresh(version)
        version_id = version.id
    finally:
        db.close()

    r = client.post("/files/open", json={"resume_version_id": version_id})
    assert r.status_code == 204, r.text
    assert calls == [docx_path.resolve()]


def test_open_resume_version_unknown_returns_404(client, tmp_path, monkeypatch):
    _setup_roots(tmp_path, monkeypatch)
    _patch_spawn(monkeypatch)

    r = client.post("/files/open", json={"resume_version_id": "does-not-exist"})
    assert r.status_code == 404


def test_open_requires_path_or_version(client, tmp_path, monkeypatch):
    _setup_roots(tmp_path, monkeypatch)
    _patch_spawn(monkeypatch)

    r = client.post("/files/open", json={})
    assert r.status_code == 422
