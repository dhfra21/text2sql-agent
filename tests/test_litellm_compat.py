"""Unit tests for the Groq compat/resilience layer (reasoning strip + fallback)."""

import asyncio
from unittest.mock import patch

from google.adk.models.lite_llm import LiteLLMClient

from agent.litellm_compat import (
    GroqReasoningClient,
    _candidates,
    _is_failover_error,
    _strip_reasoning,
    groq_models,
)


def test_groq_models_order_and_dedup(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "m-primary")
    monkeypatch.setenv("GROQ_FALLBACK_MODELS", "m2, m3 , m-primary")
    assert groq_models() == ["m-primary", "m2", "m3"]


def test_candidates_keep_prefix(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_FALLBACK_MODELS", "openai/gpt-oss-20b")
    assert _candidates("groq/openai/gpt-oss-120b") == [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
    ]


def test_strip_reasoning_removes_output_only_fields():
    msgs = [
        {"role": "assistant", "content": "x", "reasoning_content": "trace"},
        {"role": "user", "content": "q"},
    ]
    out = _strip_reasoning(msgs)
    assert "reasoning_content" not in out[0]
    assert out[0]["content"] == "x"
    assert out[1] == {"role": "user", "content": "q"}


def test_is_failover_error_by_message():
    assert _is_failover_error(Exception("rate_limit_exceeded"))
    assert _is_failover_error(Exception("429 Too Many Requests"))
    assert not _is_failover_error(Exception("invalid_request_error: bad schema"))


def test_client_fails_over_to_next_model(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_FALLBACK_MODELS", "openai/gpt-oss-20b")
    calls = []

    async def fake_acompletion(self, model, messages, tools, **kwargs):
        calls.append(model)
        if len(calls) == 1:
            raise Exception("rate_limit reached for model")
        return "OK"

    with patch.object(LiteLLMClient, "acompletion", new=fake_acompletion):
        client = GroqReasoningClient()
        result = asyncio.run(
            client.acompletion(
                "groq/openai/gpt-oss-120b",
                [{"role": "user", "content": "hi"}],
                [],
            )
        )

    assert result == "OK"
    assert calls == ["groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b"]


def test_client_does_not_fail_over_on_client_error(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_FALLBACK_MODELS", "openai/gpt-oss-20b")
    calls = []

    async def fake_acompletion(self, model, messages, tools, **kwargs):
        calls.append(model)
        raise Exception("invalid_request_error: unsupported property")

    with patch.object(LiteLLMClient, "acompletion", new=fake_acompletion):
        client = GroqReasoningClient()
        try:
            asyncio.run(client.acompletion("groq/openai/gpt-oss-120b", [], []))
        except Exception:
            pass

    assert calls == ["groq/openai/gpt-oss-120b"]  # no fallback on a client error
