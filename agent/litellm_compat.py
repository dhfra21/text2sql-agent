"""Groq compatibility + resilience layer for the Text2SQL agent.

Two problems this module solves:

1. Reasoning models (e.g. openai/gpt-oss-120b) return an assistant message that
   carries a ``reasoning_content`` field. ADK stores it and replays it on the next
   turn, but Groq rejects an *incoming* assistant message that contains
   ``reasoning_content`` (it is output-only), which breaks multi-turn tool loops.
   We strip reasoning fields from outgoing messages.

2. The Groq free tier is easily rate-limited (8000 TPM). We add automatic model
   fallback: when the primary model is rate-limited or returns a transient error,
   the request is retried on the next model in a configurable list.

Configuration (env vars, also honoured via Streamlit secrets):
    GROQ_MODEL            primary model (default: openai/gpt-oss-120b)
    GROQ_FALLBACK_MODELS  comma-separated fallbacks tried in order
                          (default: openai/gpt-oss-20b,qwen/qwen3.8-27b)
    GROQ_RATE_LIMIT_WAIT  seconds to wait before retrying the chain when every
                          model is rate-limited (default: 12)
    GROQ_MAX_ROUNDS       how many times to try the full model chain (default: 2)
"""

import asyncio
import os
import time
from typing import Any

from google.adk.models.lite_llm import LiteLLMClient

# ── Model-usage tracking (for the UI to show which model answered) ────────────

# Records the models that successfully served requests since the last reset.
# Best-effort and process-global — fine for a single-user Streamlit session.
_MODELS_USED: list[str] = []


def _bare(model: str) -> str:
    return model[len("groq/") :] if model.startswith("groq/") else model


def reset_models_used() -> None:
    """Clear the record — call this at the start of a turn."""
    _MODELS_USED.clear()


def record_model(model: str) -> None:
    """Record that ``model`` successfully served a request."""
    _MODELS_USED.append(_bare(model))


def models_used() -> list[str]:
    """Return the models that served requests since the last reset, in order."""
    return list(_MODELS_USED)


def _wait_seconds() -> float:
    try:
        return float(os.getenv("GROQ_RATE_LIMIT_WAIT", "12"))
    except ValueError:
        return 12.0


def _max_rounds() -> int:
    try:
        return max(1, int(os.getenv("GROQ_MAX_ROUNDS", "2")))
    except ValueError:
        return 2


# ── Reasoning-field stripping ─────────────────────────────────────────────────

# Output-only fields that must never be sent back in a request message.
_REASONING_KEYS = ("reasoning_content", "thinking_blocks", "reasoning")


def _strip_reasoning(messages: list[Any]) -> list[Any]:
    """Return a copy of ``messages`` with reasoning-only fields removed."""
    cleaned: list[Any] = []
    for msg in messages:
        if isinstance(msg, dict) and any(k in msg for k in _REASONING_KEYS):
            msg = {k: v for k, v in msg.items() if k not in _REASONING_KEYS}
        cleaned.append(msg)
    return cleaned


# ── Model list / fallback ─────────────────────────────────────────────────────

_DEFAULT_PRIMARY = "openai/gpt-oss-120b"
_DEFAULT_FALLBACKS = "openai/gpt-oss-20b,qwen/qwen3.8-27b"


def groq_models() -> list[str]:
    """Return the ordered, de-duplicated list of Groq models to try.

    Reads GROQ_MODEL (primary) and GROQ_FALLBACK_MODELS (comma-separated) at call
    time, so values injected at runtime (e.g. Streamlit secrets) are picked up.
    """
    primary = os.getenv("GROQ_MODEL", _DEFAULT_PRIMARY).strip()
    raw = os.getenv("GROQ_FALLBACK_MODELS", _DEFAULT_FALLBACKS)
    ordered = [primary] + [m.strip() for m in raw.split(",") if m.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for m in ordered:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


try:
    from litellm.exceptions import (
        InternalServerError,
        RateLimitError,
        ServiceUnavailableError,
        Timeout,
    )

    _FAILOVER_TYPES: tuple = (
        RateLimitError,
        ServiceUnavailableError,
        InternalServerError,
        Timeout,
    )
except Exception:  # pragma: no cover - litellm always present in practice
    _FAILOVER_TYPES = ()


def _is_failover_error(exc: Exception) -> bool:
    """True for transient errors worth retrying on a different model."""
    if _FAILOVER_TYPES and isinstance(exc, _FAILOVER_TYPES):
        return True
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "rate_limit",
            "rate limit",
            "429",
            "too many requests",
            "503",
            "service_unavailable",
            "overloaded",
            "internal server error",
        )
    )


def _candidates(model: str) -> list[str]:
    """Build the ordered list of fully-qualified models to try for a request.

    ``model`` is what ADK passes (e.g. ``groq/openai/gpt-oss-120b``); we keep its
    provider prefix and append the configured fallbacks with the same prefix.
    """
    prefix = "groq/" if model.startswith("groq/") else ""
    bare = model[len(prefix) :] if prefix else model
    models = groq_models()
    if bare not in models:
        models = [bare] + models
    else:
        models = [bare] + [m for m in models if m != bare]
    return [prefix + m for m in models]


class GroqReasoningClient(LiteLLMClient):
    """LiteLLMClient that strips reasoning fields and fails over between models."""

    async def acompletion(self, model, messages, tools, **kwargs):
        messages = _strip_reasoning(messages)
        candidates = _candidates(model)
        rounds = _max_rounds()
        last_exc: Exception | None = None
        for round_idx in range(rounds):
            if round_idx > 0:
                # Every model was rate-limited last round — wait for the
                # per-minute window to clear, then retry the whole chain.
                await asyncio.sleep(_wait_seconds())
            for candidate in candidates:
                try:
                    result = await super().acompletion(candidate, messages, tools, **kwargs)
                    record_model(candidate)
                    return result
                except Exception as exc:  # noqa: BLE001 — classify then re-raise
                    last_exc = exc
                    if not _is_failover_error(exc):
                        raise
        raise last_exc  # pragma: no cover

    def completion(self, model, messages, tools, stream=False, **kwargs):
        messages = _strip_reasoning(messages)
        candidates = _candidates(model)
        rounds = _max_rounds()
        last_exc: Exception | None = None
        for round_idx in range(rounds):
            if round_idx > 0:
                time.sleep(_wait_seconds())
            for candidate in candidates:
                try:
                    result = super().completion(candidate, messages, tools, stream=stream, **kwargs)
                    record_model(candidate)
                    return result
                except Exception as exc:  # noqa: BLE001 — classify then re-raise
                    last_exc = exc
                    if not _is_failover_error(exc):
                        raise
        raise last_exc  # pragma: no cover
