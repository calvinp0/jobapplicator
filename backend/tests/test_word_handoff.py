from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


CANDIDATE_FILES = (
    "candidate_profile.md",
    "skills_inventory.md",
    "tailoring_preferences.md",
    "resume_dos_and_donts.md",
)

# Distinctive sentinel strings so the test asserts the right inputs flow into
# the right output files without matching unrelated boilerplate.
JOB_DESCRIPTION_SENTINEL = "MATCH_ME_JOB_DESCRIPTION_kx72p"
RESUME_MARKDOWN_SENTINEL = "MATCH_ME_RESUME_MARKDOWN_qz91v"
FAKE_DOCX_BYTES = b"PK\x03\x04 not really a docx but distinctive bytes"


@pytest.fixture()
def fixture_layout(tmp_path: Path) -> dict[str, Path]:
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(
            f"# {name}\nstable content\n", encoding="utf-8"
        )
    (candidate_root / "project_notes.md").write_text(
        "notes\n", encoding="utf-8"
    )

    prompts_root = tmp_path / "runtime_prompts"
    prompts_root.mkdir()
    (prompts_root / "resume_tailoring.md").write_text(
        "# Prompt\nRead inputs and write outputs.\n", encoding="utf-8"
    )

    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    return {
        "candidate_root": candidate_root,
        "prompts_root": prompts_root,
        "runs_root": runs_root,
    }


def _make_objects():
    from app.models import EvidenceBank, Job, MasterResume

    job = Job(
        id="job-1",
        source_platform="linkedin",
        external_url="https://example.com/job/1",
        company="Acme",
        title="ML Engineer",
        location="Remote",
        description_text=f"Build ML systems. {JOB_DESCRIPTION_SENTINEL}",
        application_method="form",
    )
    resume = MasterResume(
        id="resume-1",
        name="main",
        content_markdown=(
            f"# Master Resume\n{RESUME_MARKDOWN_SENTINEL}\nExperience: ...\n"
        ),
    )
    evidence = EvidenceBank(
        id="evidence-1",
        name="main",
        content_markdown="# Evidence\nProject X: shipped.\n",
    )
    return job, resume, evidence


def _create_run(fixture_layout) -> Path:
    """Create a fresh run directory and return its path."""
    from app.run_directory import create_run_directory

    job, resume, evidence = _make_objects()
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
    )
    return info.run_dir


def test_handoff_folder_is_created(fixture_layout):
    from app.word_handoff import (
        WORD_HANDOFF_DIRNAME,
        create_word_handoff_package,
    )

    run_dir = _create_run(fixture_layout)
    info = create_word_handoff_package(run_dir)

    assert info.handoff_dir == run_dir / WORD_HANDOFF_DIRNAME
    assert info.handoff_dir.is_dir()


def test_source_docx_is_copied_when_present(fixture_layout):
    from app.word_handoff import (
        RESUME_DOCX_FILENAME,
        create_word_handoff_package,
    )

    run_dir = _create_run(fixture_layout)
    # Drop a fake "DOCX" into the run input with the project's canonical name.
    (run_dir / "input" / "master_resume.docx").write_bytes(FAKE_DOCX_BYTES)

    info = create_word_handoff_package(run_dir)
    copied = info.handoff_dir / RESUME_DOCX_FILENAME

    assert info.resume_docx_copied is True
    assert copied.is_file()
    assert copied.read_bytes() == FAKE_DOCX_BYTES


def test_prompt_file_is_created(fixture_layout):
    from app.word_handoff import PROMPT_FILENAME, create_word_handoff_package

    run_dir = _create_run(fixture_layout)
    info = create_word_handoff_package(run_dir)

    prompt_path = info.handoff_dir / PROMPT_FILENAME
    assert prompt_path.is_file()
    assert prompt_path.read_text(encoding="utf-8").strip() != ""


def test_prompt_includes_job_description_text(fixture_layout):
    from app.word_handoff import PROMPT_FILENAME, create_word_handoff_package

    run_dir = _create_run(fixture_layout)
    info = create_word_handoff_package(run_dir)

    prompt_text = (info.handoff_dir / PROMPT_FILENAME).read_text(
        encoding="utf-8"
    )
    assert JOB_DESCRIPTION_SENTINEL in prompt_text


