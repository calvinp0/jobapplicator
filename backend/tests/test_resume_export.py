from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.resume_export import (
    DOWNLOADABLE_ARTIFACTS,
    ResumeExportError,
    build_export_dir_name,
    build_resume_export_filename,
    discover_candidate_name,
    download_filename_for,
    export_run,
    resolve_output_artifact,
)


# --- Part A: filename utility -----------------------------------------------


def test_filename_includes_candidate_company_job_and_date():
    name = build_resume_export_filename(
        "Calvin Pieters",
        "Example Aero Labs",
        "Scientific Machine Learning Engineer",
        datetime(2026, 5, 27, tzinfo=timezone.utc),
        "d6df714b-1234",
        "docx",
    )
    assert name == (
        "Calvin_Pieters__Example_Aero_Labs__"
        "Scientific_Machine_Learning_Engineer__2026-05-27.docx"
    )


def test_filename_sanitizes_unsafe_characters():
    name = build_resume_export_filename(
        "Calvin / Pieters",
        "Acme, Inc.",
        "Sr. Engineer (Backend)",
        "2026-05-27",
        "run-1",
        "docx",
    )
    # No slashes, commas, parentheses, or other shell-special characters.
    assert "/" not in name
    assert "\\" not in name
    for ch in ",()*;&|$ ":
        assert ch not in name
    assert name.endswith(".docx")
    assert name.startswith("Calvin_Pieters__Acme_Inc__Sr_Engineer_Backend__")


def test_filename_accepts_iso_string_date():
    name = build_resume_export_filename(
        "Jane Doe",
        "Acme",
        "SDE",
        "2026-05-27T12:34:56+00:00",
        "run-1",
        "docx",
    )
    assert name == "Jane_Doe__Acme__SDE__2026-05-27.docx"


def test_filename_falls_back_to_resume_when_candidate_missing():
    name = build_resume_export_filename(
        None,
        "Example Aero Labs",
        "ML Engineer",
        "2026-05-27",
        "run-1",
        "docx",
    )
    assert name == "Resume__Example_Aero_Labs__ML_Engineer__2026-05-27.docx"


def test_filename_appends_short_run_id_when_company_and_title_missing():
    name = build_resume_export_filename(
        None,
        "",
        "",
        "2026-05-27",
        "d6df714b-9999-aaaa",
        "docx",
    )
    # With no company/title to disambiguate, the short run id keeps the
    # otherwise-degenerate "Resume__<date>" name unique.
    assert name == "Resume__2026-05-27__d6df714b.docx"


def test_filename_prevents_path_traversal_in_components():
    name = build_resume_export_filename(
        "../../etc",
        "../secrets",
        "..",
        "2026-05-27",
        "run-1",
        "docx",
    )
    assert "/" not in name
    assert ".." not in name
    assert name.endswith(".docx")


def test_filename_caps_overly_long_components():
    name = build_resume_export_filename(
        "x" * 500,
        "y" * 500,
        "z" * 500,
        "2026-05-27",
        "run-1",
        "docx",
    )
    # Every component is capped, so the whole name stays well under common
    # filesystem limits.
    assert len(name) < 255
    for component in name[: -len(".docx")].split("__"):
        assert len(component) <= 64


def test_export_dir_name_leads_with_date_and_short_run_id():
    name = build_export_dir_name(
        "Example Aero Labs",
        "Scientific Machine Learning Engineer",
        "2026-05-27",
        "d6df714b-1234",
    )
    assert name == (
        "2026-05-27__Example_Aero_Labs__"
        "Scientific_Machine_Learning_Engineer__d6df714b"
    )


def test_download_filename_for_non_docx_keeps_stable_basename():
    name = download_filename_for(
        "claim_audit.md",
        "Calvin Pieters",
        "Acme",
        "SDE",
        "2026-05-27",
        "run-1",
    )
    assert name == "Calvin_Pieters__Acme__SDE__2026-05-27__claim_audit.md"


# --- candidate name discovery ----------------------------------------------


def test_discover_candidate_name_reads_name_line(tmp_path):
    (tmp_path / "candidate_profile.md").write_text(
        "# Candidate Profile\n\nName: Calvin Pieters\n", encoding="utf-8"
    )
    assert discover_candidate_name(tmp_path) == "Calvin Pieters"


def test_discover_candidate_name_ignores_placeholder_heading(tmp_path):
    (tmp_path / "candidate_profile.md").write_text(
        "# Candidate Profile\n\nTODO: fill me in.\n", encoding="utf-8"
    )
    assert discover_candidate_name(tmp_path) is None


