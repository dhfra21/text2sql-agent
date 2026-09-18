"""Groq compatibility shim for reasoning models (e.g. openai/gpt-oss-120b).

Groq's reasoning models return an assistant message that carries a
``reasoning_content`` field. ADK stores that message in the conversation history
and replays it on the next turn, but Groq rejects an *incoming* assistant
message that contains ``reasoning_content`` (it is an output-only field):

    GroqException - 'messages.N' : for 'role:assistant' the following must be
    satisfied[property 'reasoning_content' is unsupported]

This breaks any multi-turn tool-calling loop. The fix is to drop reasoning
fields from messages before they are sent back to the API. Reasoning traces are
output-only, so removing them from the request is both safe and expected.
"""

from typing import Any

from google.adk.models.lite_llm import LiteLLMClient

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


class GroqReasoningClient(LiteLLMClient):
    """LiteLLMClient that strips reasoning fields from outgoing messages."""

    async def acompletion(self, model, messages, tools, **kwargs):
        return await super().acompletion(model, _strip_reasoning(messages), tools, **kwargs)

    def completion(self, model, messages, tools, stream=False, **kwargs):
        return super().completion(model, _strip_reasoning(messages), tools, stream=stream, **kwargs)
