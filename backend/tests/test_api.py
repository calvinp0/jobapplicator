from __future__ import annotations

from pathlib import Path

from .test_claude_worker import (
    ALL_OUTPUTS,
    _seed_run,
    _write_fake_binary,
)


# Distinctive sentinels so we can prove that the per-run job description text
# flows into the prompt the API returns.
JOB_DESCRIPTION_SENTINEL = "MATCH_ME_JD_API_pq74w"


def _seed_run_with_jd(client, tmp_path, monkeypatch) -> dict:
    """Seed a run whose job_description.md carries a known sentinel string.

    The default ``_seed_run`` posts a job with a short description that does
    not include anything we can grep for in the prompt; this wrapper posts a
    job that does, so the API tests can prove the prompt round-trips through
    the handoff package.
    """
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    candidate_files = (
        "candidate_profile.md",
        "project_notes.md",
        "skills_inventory.md",
        "tailoring_preferences.md",
        "resume_dos_and_donts.md",
    )
    for name in candidate_files:
        (candidate_root / name).write_text(
            f"# {name}\nbody\n", encoding="utf-8"
        )
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
            "description_text": f"Build ML systems. {JOB_DESCRIPTION_SENTINEL}",
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
    return resp.json()


def test_post_word_handoff_creates_package(client, tmp_path, monkeypatch):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)

    resp = client.post(f"/runs/{run['id']}/word-handoff")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["run_id"] == run["id"]
    assert body["status"] == "word_handoff_ready"
    assert body["tailoring_method"] == "word_handoff"

    # Project-relative paths the contract describes.
    rid = run["id"]
    assert body["handoff_dir"] == f"runs/{rid}/word_handoff"
    assert body["prompt_file"] == (
        f"runs/{rid}/word_handoff/02_prompt_for_claude_word.txt"
    )
    assert body["instructions_file"] == (
        f"runs/{rid}/word_handoff/03_instructions.md"
    )
    assert body["expected_output"] == (
        f"runs/{rid}/output/word_tailored_resume.docx"
    )
    # No source DOCX was provided, so the docx field should be null but the
    # rest of the package was still created.
    assert body["resume_docx"] is None

    # And the package files actually exist on disk.
    run_dir = Path(run["run_dir"])
    assert (run_dir / "word_handoff" / "02_prompt_for_claude_word.txt").is_file()
    assert (run_dir / "word_handoff" / "03_instructions.md").is_file()


