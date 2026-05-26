"""Unit tests for the prompt harness service and API (task 098).

These tests cover the in-process module (``app.prompt_harness``) and
the HTTP surface (``app.routers.prompts``). The route tests rely on
the ``client`` fixture from ``conftest.py`` and override the runtime
prompt + override roots via ``JOBAPPLY_*`` env vars so tests do not
read or write the repo's real ``runtime_prompts/`` or
``candidate_context/settings/prompt_overrides/`` directories.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---- Module-level tests ----------------------------------------------


def _seed_default_prompt(prompts_root: Path, body: str) -> None:
    prompts_root.mkdir(parents=True, exist_ok=True)
    (prompts_root / "resume_tailoring.md").write_text(body, encoding="utf-8")
    (prompts_root / "resume_revision.md").write_text(
        "# revision prompt body", encoding="utf-8"
    )


def test_list_prompts_returns_known_ids():
    from app.prompt_harness import (
        PROMPT_ID_RESUME_REVISION,
        PROMPT_ID_RESUME_TAILORING,
        list_prompts,
    )

    ids = [p.id for p in list_prompts()]
    assert PROMPT_ID_RESUME_TAILORING in ids
    assert PROMPT_ID_RESUME_REVISION in ids


def test_unknown_prompt_id_rejected():
    from app.prompt_harness import UnknownPromptError, get_prompt_definition

    with pytest.raises(UnknownPromptError):
        get_prompt_definition("not_a_real_prompt")


def test_read_effective_returns_default_when_no_override(tmp_path: Path):
    from app.prompt_harness import (
        get_prompt_definition,
        read_effective,
    )

    prompts_root = tmp_path / "runtime_prompts"
    overrides_root = tmp_path / "overrides"
    _seed_default_prompt(prompts_root, "# default tailoring body")

    body, source = read_effective(
        get_prompt_definition("resume_tailoring"),
        runtime_prompts_root=prompts_root,
        overrides_root=overrides_root,
    )
    assert source == "default"
    assert body == "# default tailoring body"


def test_save_override_then_read_returns_override(tmp_path: Path):
    from app.prompt_harness import (
        get_prompt_definition,
        read_effective,
        save_override,
    )

    prompts_root = tmp_path / "runtime_prompts"
    overrides_root = tmp_path / "overrides"
    _seed_default_prompt(prompts_root, "# default body")

    definition = get_prompt_definition("resume_tailoring")
    save_override(definition, "# my override body", overrides_root=overrides_root)

    body, source = read_effective(
        definition,
        runtime_prompts_root=prompts_root,
        overrides_root=overrides_root,
    )
    assert source == "override"
    assert body == "# my override body"


def test_delete_override_restores_default(tmp_path: Path):
    from app.prompt_harness import (
        delete_override,
        get_prompt_definition,
        read_effective,
        save_override,
    )

    prompts_root = tmp_path / "runtime_prompts"
    overrides_root = tmp_path / "overrides"
    _seed_default_prompt(prompts_root, "# default body")

    definition = get_prompt_definition("resume_tailoring")
    save_override(definition, "# override body", overrides_root=overrides_root)
    deleted = delete_override(definition, overrides_root=overrides_root)
    assert deleted is True

    body, source = read_effective(
        definition,
        runtime_prompts_root=prompts_root,
        overrides_root=overrides_root,
    )
    assert source == "default"
    assert body == "# default body"


def test_save_override_rejects_empty_body(tmp_path: Path):
    from app.prompt_harness import (
        PromptHarnessError,
        get_prompt_definition,
        save_override,
    )

    overrides_root = tmp_path / "overrides"
    with pytest.raises(PromptHarnessError, match="empty"):
        save_override(
            get_prompt_definition("resume_tailoring"),
            "   \n\n",
            overrides_root=overrides_root,
        )


def test_validate_tailoring_warns_when_required_elements_missing():
    from app.prompt_harness import validate_prompt_content

    result = validate_prompt_content("resume_tailoring", "# small prompt body")
    assert result.valid is False
    joined = " ".join(result.warnings).lower()
    assert "claim_audit.md" in joined
    assert "ats_audit.md" in joined


def test_validate_tailoring_passes_with_required_elements():
    from app.prompt_harness import validate_prompt_content

    body = """
    # Tailoring Prompt
    Non-interactive backend job. Do not ask clarifying questions.
    Read evidence and write tailored_resume.md tailored_resume.docx
    change_log.md claim_audit.md ats_audit.md with ATS keywords.
    """
    result = validate_prompt_content("resume_tailoring", body)
    assert result.valid is True
    assert result.warnings == []


def test_validate_revision_warns_on_missing_concepts():
    from app.prompt_harness import validate_prompt_content

    body = "# revision prompt with very little content"
    result = validate_prompt_content("resume_revision", body)
    assert result.valid is False
    joined = " ".join(result.warnings).lower()
    assert "current tailored" in joined


def test_override_path_cannot_escape_overrides_root(tmp_path: Path):
    """The override filename is sourced from the registry, not user input.

    This belt-and-braces test confirms that the resolved override path
    always sits under the overrides root — even if a future registry
    entry tried to sneak in a relative-path filename.
    """
    from app.prompt_harness import (
        PromptHarnessDefinition,
        PromptHarnessError,
        _resolve_override_path,
    )

    bad_definition = PromptHarnessDefinition(
        id="bad",
        label="bad",
        description="bad",
        default_filename="../../etc/passwd",
    )
    overrides_root = tmp_path / "overrides"
    overrides_root.mkdir()
    with pytest.raises(PromptHarnessError, match="escapes"):
        _resolve_override_path(bad_definition, overrides_root)


# ---- HTTP route tests -------------------------------------------------


def _seed_via_env(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    prompts_root = tmp_path / "runtime_prompts"
    overrides_root = tmp_path / "overrides"
    _seed_default_prompt(prompts_root, "# default body for tests\n")
    monkeypatch.setenv("JOBAPPLY_RUNTIME_PROMPTS_ROOT", str(prompts_root))
    monkeypatch.setenv("JOBAPPLY_PROMPT_OVERRIDES_ROOT", str(overrides_root))
    return prompts_root, overrides_root


def test_get_prompts_lists_known_harnesses(client, tmp_path, monkeypatch):
    _seed_via_env(tmp_path, monkeypatch)
    resp = client.get("/prompts")
    assert resp.status_code == 200
    body = resp.json()
    ids = {row["id"] for row in body}
    assert "resume_tailoring" in ids
    assert "resume_revision" in ids
    tailoring = next(row for row in body if row["id"] == "resume_tailoring")
    assert tailoring["has_override"] is False
    assert tailoring["effective_source"] == "default"


def test_get_prompt_detail_returns_default_content(client, tmp_path, monkeypatch):
    _seed_via_env(tmp_path, monkeypatch)
    resp = client.get("/prompts/resume_tailoring")
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_content"].startswith("# default body")
    assert body["override_content"] is None
    assert body["effective_source"] == "default"
    assert len(body["effective_hash"]) == 64


def test_get_prompt_detail_unknown_id_returns_404(client, tmp_path, monkeypatch):
    _seed_via_env(tmp_path, monkeypatch)
    resp = client.get("/prompts/not_a_real_prompt")
    assert resp.status_code == 404


def test_put_override_saves_and_changes_effective_source(
    client, tmp_path, monkeypatch
):
    _seed_via_env(tmp_path, monkeypatch)
    resp = client.put(
        "/prompts/resume_tailoring/override",
        json={"content": "# my edited prompt body"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_override"] is True
    assert body["effective_source"] == "override"
    assert body["override_content"] == "# my edited prompt body"
    assert body["effective_content"] == "# my edited prompt body"


def test_put_override_rejects_empty_body(client, tmp_path, monkeypatch):
    _seed_via_env(tmp_path, monkeypatch)
    resp = client.put(
        "/prompts/resume_tailoring/override",
        json={"content": ""},
    )
    # pydantic rejects min_length=1 with a 422.
    assert resp.status_code == 422


def test_delete_override_restores_default(client, tmp_path, monkeypatch):
    _seed_via_env(tmp_path, monkeypatch)
    client.put(
        "/prompts/resume_tailoring/override",
        json={"content": "# override body"},
    )
    resp = client.delete("/prompts/resume_tailoring/override")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_override"] is False
    assert body["effective_source"] == "default"


def test_validate_endpoint_returns_warnings_for_short_prompt(
    client, tmp_path, monkeypatch
):
    _seed_via_env(tmp_path, monkeypatch)
    resp = client.post("/prompts/resume_tailoring/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert any("claim_audit.md" in w for w in body["warnings"])


# ---- Worker / run-directory integration ------------------------------


CANDIDATE_FILES = (
    "candidate_profile.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
    "project_notes.md",
)


def _make_run_directory_layout(tmp_path: Path) -> dict[str, Path]:
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\n", encoding="utf-8")
    prompts_root = tmp_path / "runtime_prompts"
    _seed_default_prompt(prompts_root, "# default tailoring body\n")
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    overrides_root = tmp_path / "overrides"
    return {
        "candidate_root": candidate_root,
        "prompts_root": prompts_root,
        "runs_root": runs_root,
        "overrides_root": overrides_root,
    }


def _make_job_and_resume():
    from app.models import EvidenceBank, Job, MasterResume

    job = Job(
        id="job-1",
        source_platform="linkedin",
        external_url="https://example.com/job/1",
        company="Acme",
        title="ML Engineer",
        description_text="build things",
        application_method="form",
    )
    resume = MasterResume(
        id="resume-1",
        name="main",
        content_markdown="# Master Resume\n",
    )
    evidence = EvidenceBank(
        id="evidence-1",
        name="main",
        content_markdown="# Evidence\n",
    )
    return job, resume, evidence


def test_run_directory_writes_prompt_snapshot_with_default(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv(
        "JOBAPPLY_PROMPT_OVERRIDES_ROOT", str(tmp_path / "no_overrides_here")
    )
    from app.run_directory import create_run_directory

    layout = _make_run_directory_layout(tmp_path)
    job, resume, evidence = _make_job_and_resume()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=layout["candidate_root"],
        runs_root=layout["runs_root"],
        runtime_prompts_root=layout["prompts_root"],
    )

    snapshot = info.run_dir / "input" / "prompt_snapshot.md"
    assert snapshot.is_file()
    assert snapshot.read_text(encoding="utf-8") == "# default tailoring body\n"

    import json

    metadata = json.loads((info.run_dir / "metadata.json").read_text("utf-8"))
    assert metadata["prompt_id"] == "resume_tailoring"
    assert metadata["prompt_source"] == "default"
    assert metadata["prompt_snapshot_path"] == "input/prompt_snapshot.md"
    assert metadata["prompt_hash"] == info.prompt_hash


def test_run_directory_uses_override_when_present(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(
        "JOBAPPLY_PROMPT_OVERRIDES_ROOT", str(tmp_path / "overrides")
    )
    from app.prompt_harness import get_prompt_definition, save_override
    from app.run_directory import create_run_directory

    layout = _make_run_directory_layout(tmp_path)
    # Save an override using the same env-driven default root.
    save_override(
        get_prompt_definition("resume_tailoring"),
        "# OVERRIDE BODY MATCHING SNAPSHOT\n",
    )

    job, resume, evidence = _make_job_and_resume()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=layout["candidate_root"],
        runs_root=layout["runs_root"],
        runtime_prompts_root=layout["prompts_root"],
    )

    snapshot = (info.run_dir / "input" / "prompt_snapshot.md").read_text("utf-8")
    assert snapshot == "# OVERRIDE BODY MATCHING SNAPSHOT\n"
    import json

    metadata = json.loads((info.run_dir / "metadata.json").read_text("utf-8"))
    assert metadata["prompt_source"] == "override"
    assert metadata["prompt_id"] == "resume_tailoring"


def test_run_directory_uses_revision_prompt_when_feedback_present(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv(
        "JOBAPPLY_PROMPT_OVERRIDES_ROOT", str(tmp_path / "no_overrides")
    )
    from app.run_directory import RevisionFeedbackInput, create_run_directory

    layout = _make_run_directory_layout(tmp_path)
    # The revision prompt is seeded by _seed_default_prompt with a known
    # marker body; the snapshot for a revision run should equal it.
    job, resume, evidence = _make_job_and_resume()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=layout["candidate_root"],
        runs_root=layout["runs_root"],
        runtime_prompts_root=layout["prompts_root"],
        revision_feedback=RevisionFeedbackInput(
            source_resume_version_id="rv-1",
            feedback_markdown="Tighten the summary.",
        ),
    )

    import json

    metadata = json.loads((info.run_dir / "metadata.json").read_text("utf-8"))
    assert metadata["prompt_id"] == "resume_revision"
    snapshot = (info.run_dir / "input" / "prompt_snapshot.md").read_text("utf-8")
    assert snapshot == "# revision prompt body"
