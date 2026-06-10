"""Tests for the provider/run trace model (task 129).

Covers the pure :mod:`app.provider_trace` model (event serialization,
preflight→event mapping, the compact summary, and the no-credentials
guarantee) plus a ``run_preflight`` → events integration so the local-LLM
provider/model surfaces in the trace, and a deterministic-fallback case.

The worker/API end-to-end persistence is covered in test_claude_worker.py
(``test_invoke_run_writes_provider_trace`` and friends), which exercises
the full ``invoke_claude_run`` path and the ``GET /runs/{id}`` response.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import local_llm, preflight, provider_trace as pt


# ---- event serialization --------------------------------------------


def _ollama_event() -> pt.TraceEvent:
    return pt.TraceEvent(
        step=pt.STEP_JOB_SUMMARY,
        provider=pt.PROVIDER_OLLAMA,
        status=pt.STATUS_COMPLETE,
        model="qwen3.5:9b",
        duration_ms=1800,
        context_budget_tokens=8192,
        usable_input_tokens=6500,
        requested_num_ctx=8192,
        server_reported_context_tokens=262144,
        context_verified=True,
        endpoint_host="localhost",
    )


def test_event_derives_label_and_provider_label():
    event = _ollama_event()
    assert event.label == "Job summary"
    assert event.provider_label == "Ollama"


def test_event_to_dict_nests_advanced_fields_under_details():
    payload = _ollama_event().to_dict()
    # Compact fields at the top level.
    assert payload["step"] == "job_summary"
    assert payload["provider"] == "ollama"
    assert payload["provider_label"] == "Ollama"
    assert payload["model"] == "qwen3.5:9b"
    assert payload["status"] == "complete"
    assert payload["duration_ms"] == 1800
    # Advanced/technical fields live under a nested details block.
    details = payload["details"]
    assert details["context_budget_tokens"] == 8192
    assert details["usable_input_tokens"] == 6500
    assert details["requested_num_ctx"] == 8192
    assert details["server_reported_context_tokens"] == 262144
    assert details["context_verified"] is True
    assert details["endpoint_host"] == "localhost"


def test_event_to_dict_omits_empty_details():
    # A Claude/backend step has no context budget, so no details block.
    payload = pt.backend_event(
        pt.STEP_DOCX_RENDER, status=pt.STATUS_COMPLETE, duration_ms=700
    ).to_dict()
    assert "details" not in payload
    assert payload["provider"] == "backend"
    assert payload["provider_label"] == "Backend renderer"


def test_event_serialization_never_contains_credentials():
    # The endpoint host may be recorded, but never a key/url/full endpoint.
    blob = json.dumps(_ollama_event().to_dict())
    lowered = blob.lower()
    assert "api_key" not in lowered
    assert "apikey" not in lowered
    assert "authorization" not in lowered
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "base_url" not in lowered


# ---- preflight → events ---------------------------------------------


def _preflight_task(**overrides):
    base = dict(
        name="job_summary",
        provider="local_ollama",
        model="qwen3.5:9b",
        status=preflight.STATUS_SUCCEEDED,
        output="input/preflight/job_summary.json",
        context={
            "context_window_tokens": 8192,
            "max_input_tokens": 6500,
            "compression_used": False,
            "requested_num_ctx": 8192,
        },
        duration_ms=1800,
    )
    base.update(overrides)
    return preflight.PreflightTaskResult(**base)


def _preflight_result(tasks) -> preflight.PreflightResult:
    return preflight.PreflightResult(
        preflight_dir=Path("input/preflight"),
        provider="local_ollama",
        model="qwen3.5:9b",
        fallback_used=any(t.fallback_used for t in tasks),
        fallback_reason=None,
        tasks=tasks,
    )


def test_events_from_preflight_records_ollama_provider_and_model():
    result = _preflight_result([_preflight_task()])
    events = pt.events_from_preflight(result)
    assert len(events) == 1
    event = events[0]
    assert event.step == "job_summary"
    assert event.provider == "ollama"
    assert event.provider_label == "Ollama"
    assert event.model == "qwen3.5:9b"
    assert event.status == "complete"
    assert event.duration_ms == 1800
    assert event.context_budget_tokens == 8192
    assert event.usable_input_tokens == 6500
    assert event.requested_num_ctx == 8192


def test_events_from_preflight_maps_ats_task_name_to_step():
    result = _preflight_result(
        [_preflight_task(name="ats_keyword_extraction")]
    )
    assert pt.events_from_preflight(result)[0].step == "ats_keywords"


def test_events_from_preflight_records_deterministic_fallback():
    task = _preflight_task(
        provider=preflight.DETERMINISTIC_PROVIDER,
        model=None,
        status=preflight.STATUS_FALLBACK,
        fallback_used=True,
        fallback_reason="Ollama request failed",
    )
    event = pt.events_from_preflight(_preflight_result([task]))[0]
    assert event.provider == "deterministic"
    assert event.status == "fallback"
    assert event.fallback_used is True
    assert event.warning and "deterministic" in event.warning.lower()


# ---- summary ---------------------------------------------------------


def _full_trace() -> list[pt.TraceEvent]:
    return [
        _ollama_event(),
        pt.TraceEvent(
            step=pt.STEP_EVIDENCE_GAP_PLAN,
            provider=pt.PROVIDER_DETERMINISTIC,
            status=pt.STATUS_FALLBACK,
            fallback_used=True,
            warning="Ollama request failed; deterministic fallback used.",
        ),
        pt.claude_event(
            pt.STEP_RESUME_GENERATION,
            provider_id="claude_code",
            status=pt.STATUS_COMPLETE,
            duration_ms=42000,
        ),
        pt.claude_event(
            pt.STEP_CLAIM_AUDIT,
            provider_id="claude_code",
            status=pt.STATUS_COMPLETE,
        ),
        pt.backend_event(
            pt.STEP_DOCX_RENDER, status=pt.STATUS_COMPLETE, duration_ms=700
        ),
    ]


def test_build_summary_label_and_providers_used():
    summary = pt.build_summary(_full_trace())
    assert "Tailoring: Claude Code" in summary["label"]
    assert "DOCX: Backend" in summary["label"]
    assert summary["label"].startswith("Preflight: Ollama")
    assert summary["providers_used"] == [
        "ollama",
        "deterministic",
        "claude_code",
        "backend",
    ]
    assert summary["tailoring"] == "Claude Code"
    assert summary["docx"] == "Backend renderer"


def test_build_summary_collects_warnings():
    summary = pt.build_summary(_full_trace())
    assert summary["has_warnings"] is True
    assert any("fallback" in w.lower() for w in summary["warnings"])


def test_build_summary_no_local_llm_is_deterministic_band():
    events = [
        pt.TraceEvent(
            step=pt.STEP_JOB_SUMMARY,
            provider=pt.PROVIDER_DETERMINISTIC,
            status=pt.STATUS_COMPLETE,
        ),
        pt.claude_event(
            pt.STEP_RESUME_GENERATION,
            provider_id="claude_code",
            status=pt.STATUS_COMPLETE,
        ),
        pt.backend_event(pt.STEP_DOCX_RENDER, status=pt.STATUS_COMPLETE),
    ]
    summary = pt.build_summary(events)
    assert "Preflight: deterministic backend" in summary["label"]
    assert summary["has_warnings"] is False


def test_build_summary_skipped_steps_excluded_from_providers_used():
    events = [
        pt.claude_event(
            pt.STEP_RESUME_GENERATION,
            provider_id="claude_code",
            status=pt.STATUS_COMPLETE,
        ),
        # A skipped/disabled local suggestion step must not pull its provider
        # into the compact summary.
        pt.TraceEvent(
            step=pt.STEP_RESUME_SUGGESTIONS,
            provider=pt.PROVIDER_OLLAMA,
            status=pt.STATUS_SKIPPED,
        ),
    ]
    summary = pt.build_summary(events)
    assert "ollama" not in summary["providers_used"]


# ---- persistence -----------------------------------------------------


def test_write_and_read_provider_trace_round_trips(tmp_path):
    pt.write_provider_trace(tmp_path, _full_trace())
    path = tmp_path / pt.PROVIDER_TRACE_FILENAME
    assert path.is_file()
    rows = pt.read_provider_trace(tmp_path)
    assert [r["step"] for r in rows] == [
        "job_summary",
        "evidence_gap_plan",
        "resume_generation",
        "claim_audit",
        "docx_render",
    ]


def test_read_provider_trace_absent_returns_empty(tmp_path):
    assert pt.read_provider_trace(tmp_path) == []


# ---- run_preflight integration --------------------------------------


def test_run_preflight_local_provider_surfaces_in_trace(tmp_path, monkeypatch):
    """A real local-LLM preflight run records the local provider per step."""
    from tests.test_preflight import _fake_local_post_valid, _make_run_dir

    monkeypatch.setattr(local_llm, "_post_json", _fake_local_post_valid)
    run_dir = _make_run_dir(tmp_path)

    result = preflight.run_preflight(
        run_dir, config=local_llm.LocalLLMConfig(enabled=True)
    )
    events = pt.events_from_preflight(result)

    assert {e.step for e in events} == {
        "job_summary",
        "ats_keywords",
        "role_requirements",
        "evidence_gap_plan",
    }
    for event in events:
        assert event.provider == "openai_compatible"
        assert event.provider_label == "OpenAI-compatible local LLM"
        assert event.model == "llama3.1:8b"
        assert event.status == "complete"
        # Timing was stamped by run_preflight.
        assert event.duration_ms is not None
        assert event.context_budget_tokens == 8192