def test_discover_candidate_name_missing_file(tmp_path):
    assert discover_candidate_name(tmp_path) is None


# --- resolve_output_artifact (path safety) ---------------------------------


def test_resolve_output_artifact_rejects_unknown_name(tmp_path):
    with pytest.raises(ResumeExportError):
        resolve_output_artifact(tmp_path, "secrets.txt")


def test_resolve_output_artifact_rejects_traversal(tmp_path):
    # Even if it were allow-listed, a traversal name must never escape.
    with pytest.raises(ResumeExportError):
        resolve_output_artifact(tmp_path, "../../etc/passwd")


def test_resolve_output_artifact_resolves_known_name(tmp_path):
    path = resolve_output_artifact(tmp_path, "tailored_resume.docx")
    assert path == (tmp_path / "output" / "tailored_resume.docx").resolve()


# --- export_run (Part D) ----------------------------------------------------


def _write_output_artifacts(run_dir: Path, names) -> None:
    output = run_dir / "output"
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        (output / name).write_text(f"contents of {name}\n", encoding="utf-8")


def test_export_run_creates_subfolder_and_copies_docx(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    _write_output_artifacts(run_dir, ["tailored_resume.docx"])
    exports_root = tmp_path / "exports"

    result = export_run(
        run_dir,
        exports_root,
        candidate_name="Calvin Pieters",
        company="Example Aero Labs",
        job_title="ML Engineer",
        created_at="2026-05-27",
        run_id="d6df714b-1234",
    )

    assert result.export_dir.parent == exports_root
    assert result.export_dir.name.startswith("2026-05-27__Example_Aero_Labs")
    docx_name = "Calvin_Pieters__Example_Aero_Labs__ML_Engineer__2026-05-27.docx"
    assert (result.export_dir / docx_name).is_file()
    assert any(f.name == docx_name for f in result.files)


def test_export_run_copies_markdown_and_audits_when_present(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    _write_output_artifacts(
        run_dir,
        [
            "tailored_resume.docx",
            "tailored_resume.md",
            "claim_audit.md",
            "ats_audit.md",
            "recruiter_review.md",
        ],
    )
    exports_root = tmp_path / "exports"

    result = export_run(
        run_dir,
        exports_root,
        candidate_name="Calvin Pieters",
        company="Acme",
        job_title="SDE",
        created_at="2026-05-27",
        run_id="run-1",
    )

    for stable in (
        "tailored_resume.md",
        "claim_audit.md",
        "ats_audit.md",
        "recruiter_review.md",
    ):
        assert (result.export_dir / stable).is_file()


def test_export_run_does_not_overwrite_existing_folder(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    _write_output_artifacts(run_dir, ["tailored_resume.docx"])
    exports_root = tmp_path / "exports"

    first = export_run(
        run_dir,
        exports_root,
        candidate_name="Calvin Pieters",
        company="Acme",
        job_title="SDE",
        created_at="2026-05-27",
        run_id="run-1",
    )
    second = export_run(
        run_dir,
        exports_root,
        candidate_name="Calvin Pieters",
        company="Acme",
        job_title="SDE",
        created_at="2026-05-27",
        run_id="run-1",
    )

    assert first.export_dir != second.export_dir
    assert second.export_dir.name.endswith("-2")
    assert first.export_dir.is_dir()
    assert second.export_dir.is_dir()


def test_export_run_raises_when_nothing_to_export(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    (run_dir / "output").mkdir(parents=True)
    with pytest.raises(ResumeExportError):
        export_run(
            run_dir,
            tmp_path / "exports",
            candidate_name=None,
            company="Acme",
            job_title="SDE",
            created_at="2026-05-27",
            run_id="run-1",
        )


def test_export_run_writes_only_inside_exports_root(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    _write_output_artifacts(run_dir, ["tailored_resume.docx"])
    exports_root = tmp_path / "exports"

    result = export_run(
        run_dir,
        exports_root,
        candidate_name="Calvin Pieters",
        company="Acme",
        job_title="SDE",
        created_at="2026-05-27",
        run_id="run-1",
    )

    # Every written file resolves inside the managed exports root.
    resolved_root = exports_root.resolve()
    assert result.export_dir.resolve().is_relative_to(resolved_root)
    for f in result.files:
        assert (result.export_dir / f.name).resolve().is_relative_to(resolved_root)


def test_downloadable_artifacts_are_output_relative_names():
    # Guard: the allow-list must never contain a path separator.
    for name in DOWNLOADABLE_ARTIFACTS:
        assert "/" not in name and "\\" not in name
