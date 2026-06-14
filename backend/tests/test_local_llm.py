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


def test_local_llm_max_output_tokens_round_trips_through_settings(client):
    # Unset on a fresh DB.
    assert client.get("/settings/local-llm").json()["max_output_tokens"] is None

    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "max_output_tokens": 512,
        },
    ).raise_for_status()

    body = client.get("/settings/local-llm").json()
    assert body["max_output_tokens"] == 512


def test_local_llm_max_output_tokens_rejects_non_positive(client):
    resp = client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "max_output_tokens": 0,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "max_output_tokens" in resp.json()["detail"]


def test_get_config_parses_and_validates_max_output_tokens(monkeypatch, tmp_path):
    import pytest

    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)

    # Unset on a fresh DB.
    assert local_llm.get_config().max_output_tokens is None

    # A positive int persists and reloads.
    config = local_llm.save_config(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        timeout_seconds=local_llm.DEFAULT_TIMEOUT_SECONDS,
        allowed_tasks={},
        max_output_tokens=256,
    )
    assert config.max_output_tokens == 256
    assert local_llm.get_config().max_output_tokens == 256

    # A non-positive value is rejected, independent of the context budget.
    with pytest.raises(local_llm.LocalLLMValidationError):
        local_llm.save_config(
            enabled=True,
            provider=local_llm.PROVIDER_OLLAMA,
            base_url="http://localhost:11434/v1",
            model="llama3.1:8b",
            timeout_seconds=local_llm.DEFAULT_TIMEOUT_SECONDS,
            allowed_tasks={},
            max_output_tokens=-1,
        )


def test_get_config_treats_invalid_stored_max_output_tokens_as_none(
    monkeypatch, tmp_path
):
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
                        "max_output_tokens": "not-an-int",
                    }
                ),
            )
        )
        session.commit()

    assert local_llm.get_config().max_output_tokens is None


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
    # A timeout/unreachable host classifies as endpoint_unavailable (task 136).
    assert body["error_kind"] == "endpoint_unavailable"


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
    assert body["error_kind"] == "endpoint_unavailable"


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
    # Structured calls prepend a JSON-only system instruction, then the
    # caller's messages (task 141).
    sent_messages = captured["payload"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "json" in sent_messages[0]["content"].lower()
    assert sent_messages[1:] == [{"role": "user", "content": "hi"}]
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    # Structured calls request a deterministic temperature of 0 (task 141).
    assert captured["payload"]["temperature"] == 0
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


def test_client_ollama_without_num_ctx_uses_native_chat(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        return _ollama_completion("ok")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # Ollama provider with no num_ctx configured still routes to the native
    # /api/chat surface — routing is by provider, not by num_ctx (task 129).
    # The options block is omitted because num_ctx is unset, but stream:false
    # is still sent so the server returns a single response.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        num_ctx=None,
    )
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])

    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["payload"]["stream"] is False
    assert "options" not in captured["payload"]


def test_client_sends_num_predict_for_ollama_native(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # An output cap with no num_ctx still produces a single options block
    # carrying num_predict (and no num_ctx).
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        max_output_tokens=256,
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert result.ok is True
    assert captured["url"] == "http://localhost:11434/api/chat"
    # The structured call also adds the deterministic temperature to the same
    # options block (task 141).
    assert captured["payload"]["options"] == {"num_predict": 256, "temperature": 0}


def test_client_sends_num_predict_and_num_ctx_in_single_options_block(
    client, monkeypatch
):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # A cap set alongside num_ctx yields one options block with both keys.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        num_ctx=16384,
        max_output_tokens=256,
    )
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])

    assert captured["payload"]["options"] == {
        "num_ctx": 16384,
        "num_predict": 256,
    }


def test_client_omits_num_predict_for_ollama_when_unset(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _ollama_completion("ok")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # No cap and no num_ctx → no options block at all.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        max_output_tokens=None,
    )
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])

    assert "options" not in captured["payload"]


def test_client_sends_max_tokens_for_openai_compatible(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _completion('{"ok": true}', model="qwen")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="qwen2.5-coder:14b",
        max_output_tokens=512,
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert result.ok is True
    # The OpenAI-compatible surface caps output via top-level max_tokens,
    # never via an options/num_predict block.
    assert captured["payload"]["max_tokens"] == 512
    assert "options" not in captured["payload"]
    assert "num_predict" not in captured["payload"]


def test_client_omits_max_tokens_for_openai_compatible_when_unset(
    client, monkeypatch
):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _completion("ok")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        max_output_tokens=None,
    )
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])

    assert "max_tokens" not in captured["payload"]


# ---- structured-call temperature + JSON-only instruction (task 141) --


