"""Tests for the experimental local LLM provider (task 123).

Covers four layers:

- the persisted ``/settings/local-llm`` config (save/load, key masking);
- the ``/llm/local/test-connection`` endpoint (success and failure);
- the :class:`~app.local_llm.LocalLLMClient` (request shape, JSON schema
  validation with a repair retry);
- the task policy (high-risk tasks default to Claude Code; low-risk tasks
  are allowed; resume tailoring is blocked unless explicitly enabled) and
  the run-metadata helper.

The network boundary (``app.local_llm._post_json``) is monkeypatched so no
live server is needed.
"""

from __future__ import annotations

import sys
import urllib.error


def _completion(content: str, model: str = "llama3.1:8b") -> dict:
    """A minimal OpenAI-compatible chat-completions response body."""
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
    }


def _ollama_completion(content: str, model: str = "llama3.1:8b") -> dict:
    """A minimal Ollama native ``/api/chat`` response body."""
    return {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


def _load_local_llm_with_temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "JOBAPPLY_DATABASE_URL", f"sqlite:///{tmp_path / 'local-llm.db'}"
    )
    for mod_name in [
        "app.routers.local_llm",
        "app.routers.settings",
        "app.routers",
        "app.local_llm",
        "app.models",
        "app.db",
        "app",
    ]:
        sys.modules.pop(mod_name, None)

    from app import models  # noqa: F401  (registers tables)
    from app.db import Base, engine, ensure_runtime_columns

    Base.metadata.create_all(bind=engine)
    ensure_runtime_columns()

    import app.local_llm as local_llm

    return local_llm


# ---- settings persistence --------------------------------------------


def test_local_llm_settings_save_and_load(client):
    # Defaults on a fresh DB: disabled, documented endpoint/model.
    read = client.get("/settings/local-llm")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["enabled"] is False
    assert body["base_url"] == "http://localhost:11434/v1"
    assert body["model"] == "llama3.1:8b"
    assert body["context_window_tokens"] == 8192
    assert body["reserved_output_tokens"] == 1200
    assert body["max_input_tokens"] == 6500
    assert body["allow_compression"] is True
    assert body["allow_fallback"] is True
    assert body["abort_on_over_budget"] is False
    assert body["num_ctx"] is None
    assert body["allowed_tasks"]["resume_tailoring"] is False

    updated = client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "openai_compatible",
            "base_url": "http://localhost:1234/v1",
            "model": "qwen2.5-coder:14b",
            "timeout_seconds": 30,
            "context_window_tokens": 4096,
            "reserved_output_tokens": 512,
            "max_input_tokens": 3000,
            "allow_compression": False,
            "allow_fallback": False,
            "abort_on_over_budget": True,
            "allowed_tasks": {"ats_keywords": True, "resume_tailoring": False},
        },
    )
    assert updated.status_code == 200, updated.text

    # The change survives a follow-up GET.
    fetched = client.get("/settings/local-llm").json()
    assert fetched["enabled"] is True
    assert fetched["base_url"] == "http://localhost:1234/v1"
    assert fetched["model"] == "qwen2.5-coder:14b"
    assert fetched["timeout_seconds"] == 30
    assert fetched["context_window_tokens"] == 4096
    assert fetched["reserved_output_tokens"] == 512
    assert fetched["max_input_tokens"] == 3000
    assert fetched["allow_compression"] is False
    assert fetched["allow_fallback"] is False
    assert fetched["abort_on_over_budget"] is True


def test_local_llm_num_ctx_round_trips_through_settings(client):
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "num_ctx": 16384,
        },
    ).raise_for_status()

    body = client.get("/settings/local-llm").json()
    assert body["num_ctx"] == 16384


def test_local_llm_num_ctx_rejects_non_positive(client):
    resp = client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "num_ctx": 0,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "num_ctx" in resp.json()["detail"]


