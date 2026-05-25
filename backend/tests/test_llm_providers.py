"""Tests for the LLM provider registry, the create-run plumbing, and the
read-only ``/llm-providers`` endpoint (ADR-009, task 065).

These cover three layers:

- the registry module exposes the three initial providers with stable
  ids, non-empty binaries, and a working argv builder;
- ``POST /runs`` accepts an optional ``llm_provider``, defaults to
  ``claude_code``, validates against the registry, and persists the
  value on the ``ClaudeRun`` row and in ``metadata.json``;
- ``GET /llm-providers`` returns the registered providers.
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


def _prime_run_environment(tmp_path: Path, monkeypatch) -> None:
    candidate_root = tmp_path / "candidate_context"
    candidate_root.mkdir()
    for name in CANDIDATE_FILES:
        (candidate_root / name).write_text(f"# {name}\n", encoding="utf-8")
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


def _create_job_and_resume(client) -> tuple[str, str]:
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
    return job["id"], resume["id"]


# ---- registry ----


def test_registry_lists_three_initial_providers():
    from app.llm_providers import list_providers

    providers = list_providers()
    ids = [p.id for p in providers]
    assert ids == ["claude_code", "codex", "gemini"]
    for p in providers:
        # Stable, lowercase, snake_case ids per ADR-009.
        assert p.id == p.id.lower()
        assert p.id.replace("_", "").isalnum()
        # Defaults must be non-empty so a registry entry is always launchable.
        assert p.default_binary
        assert p.binary_env_var
        # The argv builder must accept a binary + permission mode and
        # return a list starting with the binary itself.
        argv = p.build_argv(p.default_binary, "acceptEdits")
        assert isinstance(argv, list)
        assert argv[0] == p.default_binary


def test_registry_get_and_known_provider():
    from app.llm_providers import (
        WORD_HANDOFF_PROVIDER_ID,
        get_provider,
        is_known_provider,
    )

    assert is_known_provider("claude_code")
    assert is_known_provider("codex")
    assert is_known_provider("gemini")
    assert not is_known_provider("bogus")
    # The word-handoff sentinel is metadata-only — not a runnable provider.
    assert not is_known_provider(WORD_HANDOFF_PROVIDER_ID)
    assert get_provider("bogus") is None
    claude = get_provider("claude_code")
    assert claude is not None
    assert claude.binary_env_var == "JOBAPPLY_CLAUDE_BINARY"


def test_resolve_binary_honors_env_override(monkeypatch):
    from app.llm_providers import get_provider, resolve_binary

    codex = get_provider("codex")
    assert codex is not None
    monkeypatch.delenv("JOBAPPLY_CODEX_BINARY", raising=False)
    assert resolve_binary(codex) == codex.default_binary
    monkeypatch.setenv("JOBAPPLY_CODEX_BINARY", "/tmp/custom-codex")
    assert resolve_binary(codex) == "/tmp/custom-codex"


# ---- run-creation plumbing ----


def test_create_run_without_provider_defaults_to_claude_code(
    client, tmp_path, monkeypatch
):
    _prime_run_environment(tmp_path, monkeypatch)
    job_id, resume_id = _create_job_and_resume(client)

    resp = client.post(
        "/runs", json={"job_id": job_id, "master_resume_id": resume_id}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["llm_provider"] == "claude_code"

    metadata = json.loads(
        (Path(body["run_dir"]) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["llm_provider"] == "claude_code"


def test_create_run_with_codex_persists_provider(client, tmp_path, monkeypatch):
    _prime_run_environment(tmp_path, monkeypatch)
    job_id, resume_id = _create_job_and_resume(client)

    resp = client.post(
        "/runs",
        json={
            "job_id": job_id,
            "master_resume_id": resume_id,
            "llm_provider": "codex",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["llm_provider"] == "codex"

    metadata = json.loads(
        (Path(body["run_dir"]) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["llm_provider"] == "codex"

    # The persisted column survives a GET round-trip.
    fetched = client.get(f"/runs/{body['id']}").json()
    assert fetched["llm_provider"] == "codex"


def test_create_run_with_unknown_provider_returns_400(
    client, tmp_path, monkeypatch
):
    _prime_run_environment(tmp_path, monkeypatch)
    job_id, resume_id = _create_job_and_resume(client)

    resp = client.post(
        "/runs",
        json={
            "job_id": job_id,
            "master_resume_id": resume_id,
            "llm_provider": "definitely-not-real",
        },
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "unknown llm_provider" in detail
    # The known providers are surfaced so the caller can recover without a
    # second round trip to the listing endpoint.
    assert "claude_code" in detail
    assert "codex" in detail
    assert "gemini" in detail


# ---- /llm-providers endpoint ----


def test_list_llm_providers_returns_three_entries(client):
    resp = client.get("/llm-providers")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    ids = [entry["id"] for entry in body]
    assert ids == ["claude_code", "codex", "gemini"]
    for entry in body:
        assert entry["display_name"]
        assert entry["default_binary"]
        assert entry["binary_env_var"]
