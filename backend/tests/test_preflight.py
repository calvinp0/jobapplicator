"""Tests for the provider-routed preflight analysis pipeline (task 124).

Covers:

- the deterministic extractors for all four artifacts (job summary, ATS
  keywords, role requirements, evidence gap plan);
- ``run_preflight`` writing the full artifact set + manifest with the
  deterministic provider when local LLM is disabled;
- the local-provider path: valid JSON validates and is recorded as local;
  invalid JSON triggers one repair attempt then falls back to the
  deterministic extractor, with the manifest recording the degradation;
- the schema validators;
- the staged-in-run-directory boundary.

The local LLM network boundary (``app.local_llm._post_json``) is
monkeypatched so no live server is needed.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from app import local_llm, preflight


FIXTURE_JD = """# Scientific Machine Learning Engineer — Example Aero Labs

- **Source platform:** linkedin
- **Location:** Remote

## Description

Example Aero Labs is building next-generation simulation tools.

## Requirements
- Experience building machine learning models for scientific data.
- Strong Python engineering skills.
- Experience with PyTorch.

## Preferred
- Cloud deployment experience with AWS.

## Responsibilities
- Develop production ML pipelines.
- Collaborate with researchers.
"""


PREFLIGHT_FILES = (
    "job_summary.json",
    "ats_keywords.json",
    "role_requirements.json",
    "evidence_gap_plan.json",
    "preflight_manifest.json",
)


def _make_run_dir(tmp_path: Path, jd: str = FIXTURE_JD) -> Path:
    """Stage a minimal run directory with a JD and evidence index."""
    run_dir = tmp_path / "run"
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "job_description.md").write_text(jd, encoding="utf-8")
    (input_dir / "evidence_sources_index.md").write_text(
        "# Evidence Sources\n\n(none provided)\n", encoding="utf-8"
    )
    return run_dir


def _completion(content: str, model: str = "llama3.1:8b") -> dict:
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }


def _enabled_config() -> local_llm.LocalLLMConfig:
    return local_llm.LocalLLMConfig(enabled=True)


def _disabled_config() -> local_llm.LocalLLMConfig:
    return local_llm.LocalLLMConfig(enabled=False)


def _long_jd() -> str:
    repeated = "\n".join(
        f"- Requirement {i}: Build Python machine learning systems with AWS and SQL."
        for i in range(500)
    )
    boilerplate = "\n".join(
        f"Equal opportunity boilerplate paragraph {i}. Cookie policy text."
        for i in range(300)
    )
    return f"{FIXTURE_JD}\n\n## Requirements\n{repeated}\n\n## Legal\n{boilerplate}"


# ---- deterministic extractors ----------------------------------------


def test_deterministic_job_summary_extracts_company_and_title():
    summary = preflight.deterministic_job_summary(FIXTURE_JD)
    assert summary["company"] == "Example Aero Labs"
    assert summary["job_title"] == "Scientific Machine Learning Engineer"
    assert summary["location"] == "Remote"
    assert summary["source"] == "input/job_description.md"
    # Unknown fields are null, not invented.
    assert summary["role_family"] is None
    data, reason = preflight.validate_job_summary(summary)
    assert reason is None and data is not None


def test_deterministic_ats_keywords_classifies_kinds_and_categories():
    ats = preflight.deterministic_ats_keywords(FIXTURE_JD)
    groups = ats["groups"]
    # required (from the Requirements section), preferred (Preferred section),
    # tools and domains are all populated from the JD.
    assert "Python" in groups["required"]
    assert "PyTorch" in groups["tools"]
    assert "AWS" in groups["preferred"]
    assert any("Machine Learning" in d for d in groups["domains"])
    # Every keyword carries a valid category + priority and an evidence snippet.
    for kw in ats["keywords"]:
        assert kw["category"] in preflight.KEYWORD_CATEGORIES
        assert kw["priority"] in preflight.KEYWORD_PRIORITIES
        assert kw["evidence"]
    data, reason = preflight.validate_ats_keywords(ats)
    assert reason is None and data is not None


def test_deterministic_role_requirements_extracts_reqs_and_responsibilities():
    rr = preflight.deterministic_role_requirements(FIXTURE_JD)
    reqs = rr["requirements"]
    resps = rr["responsibilities"]
    assert len(reqs) >= 3
    assert all(r["id"].startswith("req_") for r in reqs)
    assert all(r["source_quote"] for r in reqs)
    # The Preferred bullet is captured as a preferred-importance requirement.
    assert any(r["importance"] == "preferred" for r in reqs)
    assert any("production ML pipelines" in r["responsibility"] for r in resps)
    data, reason = preflight.validate_role_requirements(rr)
    assert reason is None and data is not None


def test_deterministic_evidence_gap_plan_references_files_without_claiming():
    rr = preflight.deterministic_role_requirements(FIXTURE_JD)
    files = ["input/evidence_sources_index.md", "input/evidence_bank.md"]
    plan = preflight.deterministic_evidence_gap_plan(rr, files)
    assert plan["likely_evidence_targets"]
    for target in plan["likely_evidence_targets"]:
        # It names candidate files to check, drawn only from the staged list.
        assert set(target["candidate_evidence_files_to_check"]).issubset(set(files))
        # It is a plan, not an evidence confirmation.
        assert "not yet audited" in target["notes"].lower()
    data, reason = preflight.validate_evidence_gap_plan(plan)
    assert reason is None and data is not None


# ---- run_preflight: deterministic fallback ---------------------------


def test_run_preflight_writes_all_artifacts_deterministically(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    result = preflight.run_preflight(run_dir, config=_disabled_config())

    preflight_dir = run_dir / "input" / "preflight"
    for name in PREFLIGHT_FILES:
        path = preflight_dir / name
        assert path.is_file(), f"missing artifact: {name}"
        json.loads(path.read_text(encoding="utf-8"))  # parses

    assert result.provider == preflight.DETERMINISTIC_PROVIDER
    assert result.fallback_used is False


def test_run_preflight_manifest_records_provider_model_status_output(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_disabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    data, reason = preflight.validate_manifest(manifest)
    assert reason is None and data is not None
    assert manifest["provider"] == preflight.DETERMINISTIC_PROVIDER
    assert manifest["fallback_used"] is False
    names = {t["name"] for t in manifest["tasks"]}
    assert names == {
        "job_summary",
        "ats_keyword_extraction",
        "role_requirements",
        "evidence_gap_plan",
    }
    for task in manifest["tasks"]:
        assert task["status"] == "succeeded"
        assert task["provider"] == preflight.DETERMINISTIC_PROVIDER
        assert task["output"].startswith("input/preflight/")


def test_run_preflight_artifacts_staged_inside_run_directory_only(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    result = preflight.run_preflight(run_dir, config=_disabled_config())
    run_dir = run_dir.resolve()
    for path in result.artifact_paths.values():
        assert path.resolve().is_relative_to(run_dir)
        assert (run_dir / "input" / "preflight") in path.resolve().parents or (
            path.resolve().parent == run_dir / "input" / "preflight"
        )


# ---- run_preflight: local provider path ------------------------------


def _fake_local_post_valid(url, payload, *, headers=None, timeout=60.0):
    """Return task-appropriate valid JSON based on the prompt content."""
    content = " ".join(m["content"] for m in payload["messages"]).lower()
    if "ats keyword" in content:
        body = {
            "target_company": "Example Aero Labs",
            "target_job_title": "SciML Engineer",
            "keywords": [
                {
                    "keyword": "Python",
                    "category": "required",
                    "kind": "tool",
                    "evidence": "Python",
                    "priority": "high",
                }
            ],
            "groups": {
                "required": ["Python"],
                "preferred": [],
                "tools": ["Python"],
                "domains": [],
                "responsibilities": [],
            },
        }
    elif "role requirements" in content:
        body = {
            "requirements": [
                {
                    "id": "req_001",
                    "requirement": "Build ML models",
                    "category": "technical",
                    "importance": "required",
                    "source_quote": "Build ML models",
                    "keywords": ["Python"],
                }
            ],
            "responsibilities": [],
            "screening_signals": [],
        }
    elif "evidence gap" in content:
        body = {
            "likely_evidence_targets": [
                {
                    "requirement_id": "req_001",
                    "requirement": "Build ML models",
                    "search_terms": ["Python"],
                    "candidate_evidence_files_to_check": [],
                    "notes": "check",
                }
            ],
            "known_risks_before_tailoring": [],
        }
    else:  # job summary
        body = {
            "company": "Example Aero Labs",
            "job_title": "SciML Engineer",
            "location": "Remote",
            "employment_type": None,
            "seniority": None,
            "role_family": None,
            "summary": "A neutral summary of the role.",
            "source": "input/job_description.md",
        }
    return _completion(json.dumps(body))


def test_run_preflight_local_provider_validates_json(tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_enabled_config())

    assert result.provider == "local_openai_compatible"
    assert result.fallback_used is False
    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    assert manifest["provider"] == "local_openai_compatible"
    assert manifest["model"] == "llama3.1:8b"
    for task in manifest["tasks"]:
        assert task["provider"] == "local_openai_compatible"
        assert task["status"] == "succeeded"
        assert not task.get("fallback_used")
        # Preflight budgets against the smaller default window (task 132) when
        # the user has not explicitly raised context_window_tokens.
        assert task["context"]["context_window_tokens"] == 4096
        assert task["context"]["max_input_tokens"] == 2896
        assert task["context"]["estimated_input_tokens_initial"] > 0
        assert task["context"]["estimated_input_tokens_final"] > 0
        assert task["context"]["compression_used"] is False
        assert task["context"]["fallback_used"] is False
    # The local job_summary content (not the deterministic one) was written.
    summary = json.loads(
        (run_dir / "input" / "preflight" / "job_summary.json").read_text()
    )
    assert summary["job_title"] == "SciML Engineer"


def test_run_preflight_invalid_local_json_repairs_then_falls_back(
    tmp_path, monkeypatch
):
    calls = {"n": 0}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        calls["n"] += 1
        return _completion("this is not json at all")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_enabled_config())

    # Each of the four tasks attempted the local call once and a repair retry
    # once (chat_json's single repair), so at least 2 calls per task.
    assert calls["n"] >= 8
    # The run still completes: deterministic fallback produced every artifact.
    assert result.fallback_used is True
    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    # Top-level provider stays the intended local label; fallback is recorded.
    assert manifest["provider"] == "local_openai_compatible"
    assert manifest["fallback_used"] is True
    assert manifest.get("fallback_reason")
    for task in manifest["tasks"]:
        assert task["provider"] == preflight.DETERMINISTIC_PROVIDER
        assert task["fallback_used"] is True
        assert task["status"] == "succeeded"
    # The deterministic job summary (parsed from the JD header) was written.
    summary = json.loads(
        (run_dir / "input" / "preflight" / "job_summary.json").read_text()
    )
    assert summary["company"] == "Example Aero Labs"


def test_run_preflight_local_disabled_uses_deterministic(tmp_path, monkeypatch):
    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("local provider must not be called when disabled")

    monkeypatch.setattr(local_llm, "_post_json", boom)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_disabled_config())
    assert result.provider == preflight.DETERMINISTIC_PROVIDER
    assert result.fallback_used is False


def test_local_preflight_uses_deterministic_compression_when_enabled(
    tmp_path, monkeypatch
):
    captured_payloads: list[dict] = []

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured_payloads.append(payload)
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path, jd=_long_jd())
    logs: list[str] = []
    cfg = local_llm.LocalLLMConfig(
        enabled=True,
        context_window_tokens=1400,
        reserved_output_tokens=400,
        max_input_tokens=1000,
        allow_compression=True,
        allow_fallback=True,
    )

    preflight.run_preflight(run_dir, config=cfg, on_log=logs.append)

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    assert captured_payloads
    assert "Equal opportunity boilerplate" not in str(captured_payloads)
    first_context = manifest["tasks"][0]["context"]
    assert first_context["compression_used"] is True
    assert first_context["estimated_input_tokens_initial"] > first_context[
        "estimated_input_tokens_final"
    ]
    assert first_context["over_budget"] is False
    joined_logs = "\n".join(logs)
    assert "local LLM input over budget" in joined_logs
    assert "compressed input to" in joined_logs
    assert "local LLM budget check passed" in joined_logs


def test_local_preflight_falls_back_when_still_over_budget(tmp_path, monkeypatch):
    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("over-budget local prompt must not be sent")

    monkeypatch.setattr(local_llm, "_post_json", boom)
    run_dir = _make_run_dir(tmp_path, jd=_long_jd())
    logs: list[str] = []
    cfg = local_llm.LocalLLMConfig(
        enabled=True,
        context_window_tokens=80,
        reserved_output_tokens=20,
        max_input_tokens=40,
        allow_compression=True,
        allow_fallback=True,
    )

    result = preflight.run_preflight(run_dir, config=cfg, on_log=logs.append)

    assert result.fallback_used is True
    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    assert manifest["fallback_used"] is True
    for task in manifest["tasks"]:
        assert task["provider"] == preflight.DETERMINISTIC_PROVIDER
        assert task["status"] == preflight.STATUS_FALLBACK
        assert task["fallback_used"] is True
        assert task["context"]["fallback_used"] is True
    assert "using deterministic ats_keyword_extraction extractor" in "\n".join(logs)


def test_local_preflight_over_budget_without_safeguards_fails_task(tmp_path):
    run_dir = _make_run_dir(tmp_path, jd=_long_jd())
    cfg = local_llm.LocalLLMConfig(
        enabled=True,
        context_window_tokens=80,
        reserved_output_tokens=20,
        max_input_tokens=40,
        allow_compression=False,
        allow_fallback=False,
        abort_on_over_budget=False,
    )

    with pytest.raises(preflight.PreflightError, match="over budget"):
        preflight.run_preflight(run_dir, config=cfg)


def test_local_preflight_prompts_do_not_include_evidence_file_bodies(
    tmp_path, monkeypatch
):
    payloads: list[dict] = []

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        payloads.append(payload)
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)
    input_dir = run_dir / "input"
    (input_dir / "evidence_bank.md").write_text(
        "SECRET FULL EVIDENCE BODY", encoding="utf-8"
    )
    sources_dir = input_dir / "evidence_sources"
    sources_dir.mkdir()
    (sources_dir / "001_secret.md").write_text(
        "SECRET SOURCE BODY", encoding="utf-8"
    )
    (input_dir / "evidence_sources_index.md").write_text(
        "# Evidence Sources\n\n## 1. Secret\n- Staged path: input/evidence_sources/001_secret.md\n",
        encoding="utf-8",
    )

    preflight.run_preflight(run_dir, config=_enabled_config())

    prompt_text = str(payloads)
    assert "SECRET FULL EVIDENCE BODY" not in prompt_text
    assert "SECRET SOURCE BODY" not in prompt_text
    assert "input/evidence_sources/001_secret.md" in prompt_text


def test_run_preflight_emits_log_and_progress_callbacks(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    logs: list[str] = []
    progress: list[str] = []
    preflight.run_preflight(
        run_dir,
        config=_disabled_config(),
        on_log=logs.append,
        on_progress=progress.append,
    )
    joined_logs = "\n".join(logs)
    assert "running preflight analysis" in joined_logs
    assert "preflight provider: deterministic" in joined_logs
    assert "wrote input/preflight/ats_keywords.json" in joined_logs
    assert "wrote input/preflight/preflight_manifest.json" in joined_logs
    assert "Running preflight job analysis" in progress
    assert "Extracting ATS keywords" in progress
    assert "Writing preflight analysis" in progress


# ---- validators ------------------------------------------------------


def test_validate_ats_keywords_rejects_bad_category():
    bad = {
        "keywords": [{"keyword": "Python", "category": "nonsense"}],
        "groups": {},
    }
    data, reason = preflight.validate_ats_keywords(bad)
    assert data is None
    assert "category" in reason


def test_validate_role_requirements_requires_ids():
    bad = {"requirements": [{"requirement": "do things"}]}
    data, reason = preflight.validate_role_requirements(bad)
    assert data is None
    assert "id" in reason


def test_validate_manifest_requires_task_keys():
    bad = {
        "created_at": "now",
        "provider": "deterministic",
        "fallback_used": False,
        "tasks": [{"name": "job_summary"}],
    }
    data, reason = preflight.validate_manifest(bad)
    assert data is None


def test_tailoring_prompt_reads_preflight_artifacts():
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "runtime_prompts"
        / "resume_tailoring.md"
    )
    text = prompt_path.read_text(encoding="utf-8")
    for name in PREFLIGHT_FILES:
        assert f"input/preflight/{name}" in text
    # Advisory framing + JD-wins precedence are stated.
    assert "advisory" in text.lower()
    assert "job description wins" in text.lower()
    # ATS audit starts from the preflight keyword list.
    assert "ats_keywords.json" in text


def test_preflight_task_policy_includes_new_low_risk_tasks():
    # The two new preflight tasks are low-risk, configurable, default-on.
    for task in (local_llm.TASK_ROLE_REQUIREMENTS, local_llm.TASK_EVIDENCE_GAP_PLAN):
        assert local_llm.TASK_RISK[task] == local_llm.RISK_LOW
        assert task in local_llm.CONFIGURABLE_TASKS
        assert local_llm.DEFAULT_ALLOWED_TASKS[task] is True
        cfg = local_llm.LocalLLMConfig(enabled=True)
        assert local_llm.local_allowed_for_task(task, cfg) is True


# ---- effective/assumed context logging (task 127) --------------------


def _ollama_show(context_length: int, arch: str = "llama") -> dict:
    return {
        "model_info": {
            "general.architecture": arch,
            f"{arch}.context_length": context_length,
        }
    }


def test_run_preflight_records_effective_assumed_context_per_task(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)

    # Default (openai_compatible) enabled config: each local task records the
    # assumed context it budgeted against.
    preflight.run_preflight(run_dir, config=_enabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest["tasks"]:
        # Preflight budgets against the smaller default window (task 132); the
        # per-task assumed context tracks that effective budget, not the 8192
        # general default still reported in the top-level summary below.
        assert task["context"]["effective_assumed_context_tokens"] == 4096
        # No num_ctx configured -> the requested_num_ctx key is absent.
        assert "requested_num_ctx" not in task["context"]

    # Top-level context summary: assumed recorded, but an OpenAI-compatible
    # server cannot be verified.
    summary = manifest["context"]
    assert summary["assumed_context_tokens"] == 8192
    assert summary["context_verified"] is False
    assert summary["server_reported_context_tokens"] is None
    assert summary["note"]


def test_run_preflight_records_verified_server_context_for_ollama(
    tmp_path, monkeypatch
):
    def fake_post(url, payload, *, headers=None, timeout=60.0):
        if url.endswith("/api/show"):
            return _ollama_show(16384)
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        num_ctx=16384,
    )
    preflight.run_preflight(run_dir, config=config)

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    summary = manifest["context"]
    assert summary["assumed_context_tokens"] == 8192
    assert summary["server_reported_context_tokens"] == 16384
    assert summary["context_verified"] is True
    assert summary["requested_num_ctx"] == 16384
    # Per-task records mirror the requested server context.
    for task in manifest["tasks"]:
        assert task["context"]["requested_num_ctx"] == 16384


def test_run_preflight_context_detection_failure_does_not_fail(tmp_path, monkeypatch):
    def fake_post(url, payload, *, headers=None, timeout=60.0):
        if url.endswith("/api/show"):
            raise ConnectionError("server down")
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
    )
    # Detection fails, but preflight still completes and writes the manifest.
    result = preflight.run_preflight(run_dir, config=config)
    assert result.fallback_used is False

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    summary = manifest["context"]
    assert summary["context_verified"] is False
    assert summary["server_reported_context_tokens"] is None
    assert summary["assumed_context_tokens"] == 8192


def test_run_preflight_deterministic_run_has_no_context_summary(tmp_path):
    # When the local provider is not the intended primary, there is no
    # server context to assume/verify, so the manifest omits the summary.
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_disabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    assert "context" not in manifest


# ---- task 132: provider-degradation guardrails -----------------------


def test_is_timeout_recognises_both_timeout_causes():
    """_is_timeout treats both connection and generation timeouts as timeouts."""
    # Connection timeout: endpoint_unavailable kind + the documented string.
    connection = local_llm.LLMCallResult(
        ok=False,
        provider="local_openai_compatible",
        model="llama3.1:8b",
        error="timeout after 60s contacting http://localhost:11434/v1/chat/completions",
        error_kind=local_llm.ENDPOINT_ERROR_UNAVAILABLE,
    )
    # Generation timeout: dedicated kind, different message (task 144).
    generation = local_llm.LLMCallResult(
        ok=False,
        provider="local_openai_compatible",
        model="llama3.1:8b",
        error="generation timed out after 60s: reached http://localhost:11434/v1/chat/completions but it did not finish generating",
        error_kind=local_llm.ENDPOINT_ERROR_GENERATION_TIMEOUT,
    )
    # A connection *refused* (also endpoint_unavailable) is NOT a timeout, and a
    # schema/parse failure is not either.
    refused = local_llm.LLMCallResult(
        ok=False,
        provider="local_openai_compatible",
        model="llama3.1:8b",
        error="connection error contacting http://localhost:11434/v1/chat/completions: Connection refused",
        error_kind=local_llm.ENDPOINT_ERROR_UNAVAILABLE,
    )
    schema_failure = local_llm.LLMCallResult(
        ok=False,
        provider="local_openai_compatible",
        model="llama3.1:8b",
        error="response missing choices[0].message.content",
    )

    assert preflight._is_timeout(connection) is True
    assert preflight._is_timeout(generation) is True
    assert preflight._is_timeout(refused) is False
    assert preflight._is_timeout(schema_failure) is False


def test_local_timeout_marks_provider_degraded_but_not_skipped(
    tmp_path, monkeypatch
):
    """A single early timeout degrades the provider; later tasks still try it."""
    calls = {"n": 0}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        calls["n"] += 1
        if calls["n"] == 1:  # the first task (job_summary) times out
            raise TimeoutError("simulated timeout")
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_enabled_config())

    # One timeout: degraded, but below the skip threshold so the provider is
    # still attempted on later tasks.
    assert result.local_degraded is True
    assert result.local_skipped is False
    assert result.fallback_used is True

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    first = manifest["tasks"][0]
    assert first["provider"] == preflight.DETERMINISTIC_PROVIDER
    assert first["fallback_used"] is True
    # A bare ``TimeoutError`` from the read phase is a *generation* timeout
    # (the server was reached but did not finish generating); it still counts
    # as a timeout for degradation (task 144).
    assert first["fallback_reason"].startswith("generation timed out after")
    # Later tasks recovered on the local provider (not skipped).
    for task in manifest["tasks"][1:]:
        assert task["provider"] == "local_openai_compatible"
        assert task["status"] == "succeeded"
        assert not task.get("fallback_used")


def test_schema_failure_does_not_mark_provider_degraded(tmp_path, monkeypatch):
    """An ordinary (non-timeout) local failure must not degrade the provider."""

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _completion("this is not json at all")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_enabled_config())

    # Every task fell back on a schema failure, but that is not a timeout.
    assert result.fallback_used is True
    assert result.local_degraded is False
    assert result.local_skipped is False


def test_repeated_timeouts_skip_local_provider(tmp_path, monkeypatch):
    """After the threshold of timeouts, later tasks bypass the local call."""
    calls = {"n": 0}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        calls["n"] += 1
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_enabled_config())

    # The threshold is 2: the first two tasks each pay a timeout, then the
    # remaining tasks are skipped without contacting the server.
    assert calls["n"] == preflight.LOCAL_SKIP_TIMEOUT_THRESHOLD == 2
    assert result.local_degraded is True
    assert result.local_skipped is True
    assert result.fallback_used is True

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    # Every task still produced a valid artifact via the deterministic floor.
    for filename in PREFLIGHT_FILES:
        assert (run_dir / "input" / "preflight" / filename).is_file()
    for task in manifest["tasks"]:
        assert task["provider"] == preflight.DETERMINISTIC_PROVIDER
        assert task["fallback_used"] is True
    # The tasks after the threshold record the explicit skip reason.
    skipped = [
        t for t in manifest["tasks"]
        if t.get("fallback_reason") == preflight.LOCAL_SKIPPED_REASON
    ]
    assert len(skipped) == 2  # the 3rd and 4th tasks were skipped
    for task in skipped:
        assert task["status"] == preflight.STATUS_FALLBACK


def test_degraded_state_is_per_run(tmp_path, monkeypatch):
    """A fresh run with a healthy client attempts the local provider normally."""
    # First run: the server always times out -> degraded + skipped.
    def timeout_post(url, payload, *, headers=None, timeout=60.0):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(local_llm, "_post_json", timeout_post)
    run_dir_1 = _make_run_dir(tmp_path / "a")
    first = preflight.run_preflight(run_dir_1, config=_enabled_config())
    assert first.local_degraded is True
    assert first.local_skipped is True

    # Second run: a healthy client. State does not carry over.
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir_2 = _make_run_dir(tmp_path / "b")
    second = preflight.run_preflight(run_dir_2, config=_enabled_config())
    assert second.local_degraded is False
    assert second.local_skipped is False
    assert second.fallback_used is False
    assert second.provider == "local_openai_compatible"


def test_preflight_uses_smaller_default_context_but_honours_explicit(
    tmp_path, monkeypatch
):
    """The smaller default applies only when the user has not set the window."""
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)

    # Default config: budget against the smaller preflight default window.
    run_dir_default = _make_run_dir(tmp_path / "default")
    preflight.run_preflight(run_dir_default, config=_enabled_config())
    manifest_default = json.loads(
        (run_dir_default / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest_default["tasks"]:
        ctx = task["context"]
        assert ctx["context_window_tokens"] == (
            preflight.PREFLIGHT_DEFAULT_CONTEXT_WINDOW_TOKENS
        )
        assert ctx["context_window_tokens"] < local_llm.DEFAULT_CONTEXT_WINDOW_TOKENS

    # Explicit user-configured window is honoured verbatim, not lowered.
    run_dir_explicit = _make_run_dir(tmp_path / "explicit")
    explicit_cfg = local_llm.LocalLLMConfig(enabled=True, context_window_tokens=32768)
    preflight.run_preflight(run_dir_explicit, config=explicit_cfg)
    manifest_explicit = json.loads(
        (run_dir_explicit / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest_explicit["tasks"]:
        assert task["context"]["context_window_tokens"] == 32768


def test_preflight_messages_have_no_reasoning_instruction():
    """Preflight prompts request a single JSON object, never step-by-step reasoning."""
    message_sets = [
        preflight._job_summary_messages(FIXTURE_JD),
        preflight._ats_keywords_messages(FIXTURE_JD),
        preflight._role_requirements_messages(FIXTURE_JD),
        preflight._evidence_gap_messages(FIXTURE_JD, ["input/evidence_sources_index.md"]),
    ]
    forbidden = (
        "think step by step",
        "step-by-step",
        "step by step",
        "chain of thought",
        "chain-of-thought",
        "reason through",
        "show your reasoning",
        "let's think",
    )
    for messages in message_sets:
        joined = " ".join(m["content"] for m in messages).lower()
        for phrase in forbidden:
            assert phrase not in joined, f"unexpected reasoning instruction: {phrase!r}"
        # Each preflight prompt explicitly asks for a single JSON object only.
        assert "single json object and nothing else" in joined


# ---- task 133: local LLM performance + attempted-but-fell-back -------


def _timeout_post(url, payload, *, headers=None, timeout=60.0):
    raise TimeoutError("simulated timeout")


def _invalid_json_post(url, payload, *, headers=None, timeout=60.0):
    return _completion("this is not json at all")


def test_local_attempted_task_records_performance(tmp_path, monkeypatch):
    """A genuinely-attempted local task records prompt tokens, elapsed, timeout."""
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)

    preflight.run_preflight(run_dir, config=_enabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest["tasks"]:
        assert task["local_attempted"] is True
        perf = task["performance"]
        # The prompt token estimate reuses the budgeted figure (task 133).
        assert perf["prompt_token_estimate"] == (
            task["context"]["estimated_input_tokens_final"]
        )
        assert perf["prompt_token_estimate"] > 0
        # A real call was issued, so elapsed time is recorded.
        assert isinstance(perf["elapsed_ms"], int)
        assert perf["elapsed_ms"] >= 0
        # The default openai-compatible per-call timeout bounded the attempt.
        assert perf["effective_timeout_seconds"] == 60
    # Top-level: local was attempted, no fallback, not degraded/skipped.
    assert manifest["local_attempted"] is True
    assert manifest["local_degraded"] is False
    assert manifest["local_skipped"] is False
    assert manifest["fallback_used"] is False
    # Manifest still validates with the additive fields.
    data, reason = preflight.validate_manifest(manifest)
    assert reason is None and data is not None


def test_deterministic_only_task_has_no_performance_fields(tmp_path):
    """A deterministic-only run gains no misleading attempted/performance fields."""
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_disabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest["tasks"]:
        assert "local_attempted" not in task
        assert "performance" not in task
    # No top-level attempted/degraded signals on a deterministic-only run.
    assert "local_attempted" not in manifest
    assert "local_degraded" not in manifest
    assert "local_skipped" not in manifest
    data, reason = preflight.validate_manifest(manifest)
    assert reason is None and data is not None


def test_manifest_distinguishes_attempted_from_fallback_on_timeout(
    tmp_path, monkeypatch
):
    """The timeout-degraded path records attempted + degraded distinctly."""
    calls = {"n": 0}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        calls["n"] += 1
        if calls["n"] == 1:  # only the first task times out
            raise TimeoutError("simulated timeout")
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    preflight.run_preflight(run_dir, config=_enabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    # Local was attempted; the run fell back; the provider degraded (one
    # timeout) but did not cross the skip threshold.
    assert manifest["local_attempted"] is True
    assert manifest["fallback_used"] is True
    assert manifest["local_degraded"] is True
    assert manifest["local_skipped"] is False
    # The timed-out task still recorded that local was attempted, with the
    # effective timeout that bounded it (no elapsed time on a timeout).
    first = manifest["tasks"][0]
    assert first["provider"] == preflight.DETERMINISTIC_PROVIDER
    assert first["fallback_used"] is True
    assert first["local_attempted"] is True
    assert first["performance"]["effective_timeout_seconds"] == 60
    assert "elapsed_ms" not in first["performance"]
    data, reason = preflight.validate_manifest(manifest)
    assert reason is None and data is not None


def test_summary_shows_attempted_but_fell_back(tmp_path, monkeypatch):
    """render_preflight_summary surfaces the attempted-but-fell-back line."""
    monkeypatch.setattr(local_llm, "_post_json", _invalid_json_post)
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_enabled_config())

    summary = (
        run_dir / "input" / "preflight" / "preflight_summary.md"
    ).read_text()
    assert preflight.LOCAL_ATTEMPTED_FELL_BACK_MARKER in summary


def test_summary_omits_line_on_clean_local_success(tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_enabled_config())

    summary = (
        run_dir / "input" / "preflight" / "preflight_summary.md"
    ).read_text()
    assert preflight.LOCAL_ATTEMPTED_FELL_BACK_MARKER not in summary


def test_summary_omits_line_on_deterministic_only_run(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_disabled_config())

    summary = (
        run_dir / "input" / "preflight" / "preflight_summary.md"
    ).read_text()
    assert preflight.LOCAL_ATTEMPTED_FELL_BACK_MARKER not in summary


def test_attempted_but_fell_back_marker_emitted_to_trace(tmp_path, monkeypatch):
    """The marker line reaches the run trace via the log/progress callbacks."""
    monkeypatch.setattr(local_llm, "_post_json", _invalid_json_post)
    run_dir = _make_run_dir(tmp_path)
    logs: list[str] = []
    progress: list[str] = []

    preflight.run_preflight(
        run_dir,
        config=_enabled_config(),
        on_log=logs.append,
        on_progress=progress.append,
    )

    joined = "\n".join(logs + progress)
    assert preflight.LOCAL_ATTEMPTED_FELL_BACK_MARKER in joined


def test_no_marker_on_clean_local_success(tmp_path, monkeypatch):
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)
    logs: list[str] = []
    progress: list[str] = []

    preflight.run_preflight(
        run_dir,
        config=_enabled_config(),
        on_log=logs.append,
        on_progress=progress.append,
    )

    joined = "\n".join(logs + progress)
    assert preflight.LOCAL_ATTEMPTED_FELL_BACK_MARKER not in joined


# ---- task 145: generation metrics, thinking, timeout cause, output cap ----


def _ollama_post_with_metrics(url, payload, *, headers=None, timeout=60.0):
    """Ollama-native responses carrying generation metrics + a thinking block.

    Reuses ``_fake_local_post_valid`` to pick task-appropriate JSON content,
    then rewraps it in the native ``/api/chat`` shape with server-reported
    token counts/durations and a structured ``message.thinking`` field, so the
    client populates ``generation_metrics`` and ``thinking_returned``.
    """
    if url.endswith("/api/show"):
        return _ollama_show(16384)
    openai_body = _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)
    content = openai_body["choices"][0]["message"]["content"]
    return {
        "model": "llama3.1:8b",
        "message": {
            "role": "assistant",
            "content": content,
            "thinking": "Let me work through the job description.",
        },
        "prompt_eval_count": 1234,
        "eval_count": 567,
        "total_duration": 8_000_000_000,  # 8s in nanoseconds
        "eval_duration": 4_000_000_000,  # 4s in nanoseconds -> 567/4 = 141.8 tok/s
    }


def _ollama_config() -> local_llm.LocalLLMConfig:
    return local_llm.LocalLLMConfig(
        enabled=True, provider=local_llm.PROVIDER_OLLAMA
    )


def test_attempted_local_task_records_generation_metrics_and_thinking(
    tmp_path, monkeypatch
):
    """An attempted Ollama task records server eval counts, tokens/sec, thinking."""
    monkeypatch.setattr(local_llm, "_post_json", _ollama_post_with_metrics)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(run_dir, config=_ollama_config())
    assert result.fallback_used is False

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest["tasks"]:
        assert task["provider"] == "local_ollama"
        assert task["status"] == "succeeded"
        assert task["local_attempted"] is True
        # Reasoning came back (a structured message.thinking), recorded as a flag
        # without persisting the reasoning text itself.
        assert task["thinking_returned"] is True
        perf = task["performance"]
        # The estimate stays distinct from the server-reported count.
        assert perf["prompt_token_estimate"] == (
            task["context"]["estimated_input_tokens_final"]
        )
        assert perf["prompt_eval_count"] == 1234
        assert perf["prompt_eval_count"] != perf["prompt_token_estimate"]
        assert perf["eval_count"] == 567
        assert perf["total_duration_ms"] == 8000
        assert perf["eval_duration_ms"] == 4000
        assert perf["tokens_per_second"] == 141.8
        # The existing estimate/latency/timeout fields still ride alongside.
        assert isinstance(perf["elapsed_ms"], int)
        assert perf["effective_timeout_seconds"] == 180
    data, reason = preflight.validate_manifest(manifest)
    assert reason is None and data is not None


def test_attempted_local_task_without_metrics_omits_metric_fields(
    tmp_path, monkeypatch
):
    """The OpenAI-compatible provider reports no metrics, so none are recorded."""
    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)

    preflight.run_preflight(run_dir, config=_enabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest["tasks"]:
        assert task["local_attempted"] is True
        # thinking_returned is always present on an attempted task (False here).
        assert task["thinking_returned"] is False
        perf = task["performance"]
        # No server metrics: the estimate is recorded but none of the
        # server-reported fields are.
        assert "prompt_token_estimate" in perf
        for key in (
            "prompt_eval_count",
            "eval_count",
            "total_duration_ms",
            "eval_duration_ms",
            "tokens_per_second",
        ):
            assert key not in perf
        assert "timeout_kind" not in task


def test_generation_timeout_records_distinct_timeout_kind(tmp_path, monkeypatch):
    """A generation-timeout fallback records generation_timeout as the cause."""
    calls = {"n": 0}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        calls["n"] += 1
        if calls["n"] == 1:  # only the first task times out mid-generation
            raise TimeoutError("simulated generation timeout")
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    preflight.run_preflight(run_dir, config=_enabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    first = manifest["tasks"][0]
    assert first["provider"] == preflight.DETERMINISTIC_PROVIDER
    assert first["fallback_used"] is True
    assert first["local_attempted"] is True
    # A bare TimeoutError from the read phase is a *generation* timeout (the
    # server was reached but did not finish): its cause reads distinctly from an
    # unreachable server (task 144/145).
    assert first["timeout_kind"] == local_llm.ENDPOINT_ERROR_GENERATION_TIMEOUT
    # Later tasks recovered cleanly and carry no timeout cause.
    for task in manifest["tasks"][1:]:
        assert task["provider"] == "local_openai_compatible"
        assert "timeout_kind" not in task
    data, reason = preflight.validate_manifest(manifest)
    assert reason is None and data is not None


def test_connection_timeout_records_distinct_timeout_kind(tmp_path, monkeypatch):
    """A connection-timeout fallback records endpoint_unavailable, not generation."""

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # A connect-time timeout surfaces as a URLError wrapping a TimeoutError,
        # which the client classifies as endpoint_unavailable with the documented
        # "timeout after Ns contacting ..." string (task 144).
        raise urllib.error.URLError(TimeoutError("connect timed out"))

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    run_dir = _make_run_dir(tmp_path)

    preflight.run_preflight(run_dir, config=_enabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    # The first two tasks each pay a connection timeout (then the rest skip).
    first = manifest["tasks"][0]
    assert first["fallback_used"] is True
    assert first["local_attempted"] is True
    assert first["timeout_kind"] == local_llm.ENDPOINT_ERROR_UNAVAILABLE
    assert first["timeout_kind"] != local_llm.ENDPOINT_ERROR_GENERATION_TIMEOUT


def test_deterministic_only_task_has_no_generation_fields(tmp_path):
    """A deterministic-only run gains no thinking/metrics/timeout fields."""
    run_dir = _make_run_dir(tmp_path)
    preflight.run_preflight(run_dir, config=_disabled_config())

    manifest = json.loads(
        (run_dir / "input" / "preflight" / "preflight_manifest.json").read_text()
    )
    for task in manifest["tasks"]:
        assert "thinking_returned" not in task
        assert "timeout_kind" not in task
        assert "performance" not in task


def test_configured_output_cap_reaches_local_request(tmp_path, monkeypatch):
    """max_output_tokens flows through the normal config path to the request.

    The cap is enforced at the server before the deterministic fallback can
    kick in, so it must reach the request payload on both provider surfaces.
    """
    captured: list[dict] = []

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured.append(payload)
        return _fake_local_post_valid(url, payload, headers=headers, timeout=timeout)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # OpenAI-compatible: the cap rides the top-level ``max_tokens`` field.
    run_dir_oai = _make_run_dir(tmp_path / "oai")
    oai_cfg = local_llm.LocalLLMConfig(enabled=True, max_output_tokens=256)
    preflight.run_preflight(run_dir_oai, config=oai_cfg)
    chat_payloads = [p for p in captured if "messages" in p]
    assert chat_payloads
    assert all(p["max_tokens"] == 256 for p in chat_payloads)

    # Ollama-native: the cap rides ``options.num_predict``.
    captured.clear()
    run_dir_ollama = _make_run_dir(tmp_path / "ollama")
    ollama_cfg = local_llm.LocalLLMConfig(
        enabled=True, provider=local_llm.PROVIDER_OLLAMA, max_output_tokens=128
    )
    preflight.run_preflight(run_dir_ollama, config=ollama_cfg)
    # Filter out the /api/show detection probe, which has no chat messages.
    chat_payloads = [p for p in captured if "messages" in p]
    assert chat_payloads
    assert all(p["options"]["num_predict"] == 128 for p in chat_payloads)