def test_prompt_includes_formatting_preservation_instructions(fixture_layout):
    from app.word_handoff import PROMPT_FILENAME, create_word_handoff_package

    run_dir = _create_run(fixture_layout)
    info = create_word_handoff_package(run_dir)

    prompt_text = (info.handoff_dir / PROMPT_FILENAME).read_text(
        encoding="utf-8"
    )
    # Spot-check the formatting-preservation block and the change/audit footer.
    assert "Preserve the existing Word formatting" in prompt_text
    assert "fonts, margins, section spacing" in prompt_text
    assert "CHANGE LOG" in prompt_text
    assert "CLAIM AUDIT" in prompt_text


def test_instructions_file_is_created(fixture_layout):
    from app.word_handoff import (
        INSTRUCTIONS_FILENAME,
        create_word_handoff_package,
    )

    run_dir = _create_run(fixture_layout)
    info = create_word_handoff_package(run_dir)

    instructions_path = info.handoff_dir / INSTRUCTIONS_FILENAME
    assert instructions_path.is_file()
    body = instructions_path.read_text(encoding="utf-8")
    assert "01_resume_for_claude_word.docx" in body
    assert "02_prompt_for_claude_word.txt" in body
    assert "../output/word_tailored_resume.docx" in body


def test_missing_docx_does_not_fail_if_markdown_exists(fixture_layout):
    from app.word_handoff import (
        PROMPT_FILENAME,
        RESUME_DOCX_FILENAME,
        create_word_handoff_package,
    )

    run_dir = _create_run(fixture_layout)
    # No DOCX is staged in the run input — only the markdown master resume
    # that create_run_directory wrote.
    assert not (run_dir / "input" / "master_resume.docx").exists()

    info = create_word_handoff_package(run_dir)

    assert info.resume_docx_copied is False
    assert not (info.handoff_dir / RESUME_DOCX_FILENAME).exists()
    # The markdown should still flow through as fallback context in the prompt.
    prompt_text = (info.handoff_dir / PROMPT_FILENAME).read_text(
        encoding="utf-8"
    )
    assert info.resume_markdown_included is True
    assert RESUME_MARKDOWN_SENTINEL in prompt_text


def test_metadata_tailoring_method_is_updated_to_word_handoff(fixture_layout):
    from app.run_directory import get_tailoring_method
    from app.word_handoff import create_word_handoff_package

    run_dir = _create_run(fixture_layout)
    create_word_handoff_package(run_dir)

    assert get_tailoring_method(run_dir) == "word_handoff"
    metadata = json.loads(
        (run_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["tailoring_method"] == "word_handoff"


def test_status_is_updated_to_word_handoff_ready(fixture_layout):
    from app.run_directory import get_run_status
    from app.word_handoff import create_word_handoff_package

    run_dir = _create_run(fixture_layout)
    create_word_handoff_package(run_dir)

    assert get_run_status(run_dir) == "word_handoff_ready"


def test_run_log_records_handoff_creation(fixture_layout):
    from app.word_handoff import (
        EXPECTED_WORD_OUTPUT_RELPATH,
        create_word_handoff_package,
    )

    run_dir = _create_run(fixture_layout)
    info = create_word_handoff_package(run_dir)

    log_text = (run_dir / "run.log").read_text(encoding="utf-8")
    assert "jobapply: created Claude for Word handoff package" in log_text
    assert f"jobapply: handoff_dir={info.handoff_dir}" in log_text
    assert (
        f"jobapply: expected Word output={EXPECTED_WORD_OUTPUT_RELPATH}"
        in log_text
    )


def test_updated_at_advances_when_handoff_runs(fixture_layout):
    """Sanity: writing the package bumps metadata.updated_at past created_at."""
    from datetime import timedelta

    from app.run_directory import create_run_directory
    from app.word_handoff import create_word_handoff_package

    job, resume, evidence = _make_objects()
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    info = create_run_directory(
        job=job,
        master_resume=resume,
        evidence_bank=evidence,
        candidate_context_root=fixture_layout["candidate_root"],
        runs_root=fixture_layout["runs_root"],
        runtime_prompts_root=fixture_layout["prompts_root"],
        now=fixed_now,
    )

    create_word_handoff_package(
        info.run_dir, now=fixed_now + timedelta(seconds=45)
    )
    metadata = json.loads(
        (info.run_dir / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["updated_at"].startswith("2026-01-01T00:00:45")


def test_missing_run_directory_raises(tmp_path):
    from app.word_handoff import WordHandoffError, create_word_handoff_package

    with pytest.raises(WordHandoffError, match="run directory does not exist"):
        create_word_handoff_package(tmp_path / "does_not_exist")