def test_client_structured_call_sends_temperature_zero_ollama(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # A structured Ollama call with no num_ctx / num_predict still produces a
    # single options block carrying just the deterministic temperature.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert captured["payload"]["options"] == {"temperature": 0}
    assert captured["payload"]["options"]["temperature"] == (
        local_llm.DEFAULT_JSON_TEMPERATURE
    )
    # The JSON-only instruction is prepended as a leading system message.
    sent_messages = captured["payload"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "json" in sent_messages[0]["content"].lower()
    assert sent_messages[1:] == [{"role": "user", "content": "hi"}]


def test_client_structured_call_sends_temperature_zero_openai_compatible(
    client, monkeypatch
):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    # OpenAI-compatible sends temperature as a top-level field, never via an
    # options/num_predict block.
    assert captured["payload"]["temperature"] == local_llm.DEFAULT_JSON_TEMPERATURE
    assert "options" not in captured["payload"]


def test_client_non_structured_call_sends_no_temperature(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _completion("pong")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # A free-text (non-structured) OpenAI-compatible call must not force a
    # temperature and must not prepend a JSON-only system message.
    oai = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    local_llm.LocalLLMClient(oai).chat([{"role": "user", "content": "hi"}])
    assert "temperature" not in captured["payload"]
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hi"}]

    # Same for the Ollama-native provider: no options block at all (no
    # num_ctx / num_predict / temperature) for a free-text call.
    captured.clear()

    def fake_post_ollama(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _ollama_completion("pong")

    monkeypatch.setattr(local_llm, "_post_json", fake_post_ollama)

    ollama = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    local_llm.LocalLLMClient(ollama).chat([{"role": "user", "content": "hi"}])
    assert "options" not in captured["payload"]
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hi"}]


def test_test_connection_sends_no_temperature(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _completion("pong")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # test_connection is a non-structured probe: it must not force a temperature.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    local_llm.LocalLLMClient(config).test_connection()
    assert "temperature" not in captured["payload"]


def test_client_json_only_instruction_present_under_all_thinking_modes(
    client, monkeypatch
):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        if "/api/chat" in url:
            return _ollama_completion('{"ok": true}')
        return _completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # Every structured call carries the JSON-only instruction exactly once,
    # for both providers and under every thinking_mode (task 141).
    for provider in (
        local_llm.PROVIDER_OPENAI_COMPATIBLE,
        local_llm.PROVIDER_OLLAMA,
    ):
        for mode in local_llm.SUPPORTED_THINKING_MODES:
            captured.clear()
            config = local_llm.LocalLLMConfig(
                enabled=True,
                provider=provider,
                base_url="http://localhost:11434/v1",
                model="llama3.1:8b",
                thinking_mode=mode,
            )
            local_llm.LocalLLMClient(config).chat(
                [{"role": "user", "content": "hi"}],
                response_format={"type": "json_object"},
            )
            sent_messages = captured["payload"]["messages"]
            system_messages = [
                m for m in sent_messages if m["role"] == "system"
            ]
            # Present, and not duplicated by the no_thinking path.
            assert len(system_messages) == 1, (provider, mode, sent_messages)
            assert "json" in system_messages[0]["content"].lower()


# ---- structured / inline reasoning ("thinking") signal (task 142) ----


def _ollama_completion_with_thinking(
    content: str, thinking: str, model: str = "llama3.1:8b"
) -> dict:
    """An Ollama native ``/api/chat`` body that carries structured thinking."""
    return {
        "model": model,
        "message": {
            "role": "assistant",
            "content": content,
            "thinking": thinking,
        },
        "done": True,
    }


def test_chat_json_flags_structured_ollama_thinking(client, monkeypatch):
    import app.local_llm as local_llm

    secret = "let me reason step by step about the JSON the user asked for"

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _ollama_completion_with_thinking('{"ok": true}', secret)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "go"}],
        required_fields=["ok"],
        task="ats_keywords",
    )

    # The structured thinking is detected as a signal...
    assert result.thinking_returned is True
    assert result.schema_valid is True
    assert result.parsed == {"ok": True}
    # ...but the reasoning text never reaches the surfaced content or the
    # parsed JSON, so it is not persisted by default.
    assert secret not in (result.content or "")
    assert secret not in str(result.parsed)


def test_structured_thinking_never_surfaced_under_any_mode(client, monkeypatch):
    import app.local_llm as local_llm

    secret = "chain-of-thought reasoning that must never be persisted"

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _ollama_completion_with_thinking('{"ok": true}', secret)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # The structured thinking text must stay out of content/parsed for every
    # thinking_mode, and the signal must be set in each case.
    for mode in local_llm.SUPPORTED_THINKING_MODES:
        config = local_llm.LocalLLMConfig(
            enabled=True,
            provider=local_llm.PROVIDER_OLLAMA,
            base_url="http://localhost:11434/v1",
            model="llama3.1:8b",
            thinking_mode=mode,
        )
        result = local_llm.LocalLLMClient(config).chat_json(
            [{"role": "user", "content": "go"}],
            required_fields=["ok"],
            task="ats_keywords",
        )
        assert result.thinking_returned is True, mode
        assert secret not in (result.content or ""), mode
        assert secret not in str(result.parsed), mode


def test_chat_json_flags_inline_think_block(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # A reasoning model that wraps valid JSON in an inline <think> block.
        return _completion('<think>reasoning here</think>{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(enabled=True)
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "go"}],
        required_fields=["ok"],
        task="ats_keywords",
    )

    # A stripped inline <think> block reports thinking_returned too, and the
    # reasoning never lands in the parsed JSON.
    assert result.thinking_returned is True
    assert result.schema_valid is True
    assert result.parsed == {"ok": True}
    assert "reasoning here" not in str(result.parsed)


def test_chat_json_no_thinking_reports_false(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # No structured thinking and no inline <think> block.
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "go"}],
        required_fields=["ok"],
        task="ats_keywords",
    )

    # A response with no reasoning parses exactly as before, with the flag off.
    assert result.thinking_returned is False
    assert result.schema_valid is True
    assert result.parsed == {"ok": True}


def test_llm_call_result_thinking_returned_defaults_false():
    import app.local_llm as local_llm

    result = local_llm.LLMCallResult(
        ok=True, provider="local_ollama", model="llama3.1:8b"
    )
    assert result.thinking_returned is False


# ---- Ollama generation metrics / tokens-per-second (task 143) --------


def _ollama_completion_with_metrics(
    content: str,
    *,
    prompt_eval_count=42,
    eval_count=100,
    total_duration=2_500_000_000,
    eval_duration=2_000_000_000,
    model: str = "llama3.1:8b",
) -> dict:
    """An Ollama native ``/api/chat`` body carrying generation telemetry.

    The nanosecond durations and token counts mirror what Ollama reports;
    individual fields can be dropped (pass ``None``) to simulate a partial body.
    """
    body: dict = {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": True,
    }
    for key, value in (
        ("prompt_eval_count", prompt_eval_count),
        ("eval_count", eval_count),
        ("total_duration", total_duration),
        ("eval_duration", eval_duration),
    ):
        if value is not None:
            body[key] = value
    return body