def test_post_word_handoff_returns_word_handoff_ready_status(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    resp = client.post(f"/runs/{run['id']}/word-handoff")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "word_handoff_ready"


def test_post_word_handoff_surfaces_resume_docx_when_present(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    # Drop a fake source DOCX in the run input so the API surfaces its
    # project-relative path in the response.
    (Path(run["run_dir"]) / "input" / "master_resume.docx").write_bytes(
        b"PK\x03\x04 fake docx"
    )

    resp = client.post(f"/runs/{run['id']}/word-handoff")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["resume_docx"] == (
        f"runs/{run['id']}/word_handoff/01_resume_for_claude_word.docx"
    )


def test_get_word_handoff_returns_metadata(client, tmp_path, monkeypatch):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    client.post(f"/runs/{run['id']}/word-handoff").raise_for_status()

    resp = client.get(f"/runs/{run['id']}/word-handoff")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run["id"]
    assert body["status"] == "word_handoff_ready"
    assert body["tailoring_method"] == "word_handoff"
    assert body["handoff_dir"] == f"runs/{run['id']}/word_handoff"


def test_get_word_handoff_returns_404_when_not_created(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    # No POST yet — handoff folder doesn't exist.
    resp = client.get(f"/runs/{run['id']}/word-handoff")
    assert resp.status_code == 404


def test_get_word_handoff_prompt_returns_prompt_text(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    client.post(f"/runs/{run['id']}/word-handoff").raise_for_status()

    resp = client.get(f"/runs/{run['id']}/word-handoff/prompt")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run["id"]
    content = body["content"]
    assert content.strip() != ""
    # The captured job description text must round-trip through the prompt.
    assert JOB_DESCRIPTION_SENTINEL in content
    # And the formatting-preservation block the contract guarantees.
    assert "Preserve the master resume's existing visual style" in content
    assert "colored headings" in content


def test_get_word_handoff_instructions_returns_markdown(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    client.post(f"/runs/{run['id']}/word-handoff").raise_for_status()

    resp = client.get(f"/runs/{run['id']}/word-handoff/instructions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run["id"]
    content = body["content"]
    assert "01_resume_for_claude_word.docx" in content
    assert "02_prompt_for_claude_word.txt" in content
    assert "../output/word_tailored_resume.docx" in content


def test_word_handoff_endpoints_return_404_for_unknown_run(client):
    """All four endpoints must 404 on an unknown run id, not 500."""
    for path in (
        "/runs/does-not-exist/word-handoff",
        "/runs/does-not-exist/word-handoff/prompt",
        "/runs/does-not-exist/word-handoff/instructions",
    ):
        resp = client.get(path)
        assert resp.status_code == 404, (path, resp.text)

    resp = client.post("/runs/does-not-exist/word-handoff")
    assert resp.status_code == 404, resp.text


def test_post_word_handoff_returns_400_when_input_is_unusable(
    client, tmp_path, monkeypatch
):
    """If the run exists but its ``input/`` contents won't make a useful
    handoff (no job description, no resume), POST should return 400 — not
    500 and not pretend a package was made."""
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    # Strip out the job description so word_handoff has nothing to anchor on.
    # Removing the markdown master_resume too means there is no source resume
    # at all — the package cannot be assembled.
    run_dir = Path(run["run_dir"])
    for fname in (
        "job_description.md",
        "master_resume.md",
    ):
        target = run_dir / "input" / fname
        if target.is_file():
            target.unlink()

    resp = client.post(f"/runs/{run['id']}/word-handoff")
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and detail


def test_word_handoff_status_returns_not_prepared_before_post(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)

    resp = client.get(f"/runs/{run['id']}/word-handoff/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["run_id"] == run["id"]
    assert body["state"] == "not_prepared"
    assert body["handoff_dir_exists"] is False
    assert body["handoff_dir"] == f"runs/{run['id']}/word_handoff"
    files = body["files"]
    assert files["prompt_txt"]["exists"] is False
    assert files["instructions_md"]["exists"] is False
    assert files["expected_output_docx"]["exists"] is False


def test_word_handoff_status_returns_prepared_after_post(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    client.post(f"/runs/{run['id']}/word-handoff").raise_for_status()

    resp = client.get(f"/runs/{run['id']}/word-handoff/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["state"] == "prepared"
    assert body["handoff_dir_exists"] is True
    assert body["files"]["prompt_txt"]["exists"] is True
    assert body["files"]["instructions_md"]["exists"] is True
    assert body["missing_required_files"] == []


def test_word_handoff_status_returns_import_ready_when_result_exists(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    client.post(f"/runs/{run['id']}/word-handoff").raise_for_status()
    # Drop the operator's saved Word result into the expected location.
    output_dir = Path(run["run_dir"]) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "word_tailored_resume.docx").write_bytes(
        b"PK\x03\x04 word result body"
    )

    resp = client.get(f"/runs/{run['id']}/word-handoff/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["state"] == "import_ready"
    assert body["files"]["expected_output_docx"]["exists"] is True


def test_word_handoff_status_returns_404_for_unknown_run(client):
    resp = client.get("/runs/does-not-exist/word-handoff/status")
    assert resp.status_code == 404


def test_post_import_word_result_returns_waiting_when_file_missing(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)

    resp = client.post(f"/runs/{run['id']}/import-word-result")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["run_id"] == run["id"]
    assert body["status"] == "waiting_for_word_result"
    assert body["expected_output"] == (
        f"runs/{run['id']}/output/word_tailored_resume.docx"
    )
    # Operator-facing message must point at the expected save location.
    assert isinstance(body["message"], str) and body["message"]


def test_post_import_word_result_imports_and_marks_completed(
    client, tmp_path, monkeypatch
):
    run = _seed_run_with_jd(client, tmp_path, monkeypatch)
    run_dir = Path(run["run_dir"])
    output_dir = run_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    word_result_bytes = b"PK\x03\x04 word result for api test"
    (output_dir / "word_tailored_resume.docx").write_bytes(word_result_bytes)

    resp = client.post(f"/runs/{run['id']}/import-word-result")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["run_id"] == run["id"]
    assert body["status"] == "completed"
    assert body["word_result"] == (
        f"runs/{run['id']}/output/word_tailored_resume.docx"
    )
    assert body["final_resume"] == (
        f"runs/{run['id']}/output/final_resume.docx"
    )

    final = output_dir / "final_resume.docx"
    assert final.is_file()
    assert final.stat().st_size > 0
    assert final.read_bytes() == word_result_bytes


def test_import_word_result_endpoint_404_for_unknown_run(client):
    resp = client.post("/runs/does-not-exist/import-word-result")
    assert resp.status_code == 404


def test_existing_auto_invoke_endpoint_still_works(
    client, tmp_path, monkeypatch
):
    """The Auto / Claude Code generation path must be unchanged by the new
    word-handoff endpoints living on the same /runs prefix."""
    run = _seed_run(client, tmp_path, monkeypatch)
    binary = _write_fake_binary(tmp_path, exit_code=0, write_outputs=ALL_OUTPUTS)
    monkeypatch.setenv("JOBAPPLY_CLAUDE_BINARY", str(binary))

    resp = client.post(f"/runs/{run['id']}/invoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["error_message"] is None