def test_get_config_parses_and_validates_num_ctx(monkeypatch, tmp_path):
    import pytest

    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)

    # Unset on a fresh DB.
    assert local_llm.get_config().num_ctx is None

    # A positive int persists and reloads.
    config = local_llm.save_config(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        timeout_seconds=local_llm.DEFAULT_TIMEOUT_SECONDS,
        allowed_tasks={},
        num_ctx=8192,
    )
    assert config.num_ctx == 8192
    assert local_llm.get_config().num_ctx == 8192

    # A non-positive value is rejected, independent of the context budget.
    with pytest.raises(local_llm.LocalLLMValidationError):
        local_llm.save_config(
            enabled=True,
            provider=local_llm.PROVIDER_OLLAMA,
            base_url="http://localhost:11434/v1",
            model="llama3.1:8b",
            timeout_seconds=local_llm.DEFAULT_TIMEOUT_SECONDS,
            allowed_tasks={},
            num_ctx=-5,
        )


def test_get_config_treats_invalid_stored_num_ctx_as_none(monkeypatch, tmp_path):
    import json

    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)
    from app.db import SessionLocal
    from app.models import AppSetting

    # A garbage stored value (non-int) is coerced to None on load.
    with SessionLocal() as session:
        session.add(
            AppSetting(
                key=local_llm.LOCAL_LLM_SETTING_KEY,
                value=json.dumps(
                    {
                        "enabled": True,
                        "provider": "ollama",
                        "base_url": "http://localhost:11434/v1",
                        "model": "llama3.1:8b",
                        "num_ctx": "not-an-int",
                    }
                ),
            )
        )
        session.commit()

    assert local_llm.get_config().num_ctx is None


def test_local_llm_settings_rejects_impossible_budget(client):
    resp = client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "context_window_tokens": 1024,
            "reserved_output_tokens": 1200,
            "max_input_tokens": 100,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "reserved_output_tokens" in resp.json()["detail"]


def test_local_llm_settings_save_computes_omitted_max_input_tokens(
    monkeypatch, tmp_path
):
    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)

    config = local_llm.save_config(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        timeout_seconds=local_llm.DEFAULT_TIMEOUT_SECONDS,
        allowed_tasks={},
        context_window_tokens=2048,
        reserved_output_tokens=512,
        max_input_tokens=None,
    )
    assert config.context_window_tokens == 2048
    assert config.reserved_output_tokens == 512
    assert config.max_input_tokens == 1536

    stored = local_llm.get_settings_view()
    assert stored["context_window_tokens"] == 2048
    assert stored["reserved_output_tokens"] == 512
    assert stored["max_input_tokens"] == 1536


def test_local_llm_settings_rejects_bad_base_url(client):
    resp = client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "localhost:11434",  # missing scheme
            "model": "llama3.1:8b",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "base_url" in resp.json()["detail"]


def test_local_llm_api_key_is_masked_in_read(client):
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "api_key": "super-secret-token",
        },
    ).raise_for_status()

    body = client.get("/settings/local-llm").json()
    assert body["has_api_key"] is True
    # The plaintext key must never appear in the read view.
    assert "super-secret-token" not in str(body)
    assert body["api_key_preview"] and "super-secret-token" not in body[
        "api_key_preview"
    ]


def test_local_llm_preserve_existing_key(client):
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "api_key": "keep-me",
        },
    ).raise_for_status()

    # Update other fields without resending the key.
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "mistral-small",
            "preserve_existing_key": True,
        },
    ).raise_for_status()

    import app.local_llm as local_llm

    assert local_llm.get_config().api_key == "keep-me"


# ---- test-connection endpoint ----------------------------------------