def test_extract_generation_metrics_full():
    import app.local_llm as local_llm

    metrics = local_llm.extract_generation_metrics(
        _ollama_completion_with_metrics('{"ok": true}')
    )
    assert metrics is not None
    assert metrics.prompt_eval_count == 42
    assert metrics.eval_count == 100
    # Nanosecond durations are converted to milliseconds.
    assert metrics.total_duration_ms == 2500
    assert metrics.eval_duration_ms == 2000
    # tokens/sec = eval_count / (eval_duration / 1e9) = 100 / 2.0 = 50.0
    assert metrics.tokens_per_second == 50.0


def test_extract_generation_metrics_partial():
    import app.local_llm as local_llm

    # Only the token counts are present (no durations): the counts survive and
    # the missing durations / derived tokens/sec degrade to None.
    metrics = local_llm.extract_generation_metrics(
        _ollama_completion_with_metrics(
            '{"ok": true}', total_duration=None, eval_duration=None
        )
    )
    assert metrics is not None
    assert metrics.prompt_eval_count == 42
    assert metrics.eval_count == 100
    assert metrics.total_duration_ms is None
    assert metrics.eval_duration_ms is None
    assert metrics.tokens_per_second is None


def test_extract_generation_metrics_zero_duration_is_none_not_divide_error():
    import app.local_llm as local_llm

    # A zero eval_duration must not raise; tokens/sec degrades to None while
    # the (zero) eval_duration_ms is still reported.
    metrics = local_llm.extract_generation_metrics(
        _ollama_completion_with_metrics('{"ok": true}', eval_duration=0)
    )
    assert metrics is not None
    assert metrics.eval_duration_ms == 0
    assert metrics.tokens_per_second is None


def test_extract_generation_metrics_missing_returns_none():
    import app.local_llm as local_llm

    # A response with none of the metric fields (e.g. an OpenAI-compatible
    # body) yields no metrics holder at all.
    assert local_llm.extract_generation_metrics(_completion("pong")) is None
    assert local_llm.extract_generation_metrics(_ollama_completion("pong")) is None
    # Never raises on a non-dict body either.
    assert local_llm.extract_generation_metrics("not-a-dict") is None


def test_extract_generation_metrics_malformed_fields_degrade_to_none():
    import app.local_llm as local_llm

    # Garbage values are coerced to None per field rather than raising; a
    # present-but-malformed field still counts as "metrics present".
    metrics = local_llm.extract_generation_metrics(
        {
            "message": {"role": "assistant", "content": "{}"},
            "prompt_eval_count": "not-an-int",
            "eval_count": 100,
            "eval_duration": "bogus",
            "total_duration": 2_500_000_000,
        }
    )
    assert metrics is not None
    assert metrics.prompt_eval_count is None
    assert metrics.eval_count == 100
    assert metrics.total_duration_ms == 2500
    assert metrics.eval_duration_ms is None
    # eval_duration was unusable, so tokens/sec cannot be derived.
    assert metrics.tokens_per_second is None


