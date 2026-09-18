"""End-to-end tests for the Text2SQL Agent.

Two layers:
  1. Tool-chain tests: schema → generate → validate → execute, calling the tools directly.
  2. Agent tests: the same questions through the ADK ``root_agent`` via a ``Runner``,
     asserting a non-empty natural-language answer comes back.

Both need a real Groq API key and a reachable PostgreSQL instance loaded with
db/schema.sql + db/seed.sql. They are skipped automatically otherwise.
"""

import asyncio
import os
import re
import time

import pytest

from agent.tools.schema_tool import get_schema


def _env_ready() -> tuple[bool, str]:
    key = os.getenv("GROQ_API_KEY", "")
    if not key or key.startswith("your_"):
        return False, "GROQ_API_KEY is unset or still a placeholder"
    if not os.getenv("DB_HOST"):
        return False, "DB_HOST is unset"
    schema = get_schema()
    if "error" in schema:
        return False, f"database unreachable: {schema['error'][:80]}"
    return True, ""


_READY, _REASON = _env_ready()
pytestmark = pytest.mark.skipif(not _READY, reason=f"skipping e2e tests — {_REASON}")


QUESTIONS = [
    "How many customers are there?",
    "List all products in the Electronics category.",
    "What is the total revenue from completed orders?",
    "Which customer placed the most orders?",
    "Show the top 3 most expensive products.",
]


@pytest.fixture(scope="module")
def schema():
    s = get_schema()
    assert "error" not in s, f"Schema fetch failed: {s}"
    return s


# ── Layer 1: tool chain ──────────────────────────────────────────────────────


@pytest.mark.parametrize("question", QUESTIONS)
def test_tool_chain(question, schema):
    from agent.tools.query_executor import execute_query
    from agent.tools.sql_generator import generate_sql
    from agent.tools.sql_validator import validate_sql

    sql = generate_sql(question, schema)
    assert isinstance(sql, str), f"generate_sql returned non-string: {sql}"
    assert sql != "UNANSWERABLE", f"Question was unanswerable: {question}"

    validation = validate_sql(sql)
    assert validation["valid"], f"SQL failed validation: {validation['reason']}\nSQL: {sql}"

    result = execute_query(sql)
    assert "error" not in result, f"Query execution failed: {result['error']}"
    assert "columns" in result
    assert result["row_count"] >= 0


# ── Layer 2: full ADK agent ──────────────────────────────────────────────────


def _ask_agent(question: str, max_retries: int = 6) -> str:
    """Run one question through root_agent and return the final text reply.

    Retries on Groq free-tier rate-limit errors (429 / TPM) with a backoff that
    honours the "try again in Xs" hint, so the suite is reliable on the free tier.
    """
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from agent.agent import root_agent

    async def _run() -> str:
        runner = InMemoryRunner(agent=root_agent, app_name="text2sql_e2e")
        session = await runner.session_service.create_session(
            app_name="text2sql_e2e", user_id="pytest"
        )
        message = types.Content(role="user", parts=[types.Part(text=question)])
        final = ""
        async for event in runner.run_async(
            user_id="pytest", session_id=session.id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                final = "".join(p.text or "" for p in event.content.parts)
        return final

    for attempt in range(max_retries):
        try:
            return asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001 — inspect message to classify
            msg = str(exc).lower()
            is_rate_limit = "rate_limit" in msg or "429" in msg or "too many requests" in msg
            # gpt-oss occasionally malforms the large schema JSON it must echo into
            # the generate_sql tool call — a transient, probabilistic model error.
            is_tool_glitch = "tool_use_failed" in msg or "parse tool call" in msg
            if (not is_rate_limit and not is_tool_glitch) or attempt == max_retries - 1:
                raise
            if is_rate_limit:
                match = re.search(r"try again in ([0-9.]+)s", str(exc))
                hinted = (float(match.group(1)) + 1.0) if match else 0.0
                # Floor the wait so the per-minute TPM window actually clears — the
                # short "try again in Xs" hint only covers a single request.
                wait = max(hinted, 15.0 * (attempt + 1))
            else:
                wait = 2.0  # transient tool-call glitch — just retry promptly
            time.sleep(wait)
    raise RuntimeError("unreachable")


# Two questions are enough to prove the ADK multi-turn tool loop end-to-end;
# keeping this small avoids exhausting the Groq free-tier TPM budget.
AGENT_QUESTIONS = QUESTIONS[:2]


@pytest.mark.parametrize("question", AGENT_QUESTIONS)
def test_agent_returns_answer(question):
    answer = _ask_agent(question)
    assert answer.strip(), f"Agent returned an empty answer for: {question}"
    # The answer must be prose, not a raw SQL statement
    assert not answer.strip().upper().startswith("SELECT"), f"Agent leaked raw SQL: {answer}"
