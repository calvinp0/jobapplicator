"""Tests for the persisted default-LLM-provider setting (task 066).

Covers three layers:

- the :mod:`app.settings` helper API (getter default, setter validation,
  round-trip);
- the ``/settings/llm-provider`` GET/PUT endpoints;
- the run-creation route's fallback to the persisted default when the
  request omits ``llm_provider``.
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


# ---- helper API ----


def test_get_default_returns_claude_code_on_fresh_db(client):
    # ``client`` exists so the DB and tables are initialized; we then import
    # the helper and confirm it reads the documented fallback without any
    # row present.
    from app.settings import get_default_llm_provider

    assert get_default_llm_provider() == "claude_code"


def test_set_default_persists_and_getter_reads_back(client):
    from app.settings import get_default_llm_provider, set_default_llm_provider

    returned = set_default_llm_provider("codex")
    assert returned == "codex"
    assert get_default_llm_provider() == "codex"


def test_set_default_rejects_unknown_provider_and_leaves_row_unchanged(client):
    from app.settings import (
        UnknownLLMProviderError,
        get_default_llm_provider,
        set_default_llm_provider,
    )

    set_default_llm_provider("gemini")
    try:
        set_default_llm_provider("definitely-not-real")
    except UnknownLLMProviderError as exc:
        assert "unknown llm_provider" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("expected UnknownLLMProviderError")

    # Rejected update must not have overwritten the prior value.
    assert get_default_llm_provider() == "gemini"


# ---- endpoints ----


def test_get_settings_llm_provider_returns_current_and_available(client):
    resp = client.get("/settings/llm-provider")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["default_provider"] == "claude_code"
    ids = [entry["id"] for entry in body["available"]]
    assert ids == ["claude_code", "codex", "gemini"]
    for entry in body["available"]:
        assert entry["display_name"]
        assert entry["default_binary"]
        assert entry["binary_env_var"]


def test_put_settings_llm_provider_accepts_valid_id(client):
    resp = client.put(
        "/settings/llm-provider", json={"default_provider": "codex"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["default_provider"] == "codex"

    # The change survives a follow-up GET.
    fetched = client.get("/settings/llm-provider").json()
    assert fetched["default_provider"] == "codex"


def test_put_settings_llm_provider_rejects_unknown_with_400(client):
    # Seed a known value so we can also confirm the rejected PUT is a no-op.
    client.put(
        "/settings/llm-provider", json={"default_provider": "gemini"}
    ).raise_for_status()

    resp = client.put(
        "/settings/llm-provider",
        json={"default_provider": "definitely-not-real"},
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "unknown llm_provider" in detail
    # The known providers are listed so the caller can recover without a
    # separate listing call.
    assert "claude_code" in detail
    assert "codex" in detail
    assert "gemini" in detail

    # The previous setting is unchanged.
    assert (
        client.get("/settings/llm-provider").json()["default_provider"]
        == "gemini"
    )


# ---- run-creation fallback ----


def test_create_run_without_provider_uses_persisted_default(
    client, tmp_path, monkeypatch
):
    _prime_run_environment(tmp_path, monkeypatch)
    job_id, resume_id = _create_job_and_resume(client)

    client.put(
        "/settings/llm-provider", json={"default_provider": "codex"}
    ).raise_for_status()

    resp = client.post(
        "/runs", json={"job_id": job_id, "master_resume_id": resume_id}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # The persisted default — not the hardcoded ``claude_code`` fallback —
    # must drive the run.
    assert body["llm_provider"] == "codex"

    metadata = json.loads(
        (Path(body["run_dir"]) / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["llm_provider"] == "codex"