def test_chat_populates_generation_metrics_for_ollama(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _ollama_completion_with_metrics('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert result.ok is True
    assert result.generation_metrics is not None
    assert result.generation_metrics.eval_count == 100
    assert result.generation_metrics.prompt_eval_count == 42
    assert result.generation_metrics.tokens_per_second == 50.0


def test_chat_leaves_generation_metrics_none_for_openai_compatible(
    client, monkeypatch
):
    import app.local_llm as local_llm

    # Even if an OpenAI-compatible server somehow echoed Ollama-style fields,
    # the client never populates metrics for that provider.
    def fake_post(url, payload, *, headers=None, timeout=60.0):
        body = _completion('{"ok": true}')
        body["eval_count"] = 100
        body["eval_duration"] = 2_000_000_000
        return body

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    assert result.ok is True
    assert result.generation_metrics is None


def test_log_call_appends_tokens_per_second_and_output_tokens(caplog):
    import logging

    import app.local_llm as local_llm

    result = local_llm.LLMCallResult(
        ok=True,
        provider="local_ollama",
        model="llama3.1:8b",
        task="ats_keywords",
        schema_valid=True,
        generation_metrics=local_llm.GenerationMetrics(
            prompt_eval_count=42,
            eval_count=100,
            total_duration_ms=2500,
            eval_duration_ms=2000,
            tokens_per_second=50.0,
        ),
    )
    with caplog.at_level(logging.INFO, logger="app.local_llm"):
        local_llm._log_call(result)

    line = caplog.records[-1].getMessage()
    # The existing prefix is preserved verbatim...
    assert line.startswith(
        "LLM provider: local_ollama | Model: llama3.1:8b | Task: ats_keywords | "
        "Schema validation: passed | Fallback used: no"
    )
    # ...and the metrics are appended.
    assert "Tokens/sec: 50.0" in line
    assert "Output tokens: 100" in line


def test_log_call_without_metrics_keeps_existing_format(caplog):
    import logging

    import app.local_llm as local_llm

    result = local_llm.LLMCallResult(
        ok=True,
        provider="local_openai_compatible",
        model="llama3.1:8b",
        task="ats_keywords",
        schema_valid=True,
    )
    with caplog.at_level(logging.INFO, logger="app.local_llm"):
        local_llm._log_call(result)

    line = caplog.records[-1].getMessage()
    # No generation metrics → the original single-line format is unchanged.
    assert line == (
        "LLM provider: local_openai_compatible | Model: llama3.1:8b | "
        "Task: ats_keywords | Schema validation: passed | Fallback used: no"
    )
    assert "Tokens/sec" not in line
    assert "Output tokens" not in line


def test_client_ollama_bare_base_url_uses_native_chat(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        return _ollama_completion("ok")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # The reported bug: an Ollama base URL with no /v1 suffix used to fall
    # through to /chat/completions and 404. It must now hit /api/chat, and
    # must never call /chat/completions.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://100.104.129.123:11434",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}]
    )

    assert result.ok is True
    assert captured["url"] == "http://100.104.129.123:11434/api/chat"
    assert not captured["url"].endswith("/chat/completions")


def test_client_ollama_never_calls_chat_completions(client, monkeypatch):
    import app.local_llm as local_llm

    seen_urls: list[str] = []

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        seen_urls.append(url)
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # Across every Ollama configuration (with/without num_ctx, with/without a
    # JSON response_format, bare or /v1 base URL), no request may ever target
    # the OpenAI-compatible /chat/completions path.
    for num_ctx in (None, 16384):
        for base_url in (
            "http://localhost:11434",
            "http://localhost:11434/v1",
        ):
            config = local_llm.LocalLLMConfig(
                enabled=True,
                provider=local_llm.PROVIDER_OLLAMA,
                base_url=base_url,
                model="llama3.1:8b",
                num_ctx=num_ctx,
            )
            client_obj = local_llm.LocalLLMClient(config)
            client_obj.chat([{"role": "user", "content": "hi"}])
            client_obj.chat(
                [{"role": "user", "content": "hi"}],
                response_format={"type": "json_object"},
            )

    assert seen_urls, "expected at least one request"
    assert all(url.endswith("/api/chat") for url in seen_urls), seen_urls
    assert all("/chat/completions" not in url for url in seen_urls), seen_urls


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


def test_client_http_error_reports_attempted_url(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # An Ollama 404 (the reported bug) must name the endpoint that was hit so
    # a misconfigured base URL is obvious from the error alone.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://100.104.129.123:11434",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}]
    )

    assert result.ok is False
    assert "404" in (result.error or "")
    assert "http://100.104.129.123:11434/api/chat" in (result.error or "")


def test_client_connection_error_reports_attempted_url(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://100.104.129.123:11434",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}]
    )

    assert result.ok is False
    assert "http://100.104.129.123:11434/api/chat" in (result.error or "")


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


# ---- server-context detection (task 127) -----------------------------


def _ollama_show(context_length: int, arch: str = "llama") -> dict:
    """A minimal Ollama native ``/api/show`` response body."""
    return {
        "model_info": {
            "general.architecture": arch,
            f"{arch}.context_length": context_length,
            f"{arch}.embedding_length": 4096,
        },
        "details": {"family": arch},
    }


def test_detect_server_context_ollama_success(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["url"] = url
        captured["payload"] = payload
        return _ollama_show(131072)

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.detect_server_context(config)

    # The /v1 suffix is stripped to reach the native metadata endpoint.
    assert captured["url"] == "http://localhost:11434/api/show"
    assert captured["payload"] == {"model": "llama3.1:8b"}
    assert result.context_verified is True
    assert result.server_reported_context_tokens == 131072
    assert "131072" in result.note


def test_detect_server_context_ollama_failure_degrades(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    # Must never raise; degrades to unverified with an explanatory note.
    result = local_llm.detect_server_context(config)
    assert result.context_verified is False
    assert result.server_reported_context_tokens is None
    assert result.note


def test_detect_server_context_ollama_missing_context_length_degrades(
    client, monkeypatch
):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # A well-formed response that simply lacks any context_length key.
        return {"model_info": {"general.architecture": "llama"}, "details": {}}

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.detect_server_context(config)
    assert result.context_verified is False
    assert result.server_reported_context_tokens is None


def test_detect_server_context_openai_compatible_cannot_verify(client, monkeypatch):
    import app.local_llm as local_llm

    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("openai-compatible detection must not hit the network")

    monkeypatch.setattr(local_llm, "_post_json", boom)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:8000/v1",
        model="mistral-small",
    )
    result = local_llm.detect_server_context(config)
    assert result.context_verified is False
    assert result.server_reported_context_tokens is None
    assert "cannot verify" in result.note.lower()


def test_test_connection_reports_server_context_for_ollama(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        if url.endswith("/api/show"):
            return _ollama_show(8192)
        return _completion("pong")

    def fake_get(url, *, headers=None, timeout=60.0):
        # The Ollama connection test lists installed models before probing.
        return _ollama_tags("llama3.1:8b")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    monkeypatch.setattr(local_llm, "_get_json", fake_get)

    resp = client.post(
        "/llm/local/test-connection",
        json={
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    # A successful Ollama test reports the installed models and a clean kind.
    assert body["error_kind"] == "none"
    assert body["installed_models"] == ["llama3.1:8b"]
    assert body["context_verified"] is True
    assert body["server_reported_context_tokens"] == 8192
    assert body["context_warning"] is None
    assert "server-reported context: 8192 tokens" in body["message"].lower()


def test_test_connection_warns_when_context_unverified(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # The chat test succeeds; detection is not attempted for the
        # OpenAI-compatible provider, so the context stays unverified.
        return _completion("pong")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    resp = client.post(
        "/llm/local/test-connection",
        json={
            "provider": "openai_compatible",
            "base_url": "http://localhost:8000/v1",
            "model": "mistral-small",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["context_verified"] is False
    assert body["server_reported_context_tokens"] is None
    assert body["context_warning"]
    assert "cannot verify" in body["context_warning"].lower()


def test_test_connection_accepts_num_ctx_override(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        if url.endswith("/api/show"):
            return _ollama_show(16384)
        captured["chat_url"] = url
        captured["chat_payload"] = payload
        return _ollama_completion("pong")

    def fake_get(url, *, headers=None, timeout=60.0):
        return _ollama_tags("llama3.1:8b")

    monkeypatch.setattr(local_llm, "_post_json", fake_post)
    monkeypatch.setattr(local_llm, "_get_json", fake_get)

    resp = client.post(
        "/llm/local/test-connection",
        json={
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
            "num_ctx": 16384,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    # The num_ctx override routed the chat test to the native surface and was
    # sent on the request, mirroring a saved Ollama num_ctx.
    assert captured["chat_url"] == "http://localhost:11434/api/chat"
    assert captured["chat_payload"]["options"]["num_ctx"] == 16384
    assert body["context_verified"] is True
    assert body["server_reported_context_tokens"] == 16384


# ---- installed-model detection (task 135) ----------------------------


def _ollama_tags(*names: str) -> dict:
    """A minimal Ollama native ``/api/tags`` response body."""
    return {
        "models": [
            {"name": name, "model": name, "size": 123, "digest": "sha256:abc"}
            for name in names
        ]
    }


def test_list_models_ollama_returns_installed_names(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_get(url, *, headers=None, timeout=60.0):
        captured["url"] = url
        return _ollama_tags("llama3.1:8b", "qwen2.5-coder:14b")

    monkeypatch.setattr(local_llm, "_get_json", fake_get)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).list_models()

    # The /v1 suffix is stripped to reach the native tags endpoint.
    assert captured["url"] == "http://localhost:11434/api/tags"
    assert result.ok is True
    assert result.models == ["llama3.1:8b", "qwen2.5-coder:14b"]
    assert result.error is None
    assert result.error_kind is None


def test_list_models_openai_compatible_is_unsupported_without_network(
    client, monkeypatch
):
    import app.local_llm as local_llm

    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("openai-compatible model listing must not hit network")

    monkeypatch.setattr(local_llm, "_get_json", boom)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:8000/v1",
        model="mistral-small",
    )
    result = local_llm.LocalLLMClient(config).list_models()

    assert result.ok is False
    assert result.models == []
    assert result.error_kind == local_llm.MODEL_LIST_UNSUPPORTED
    assert "ollama" in (result.error or "").lower()


def test_list_models_classifies_transport_failures(client, monkeypatch):
    import app.local_llm as local_llm

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434",
        model="llama3.1:8b",
    )

    # A connection failure (URLError) classifies as endpoint_unavailable.
    def unreachable(url, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(local_llm, "_get_json", unreachable)
    unavailable = local_llm.LocalLLMClient(config).list_models()
    assert unavailable.ok is False
    assert unavailable.error_kind == local_llm.ENDPOINT_ERROR_UNAVAILABLE

    # A reachable host returning 404 classifies as bad_url — a distinct kind.
    def not_found(url, *, headers=None, timeout=60.0):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(local_llm, "_get_json", not_found)
    bad_url = local_llm.LocalLLMClient(config).list_models()
    assert bad_url.ok is False
    assert bad_url.error_kind == local_llm.ENDPOINT_ERROR_BAD_URL

    # The two failure modes are clearly distinguishable.
    assert unavailable.error_kind != bad_url.error_kind


def test_classify_endpoint_error_kinds():
    import app.local_llm as local_llm

    base = "http://host:11434/api/tags"

    kind, msg = local_llm.classify_endpoint_error(
        urllib.error.URLError("Connection refused"), base_url=base
    )
    assert kind == local_llm.ENDPOINT_ERROR_UNAVAILABLE
    assert base in msg

    kind, _ = local_llm.classify_endpoint_error(
        urllib.error.HTTPError(base, 404, "Not Found", hdrs=None, fp=None),
        base_url=base,
    )
    assert kind == local_llm.ENDPOINT_ERROR_BAD_URL

    kind, _ = local_llm.classify_endpoint_error(
        urllib.error.HTTPError(base, 405, "Method Not Allowed", hdrs=None, fp=None),
        base_url=base,
    )
    assert kind == local_llm.ENDPOINT_ERROR_BAD_URL

    # An HTTP 500 (reachable, but a server error) is unexpected, not bad_url.
    kind, _ = local_llm.classify_endpoint_error(
        urllib.error.HTTPError(base, 500, "Server Error", hdrs=None, fp=None),
        base_url=base,
    )
    assert kind == local_llm.ENDPOINT_ERROR_UNEXPECTED

    kind, _ = local_llm.classify_endpoint_error(
        ValueError("boom"), base_url=base
    )
    assert kind == local_llm.ENDPOINT_ERROR_UNEXPECTED


def test_models_endpoint_lists_ollama_models_with_overrides(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_get(url, *, headers=None, timeout=60.0):
        captured["url"] = url
        return _ollama_tags("llama3.1:8b", "phi3:mini")

    monkeypatch.setattr(local_llm, "_get_json", fake_get)

    # The persisted config defaults to the OpenAI-compatible provider; the
    # query overrides switch the listing to the Ollama-native surface for an
    # unsaved edit.
    resp = client.get(
        "/llm/local/models",
        params={"provider": "ollama", "base_url": "http://localhost:11434/v1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["provider"] == "local_ollama"
    assert body["models"] == ["llama3.1:8b", "phi3:mini"]
    assert body["error"] is None
    assert body["error_kind"] is None
    assert captured["url"] == "http://localhost:11434/api/tags"


def test_models_endpoint_reports_unsupported_for_openai_compatible(client):
    # With no overrides the persisted default is the OpenAI-compatible
    # provider, which cannot list models — reported, not raised.
    resp = client.get("/llm/local/models")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["provider"] == "local_openai_compatible"
    assert body["models"] == []
    assert body["error_kind"] == "unsupported"


# ---- classified connection diagnosis (task 136) ----------------------


def test_test_connection_reports_model_not_installed(client, monkeypatch):
    import app.local_llm as local_llm

    def fake_get(url, *, headers=None, timeout=60.0):
        # The server is reachable and reports two installed models, neither of
        # which is the configured one.
        return _ollama_tags("llama3.1:8b", "qwen2.5-coder:14b")

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        # The chat probe must never run for a missing model — it would surface
        # a raw 404. Only best-effort context detection's /api/show may be hit.
        if url.endswith("/api/show"):
            return _ollama_show(8192)
        raise AssertionError(
            f"chat probe must not run for a missing model: {url}"
        )

    monkeypatch.setattr(local_llm, "_get_json", fake_get)
    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    resp = client.post(
        "/llm/local/test-connection",
        json={
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:70b",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["error_kind"] == "model_not_installed"
    # The message names the missing model and the installed list, with no raw
    # HTTP 404 leaking through.
    assert "llama3.1:70b" in body["message"]
    assert "llama3.1:8b" in body["message"]
    assert "404" not in body["message"]
    assert body["installed_models"] == ["llama3.1:8b", "qwen2.5-coder:14b"]


def test_test_connection_classifies_endpoint_unavailable_for_ollama(
    client, monkeypatch
):
    import app.local_llm as local_llm

    def unreachable(url, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")

    def post_unreachable(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(local_llm, "_get_json", unreachable)
    monkeypatch.setattr(local_llm, "_post_json", post_unreachable)

    resp = client.post(
        "/llm/local/test-connection",
        json={
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3.1:8b",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["error_kind"] == "endpoint_unavailable"
    assert body["installed_models"] == []


def test_test_connection_classifies_bad_url_for_ollama(client, monkeypatch):
    import app.local_llm as local_llm

    def not_found(url, *, headers=None, timeout=60.0):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    def post_not_found(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(local_llm, "_get_json", not_found)
    monkeypatch.setattr(local_llm, "_post_json", post_not_found)

    # A reachable host whose tags endpoint 404s means the URL/surface is wrong,
    # not that the server is down — a distinct kind from endpoint_unavailable.
    resp = client.post(
        "/llm/local/test-connection",
        json={
            "provider": "ollama",
            "base_url": "http://localhost:11434/wrong",
            "model": "llama3.1:8b",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["error_kind"] == "bad_url"


# ---- per-call timeout (task 130) -------------------------------------


def test_ollama_effective_timeout_defaults_to_180(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["timeout"] = timeout
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # Ollama provider with no explicitly configured timeout: the cold-model
    # aware 180s default is the per-call bound actually passed to the request.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434",
        model="llama3.1:8b",
    )
    assert config.timeout_explicitly_set is False
    assert config.effective_timeout_seconds == 180
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])
    assert captured["timeout"] == 180


def test_openai_compatible_effective_timeout_defaults_to_60(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["timeout"] = timeout
        return _completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # OpenAI-compatible provider keeps the 60s default when no explicit timeout
    # is set — the longer Ollama default is provider-specific.
    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )
    assert config.timeout_explicitly_set is False
    assert config.effective_timeout_seconds == 60
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])
    assert captured["timeout"] == 60


def test_explicit_timeout_wins_over_ollama_default(monkeypatch, tmp_path):
    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["timeout"] = timeout
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    # A user-configured timeout is honoured verbatim, even on Ollama where the
    # default would otherwise be 180s. The stored value persists as an explicit
    # choice and is the per-call bound passed to the request.
    config = local_llm.save_config(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434",
        model="llama3.1:8b",
        timeout_seconds=45,
        allowed_tasks={},
    )
    assert config.timeout_explicitly_set is True
    assert config.effective_timeout_seconds == 45
    assert local_llm.get_config().effective_timeout_seconds == 45
    local_llm.LocalLLMClient(config).chat([{"role": "user", "content": "hi"}])
    assert captured["timeout"] == 45


def test_save_config_rejects_invalid_timeout(monkeypatch, tmp_path):
    import pytest

    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)

    # Non-positive timeouts are rejected.
    for bad in (0, -5):
        with pytest.raises(local_llm.LocalLLMValidationError):
            local_llm.save_config(
                enabled=True,
                provider=local_llm.PROVIDER_OLLAMA,
                base_url="http://localhost:11434",
                model="llama3.1:8b",
                timeout_seconds=bad,
                allowed_tasks={},
            )

    # A non-integer timeout is rejected too.
    with pytest.raises(local_llm.LocalLLMValidationError):
        local_llm.save_config(
            enabled=True,
            provider=local_llm.PROVIDER_OLLAMA,
            base_url="http://localhost:11434",
            model="llama3.1:8b",
            timeout_seconds="not-an-int",
            allowed_tasks={},
        )


def test_effective_timeout_round_trips_through_settings(client):
    # Ollama with no explicit timeout: the stored value is null and the
    # effective value in force is the 180s Ollama default.
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3.1:8b",
        },
    ).raise_for_status()
    body = client.get("/settings/local-llm").json()
    assert body["timeout_seconds"] is None
    assert body["effective_timeout_seconds"] == 180

    # An explicit timeout wins and round-trips through both fields.
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3.1:8b",
            "timeout_seconds": 90,
        },
    ).raise_for_status()
    body = client.get("/settings/local-llm").json()
    assert body["timeout_seconds"] == 90
    assert body["effective_timeout_seconds"] == 90


def test_openai_compatible_effective_timeout_round_trips(client):
    # OpenAI-compatible provider with no explicit timeout: effective stays 60.
    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "model": "llama3.1:8b",
        },
    ).raise_for_status()
    body = client.get("/settings/local-llm").json()
    assert body["timeout_seconds"] is None
    assert body["effective_timeout_seconds"] == 60


# ---- reasoning ("thinking") controls (task 131) ----------------------


def test_strip_thinking_removes_reasoning_before_json():
    import app.local_llm as local_llm

    # Reasoning wrapped in <think> precedes the JSON object; only the JSON
    # (whitespace-trimmed) should survive.
    content = (
        "<think>The user wants ATS keywords. Let me reason about it "
        "carefully.</think>\n\n{\"keywords\": [\"python\"]}"
    )
    assert local_llm.strip_thinking(content) == '{"keywords": ["python"]}'


def test_strip_thinking_handles_case_and_multiline_and_thinking_variant():
    import app.local_llm as local_llm

    # Case-insensitive tag matching, multi-line spans, and the <thinking>
    # variant are all removed.
    content = (
        "<THINK>line one\nline two</think>"
        "<Thinking>more\nreasoning</THINKING>"
        '  {"ok": true}  '
    )
    assert local_llm.strip_thinking(content) == '{"ok": true}'


def test_strip_thinking_leaves_content_without_markers_unchanged():
    import app.local_llm as local_llm

    # No thinking markers: content is returned unchanged (bar whitespace trim).
    assert local_llm.strip_thinking('{"ok": true}') == '{"ok": true}'
    # None passes through as None; empty stays empty.
    assert local_llm.strip_thinking(None) is None
    assert local_llm.strip_thinking("") == ""


def test_chat_json_recovers_json_wrapped_in_think_block(client, monkeypatch):
    import app.local_llm as local_llm

    # A reasoning model wraps valid JSON in a <think> block. Under the default
    # strip mode the JSON is recovered and validated instead of falling back.
    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _completion(
            "<think>Let me work out the suggestions step by step.</think>\n"
            '{"suggestions": [{"target": "summary"}]}'
        )

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(enabled=True)
    assert config.thinking_mode == local_llm.THINKING_MODE_STRIP
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "go"}],
        required_fields=["suggestions"],
        task="resume_suggestions",
    )
    assert result.schema_valid is True
    assert result.repaired is False
    assert result.parsed == {"suggestions": [{"target": "summary"}]}


def test_chat_json_hide_thinking_strips_content_surfaced(client, monkeypatch):
    import app.local_llm as local_llm

    # Under hide_thinking the reasoning is also removed from the surfaced
    # ``content`` so it never reaches persisted artifacts or logs.
    def fake_post(url, payload, *, headers=None, timeout=60.0):
        return _completion(
            "<think>secret reasoning</think>{\"suggestions\": []}"
        )

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True, thinking_mode=local_llm.THINKING_MODE_HIDE
    )
    result = local_llm.LocalLLMClient(config).chat_json(
        [{"role": "user", "content": "go"}],
        required_fields=["suggestions"],
        task="resume_suggestions",
    )
    assert result.schema_valid is True
    assert result.parsed == {"suggestions": []}
    assert "secret reasoning" not in (result.content or "")
    assert result.content == '{"suggestions": []}'


def test_ollama_no_thinking_sends_native_disable_option(client, monkeypatch):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _ollama_completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434",
        model="llama3.1:8b",
        thinking_mode=local_llm.THINKING_MODE_NO_THINKING,
    )
    local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    # Native Ollama disable-reasoning flag is carried on the request.
    assert captured["payload"]["think"] is False


def test_openai_compatible_no_thinking_never_sends_reasoning_flag(
    client, monkeypatch
):
    import app.local_llm as local_llm

    captured: dict = {}

    def fake_post(url, payload, *, headers=None, timeout=60.0):
        captured["payload"] = payload
        return _completion('{"ok": true}')

    monkeypatch.setattr(local_llm, "_post_json", fake_post)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        thinking_mode=local_llm.THINKING_MODE_NO_THINKING,
    )
    local_llm.LocalLLMClient(config).chat(
        [{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
    )

    # No provider-specific reasoning flag is ever sent to an OpenAI-compatible
    # endpoint; instead the instruction is reinforced via a system message.
    assert "think" not in captured["payload"]
    messages = captured["payload"]["messages"]
    assert messages[0]["role"] == "system"
    assert "reasoning" in messages[0]["content"].lower()
    assert messages[-1] == {"role": "user", "content": "hi"}


def test_thinking_mode_round_trips_through_settings(client):
    # Default on a fresh DB is the safe strip mode.
    body = client.get("/settings/local-llm").json()
    assert body["thinking_mode"] == "strip_thinking"

    client.put(
        "/settings/local-llm",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3.1:8b",
            "thinking_mode": "no_thinking",
        },
    ).raise_for_status()
    assert client.get("/settings/local-llm").json()["thinking_mode"] == (
        "no_thinking"
    )


def test_save_config_rejects_unknown_thinking_mode(monkeypatch, tmp_path):
    import pytest

    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)

    with pytest.raises(local_llm.LocalLLMValidationError):
        local_llm.save_config(
            enabled=True,
            provider=local_llm.PROVIDER_OLLAMA,
            base_url="http://localhost:11434",
            model="llama3.1:8b",
            allowed_tasks={},
            thinking_mode="ponder-deeply",
        )


def test_get_config_defaults_unknown_thinking_mode(monkeypatch, tmp_path):
    import json

    local_llm = _load_local_llm_with_temp_db(monkeypatch, tmp_path)
    from app.db import SessionLocal
    from app.models import AppSetting

    # A missing thinking_mode defaults to the safe strip mode.
    assert local_llm.get_config().thinking_mode == local_llm.THINKING_MODE_STRIP

    # A garbage stored value also coerces to the safe default on load.
    with SessionLocal() as session:
        session.add(
            AppSetting(
                key=local_llm.LOCAL_LLM_SETTING_KEY,
                value=json.dumps(
                    {
                        "enabled": True,
                        "provider": "ollama",
                        "base_url": "http://localhost:11434",
                        "model": "llama3.1:8b",
                        "thinking_mode": "nonsense",
                    }
                ),
            )
        )
        session.commit()

    assert local_llm.get_config().thinking_mode == local_llm.THINKING_MODE_STRIP


# ---- explicit model pull (task 137) ----------------------------------


def _pull_stream(*lines: dict):
    """A fake ``_post_json_stream`` returning the given NDJSON progress lines.

    Mirrors the streaming network boundary's signature so it can be dropped in
    via monkeypatch without a live Ollama server.
    """

    def fake_stream(url, payload, *, headers=None, timeout=60.0):
        fake_stream.url = url
        fake_stream.payload = payload
        for line in lines:
            yield line

    return fake_stream


def test_pull_model_ollama_streams_progress(client, monkeypatch):
    import app.local_llm as local_llm

    fake = _pull_stream(
        {"status": "pulling manifest"},
        {
            "status": "downloading",
            "completed": 50,
            "total": 100,
            "digest": "sha256:abc",
        },
        {"status": "downloading", "completed": 100, "total": 100},
        {"status": "success"},
    )
    monkeypatch.setattr(local_llm, "_post_json_stream", fake)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )

    seen: list = []
    result = local_llm.LocalLLMClient(config).pull_model(
        "qwen2.5-coder:14b", on_progress=seen.append
    )

    # The /v1 suffix is stripped to reach the native pull endpoint, and the
    # requested model name (not the configured one) is what is pulled.
    assert fake.url == "http://localhost:11434/api/pull"
    assert fake.payload["name"] == "qwen2.5-coder:14b"
    assert result.ok is True
    assert result.error is None
    assert result.error_kind is None
    # Every streamed line is surfaced as a structured update, both collected
    # and pushed to the on_progress callback.
    assert [u.status for u in result.updates] == [
        "pulling manifest",
        "downloading",
        "downloading",
        "success",
    ]
    assert seen == result.updates
    assert result.updates[1].completed == 50
    assert result.updates[1].total == 100
    assert result.updates[1].digest == "sha256:abc"
    # The disk/VRAM advisory is always carried on the result.
    assert "disk" in result.advisory.lower()
    assert "vram" in result.advisory.lower()


def test_pull_model_openai_compatible_is_unsupported_without_network(
    client, monkeypatch
):
    import app.local_llm as local_llm

    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("openai-compatible pull must not hit the network")

    monkeypatch.setattr(local_llm, "_post_json_stream", boom)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OPENAI_COMPATIBLE,
        base_url="http://localhost:8000/v1",
        model="mistral-small",
    )
    result = local_llm.LocalLLMClient(config).pull_model("mistral-small")

    assert result.ok is False
    assert result.error_kind == local_llm.PULL_UNSUPPORTED
    assert "ollama" in (result.error or "").lower()
    assert result.updates == []


def test_pull_model_surfaces_server_reported_error(client, monkeypatch):
    import app.local_llm as local_llm

    # Ollama emits an ``error`` line when, e.g., the model name does not exist.
    fake = _pull_stream(
        {"status": "pulling manifest"},
        {"error": "pull model manifest: file does not exist"},
    )
    monkeypatch.setattr(local_llm, "_post_json_stream", fake)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).pull_model("nope:404")

    assert result.ok is False
    assert "does not exist" in (result.error or "")
    # The progress already streamed before the error is still preserved.
    assert result.updates[0].status == "pulling manifest"


def test_pull_model_classifies_transport_failure(client, monkeypatch):
    import app.local_llm as local_llm

    def unreachable(url, payload, *, headers=None, timeout=60.0):
        raise urllib.error.URLError("Connection refused")
        yield  # pragma: no cover - marks this function a generator

    monkeypatch.setattr(local_llm, "_post_json_stream", unreachable)

    config = local_llm.LocalLLMConfig(
        enabled=True,
        provider=local_llm.PROVIDER_OLLAMA,
        base_url="http://localhost:11434",
        model="llama3.1:8b",
    )
    result = local_llm.LocalLLMClient(config).pull_model("llama3.1:8b")

    assert result.ok is False
    assert result.error_kind == local_llm.ENDPOINT_ERROR_UNAVAILABLE


def test_pull_endpoint_streams_ndjson_progress(client, monkeypatch):
    import json

    import app.local_llm as local_llm

    fake = _pull_stream(
        {"status": "pulling manifest"},
        {"status": "downloading", "completed": 100, "total": 100},
        {"status": "success"},
    )
    monkeypatch.setattr(local_llm, "_post_json_stream", fake)

    resp = client.post(
        "/llm/local/pull",
        json={
            "model": "qwen2.5-coder:14b",
            "provider": "ollama",
            "base_url": "http://localhost:11434/v1",
        },
    )
    assert resp.status_code == 200, resp.text
    # The disk/VRAM advisory is also surfaced on the response header.
    assert "disk" in resp.headers["x-pull-advisory"].lower()

    events = [
        json.loads(line) for line in resp.text.splitlines() if line.strip()
    ]
    # First line is the advisory, last line is the result, progress in between.
    assert events[0]["type"] == "advisory"
    assert events[0]["model"] == "qwen2.5-coder:14b"
    assert "disk" in events[0]["message"].lower()
    statuses = [e["status"] for e in events if e["type"] == "progress"]
    assert statuses == ["pulling manifest", "downloading", "success"]
    assert events[-1] == {
        "type": "result",
        "ok": True,
        "error": None,
        "error_kind": None,
    }
    assert fake.url == "http://localhost:11434/api/pull"


def test_pull_endpoint_requires_model_name(client):
    # No model name in the body — refused by request validation, never reaching
    # a "pull whatever is configured" path.
    resp = client.post("/llm/local/pull", json={"provider": "ollama"})
    assert resp.status_code == 422, resp.text


def test_pull_endpoint_refuses_non_ollama_provider(client, monkeypatch):
    import app.local_llm as local_llm

    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("a refused pull must not hit the network")

    monkeypatch.setattr(local_llm, "_post_json_stream", boom)

    # The persisted default provider is OpenAI-compatible, which has no pull
    # endpoint — refused with a clear 409 before any network call.
    resp = client.post("/llm/local/pull", json={"model": "llama3.1:8b"})
    assert resp.status_code == 409, resp.text
    assert "ollama" in resp.json()["detail"].lower()


def test_pull_model_is_only_called_from_the_pull_endpoint():
    """Pulling must never be a side effect of tailoring/preflight/startup.

    The only caller of the pull capability is the dedicated pull endpoint, so
    the tailoring/preflight/startup modules must not reference ``pull_model``
    or its streaming primitive (task 137 acceptance: grep evidence).
    """
    import pathlib

    import app

    app_dir = pathlib.Path(app.__file__).resolve().parent
    forbidden = [
        app_dir / "preflight.py",
        app_dir / "claude_worker.py",
        app_dir / "run_directory.py",
        app_dir / "main.py",
    ]
    for path in forbidden:
        text = path.read_text()
        assert "pull_model" not in text, f"{path} must not invoke pull_model"
        assert "iter_pull_model" not in text, f"{path} must not invoke a pull"

    # The router *is* the sole caller.
    router_text = (app_dir / "routers" / "local_llm.py").read_text()
    assert "iter_pull_model" in router_text