def test_test_connection_success(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        return _completion("pong")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    resp = client.post(
        "/llm/local/test-connection",
        json={"base_url": "http://localhost:11434/v1", "model": "llama3.1:8b"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "model responded" in body["message"].lower()
    assert "configured context window: 8192 tokens" in body["message"].lower()
    assert "usable input budget: 6500 tokens" in body["message"].lower()
    assert body["context_window_tokens"] == 8192
    assert body["max_input_tokens"] == 6500
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"


def test_test_connection_computes_omitted_max_input_tokens_for_budget_overrides(
    monkeypatch, tmp_path
):
    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)
    from app.routers.local_llm import LocalLLMTestRequest, test_local_llm_connection

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _completion("pong")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    result = test_local_llm_connection(
        LocalLLMTestRequest(
            base_url="http://localhost:11434/v1",
            model="llama3.1:8b",
            context_window_tokens=2048,
            reserved_output_tokens=512,
        )
    )
    assert result.ok is True
    assert "configured context window: 2048 tokens" in result.message.lower()
    assert "usable input budget: 1536 tokens" in result.message.lower()
    assert result.context_window_tokens == 2048
    assert result.max_input_tokens == 1536


def test_test_connection_timeout(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    resp = client.post(
        "/llm/local/test-connection",
        json={"base_url": "http://localhost:9/v1", "model": "x"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert "timeout" in (body["error"] or "").lower()


def test_test_connection_connection_error(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    resp = client.post("/llm/local/test-connection", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]


# ---- client request shape --------------------------------------------


def test_client_formats_openai_compatible_request(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _completion('{"ok": true}', model="qwen")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        base_url="http://localhost:11434/v1/",  # trailing slash handled
        model="qwen2.5-coder:14b",
        timeout_seconds=42,
        api_key="tok",
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert result.ok is True
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["payload"]["model"] == "qwen2.5-coder:14b"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert captured["timeout"] == 42


def test_client_sends_num_ctx_for_ollama_native(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        num_ctx=16384,
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert result.ok is True
    # Routed to the native /api/chat surface (the /v1 suffix is stripped).
    assert captured["url"] == "http://localhost:11434/api/chat"
    # The configured server context reaches the request body.
    assert captured["payload"]["options"]["num_ctx"] == 16384
    assert captured["payload"]["stream"] is False
    # Native surface uses top-level "format", not OpenAI's response_format.
    assert captured["payload"]["format"] == "json"
    assert "response_format" not in captured["payload"]


def test_client_never_sends_num_ctx_for_openai_compatible(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        return _completion("ok")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # num_ctx is stored, but must never be sent on the OpenAI-compatible
    # surface — it cannot be set per request there.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        num_ctx=16384,
    )
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])

    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert "options" not in captured["payload"]
    assert "num_ctx" not in captured["payload"]


def test_client_ollama_without_num_ctx_uses_openai_surface(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        return _completion("ok")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # Ollama provider but no num_ctx configured: nothing changes — the request
    # keeps using the existing /v1/chat/completions path with no options block.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        num_ctx=None,
    )
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])

    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert "options" not in captured["payload"]


def test_client_refuses_over_budget_prompt_before_http(client, monkeypatch):
    import app.local_llm as local_llm

    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("over-budget prompt must not be sent")

    monkeypatch.setattr(local_llm, "_post_json", boom)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        context_window_tokens=128,
        reserved_output_tokens=32,
        max_input_tokens=20,
        allow_compression=False,
        allow_fallback=False,
        abort_on_over_budget=True,
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "x" * 1000}],
        task="ats_keywords",
    )

    assert result.ok is False
    assert "over budget" in (result.error or "")
    assert result.context is not None
    assert result.context["over_budget"] is True


# ---- task policy ------------------------------------------------------


def test_policy_defaults_resume_tailoring_to_claude_code(client):
    import app.local_llm as local_llm

    # Even with the subsystem enabled, the default per-task toggle keeps
    # resume tailoring on Claude Code.
    config = local_llm.LocalLLMConfig(enabled=True)
    assert local_llm.local_allowed_for_task("resume_tailoring", config) is False
    assert (
        local_llm.provider_for_task("resume_tailoring", config) == "claude_code"
    )


def test_policy_allows_low_risk_tasks_when_enabled(client):
    import app.local_llm as local_llm

    config = local_llm.LocalLLMConfig(enabled=True)
    for task in ("job_summary", "ats_keywords", "email_classification"):
        assert local_llm.local_allowed_for_task(task, config) is True
        assert local_llm.provider_for_task(task, config) == (
            "local_openai_compatible"
        )


def test_policy_blocks_low_risk_when_subsystem_disabled(client):
    import app.local_llm as local_llm

    config = local_llm.LocalLLMConfig(enabled=False)
    assert local_llm.local_allowed_for_task("ats_keywords", config) is False
    assert local_llm.provider_for_task("ats_keywords", config) == "claude_code"


def test_policy_blocks_resume_tailoring_unless_explicitly_enabled(client):
    import app.local_llm as local_llm

    explicit = local_llm.LocalLLMConfig(
        enabled=True,
        allowed_tasks={**local_llm.DEFAULT_ALLOWED_TASKS, "resume_tailoring": True},
    )
    assert local_llm.local_allowed_for_task("resume_tailoring", explicit) is True
    assert (
        local_llm.provider_for_task("resume_tailoring", explicit)
        == "local_openai_compatible"
    )


def test_policy_recruiter_review_is_never_local(client):
    import app.local_llm as local_llm

    # recruiter_review is not configurable; even if someone smuggles a True
    # toggle in, it stays on Claude Code.
    config = local_llm.LocalLLMConfig(
        enabled=True, allowed_tasks={"recruiter_review": True}
    )
    assert local_llm.local_allowed_for_task("recruiter_review", config) is False
    assert local_llm.provider_for_task("recruiter_review", config) == "claude_code"


# ---- schema validation -----------------------------------------------


def test_invalid_json_fails_validation_after_repair(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # Both the initial call and the repair retry return non-JSON.
        return _completion("this is not json")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(enabled=True)
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "give me json"}],
        required_fields=["suggestions"],
        task="resume_suggestions",
    )
    assert result.ok is True  # the HTTP call succeeded...
    assert result.schema_valid is False  # ...but the payload is not valid
    assert result.repaired is True


def test_valid_json_passes_validation(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _completion('{"suggestions": [{"target": "summary"}]}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(enabled=True)
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "go"}],
        required_fields=["suggestions"],
        task="resume_suggestions",
    )
    assert result.schema_valid is True
    assert result.repaired is False
    assert result.parsed == {"suggestions": [{"target": "summary"}]}


# ---- run metadata ----------------------------------------------------


def test_run_metadata_records_provider_and_model(client):
    import app.local_llm as local_llm

    # Default (disabled) → Claude Code, sentinel model.
    default_meta = local_llm.task_run_metadata("ats_keywords")
    assert default_meta["provider"] == "claude_code"
    assert default_meta["model"] == "claude-code"
    assert default_meta["local_llm_enabled"] is False

    # Enabled + low-risk task → local provider/model recorded.
    config = local_llm.LocalLLMConfig(enabled=True, model="mistral-small")
    local_meta = local_llm.task_run_metadata("ats_keywords", config)
    assert local_meta["provider"] == "local_openai_compatible"
    assert local_meta["model"] == "mistral-small"
    assert local_meta["local_llm_enabled"] is True

    # High-risk task stays on Claude Code regardless.
    high = local_llm.task_run_metadata("resume_tailoring", config)
    assert high["provider"] == "claude_code"


# ---- suggest-resume-edits endpoint -----------------------------------


def test_suggest_resume_edits_blocked_when_not_enabled(client):
    resp = client.post(
        "/llm/local/suggest-resume-edits",
        json={"job_description": "jd", "resume_excerpt": "resume"},
    )
    assert resp.status_code == 409, resp.text


def test_suggest_resume_edits_returns_suggestions(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _completion(
            '{"suggestions": [{"target": "summary", "suggestion": "tighten", '
            '"rationale": "matches jd"}]}'
        )

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "allowed_tasks": {
                **local_llm.DEFAULT_ALLOWED_TASKS,
                "resume_suggestions": True,
            },
        },
    ).raise_for_status()

    resp = client.post(
        "/llm/local/suggest-resume-edits",
        json={"job_description": "build things", "resume_excerpt": "did things"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["experimental"] is True
    assert body["provider"] == "local_openai_compatible"
    assert body["model"] == "llama3.1:8b"
    assert body["schema_valid"] is True
    assert len(body["suggestions"]) == 1
