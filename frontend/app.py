"""Streamlit frontend for the Text2SQL Agent.

A chat UI that drives the full ADK ``root_agent``: the agent runs its own
schema -> generate -> validate -> execute pipeline and replies in plain English.
The generated SQL and the raw result table are surfaced in a collapsible
section under each answer, extracted from the agent's tool-call events.

Run with:
    streamlit run frontend/app.py
"""

import asyncio
import os
import sys
from pathlib import Path

import certifi
import streamlit as st
from dotenv import load_dotenv

# Make the project root importable when run as `streamlit run frontend/app.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

# On Streamlit Community Cloud there is no .env — configuration is provided via
# st.secrets. Mirror those values into the environment so the agent tools
# (which read os.getenv) pick them up. Must run before agent.agent is imported.
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

st.set_page_config(page_title="Text2SQL Agent", page_icon="🔍", layout="centered")

APP_NAME = "text2sql_frontend"
USER_ID = "streamlit_user"


# ── Agent bootstrap (cached across reruns) ────────────────────────────────────


@st.cache_resource(show_spinner=False)
def _get_runner():
    """Create the ADK runner once and reuse it across reruns (keeps memory)."""
    from google.adk.runners import InMemoryRunner

    from agent.agent import root_agent

    return InMemoryRunner(agent=root_agent, app_name=APP_NAME)


def _ensure_session(runner) -> str:
    """Create an ADK session on first use and remember its id."""
    if "adk_session_id" not in st.session_state:
        session = asyncio.run(
            runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
        )
        st.session_state.adk_session_id = session.id
    return st.session_state.adk_session_id


# ── One agent turn ────────────────────────────────────────────────────────────


def _unwrap(response):
    """Tool responses come back as {'result': value} for non-dict returns."""
    if isinstance(response, dict) and set(response.keys()) == {"result"}:
        return response["result"]
    return response


async def _run_turn(runner, session_id: str, question: str) -> dict:
    """Send one question to the agent; collect the answer + tool artifacts."""
    from google.genai import types

    message = types.Content(role="user", parts=[types.Part(text=question)])
    answer, sql, exec_result = "", None, None

    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                fr = getattr(part, "function_response", None)
                if fr is not None:
                    if fr.name == "generate_sql":
                        sql = _unwrap(fr.response)
                    elif fr.name == "execute_query":
                        exec_result = _unwrap(fr.response)
        if event.is_final_response() and event.content and event.content.parts:
            answer = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))

    return {"answer": answer, "sql": sql, "result": exec_result}


def _render_model_badge(models):
    """Right-hand badge showing which model(s) answered, flagging any fallback."""
    from agent.litellm_compat import groq_models

    if not models:
        return
    seen = list(dict.fromkeys(models))  # de-dupe, preserve order
    primary = groq_models()[0]
    fell_back = any(m != primary for m in seen)
    if fell_back:
        st.caption("🔀 fallback")
    else:
        st.caption("⚙️ model")
    for m in seen:
        tag = "" if m == primary else " ↩"
        st.markdown(f"<small><code>{m}</code>{tag}</small>", unsafe_allow_html=True)


def _render_assistant(content, sql, result, models):
    """Render one assistant turn: answer + details on the left, model on the right."""
    col_answer, col_model = st.columns([4, 1])
    with col_answer:
        st.markdown(content)
        _render_details(sql, result)
    with col_model:
        _render_model_badge(models)


def _render_details(sql, result):
    """Show the generated SQL and result table in a collapsible section."""
    if not sql and not result:
        return
    with st.expander("🔍 SQL & data"):
        if isinstance(sql, str) and sql:
            st.caption("Generated SQL")
            st.code(sql, language="sql")
        if isinstance(result, dict):
            if "error" in result:
                st.error(result["error"])
            elif result.get("columns"):
                st.caption(f"Result — {result.get('row_count', len(result['rows']))} row(s)")
                st.dataframe(
                    {
                        col: [row[i] for row in result["rows"]]
                        for i, col in enumerate(result["columns"])
                    },
                    use_container_width=True,
                )


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("🔍 Text2SQL Agent")
st.caption("Ask questions about the database in plain English.")

with st.sidebar:
    st.subheader("Status")
    key = os.getenv("GROQ_API_KEY", "")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    st.write("**Model:**", f"`{model}`")
    st.write("**Groq key:**", "✅ set" if key and not key.startswith("your_") else "❌ missing")

    db_ok = False
    try:
        from agent.tools.schema_tool import get_schema

        _schema = get_schema()
        db_ok = "error" not in _schema
        st.write("**Database:**", "✅ connected" if db_ok else "❌ unreachable")
        if db_ok:
            st.write("**Tables:**", ", ".join(f"`{t}`" for t in _schema))
        else:
            st.caption(_schema["error"][:200])
    except Exception as exc:  # noqa: BLE001
        st.write("**Database:**", "❌ error")
        st.caption(str(exc)[:200])

    if st.button("Clear conversation"):
        st.session_state.pop("messages", None)
        st.session_state.pop("adk_session_id", None)
        st.rerun()

    st.divider()
    st.caption("Try: *How many customers are there?* · *Total revenue from completed orders?*")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Replay history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            _render_assistant(msg["content"], msg.get("sql"), msg.get("result"), msg.get("models"))
        else:
            st.markdown(msg["content"])

# New question
question = st.chat_input("Ask a question about the data…")
if question:
    from agent.litellm_compat import models_used, reset_models_used

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        reset_models_used()
        with st.spinner("Thinking…"):
            try:
                runner = _get_runner()
                session_id = _ensure_session(runner)
                turn = asyncio.run(_run_turn(runner, session_id, question))
            except Exception as exc:  # noqa: BLE001
                turn = {"answer": f"⚠️ Something went wrong: {exc}", "sql": None, "result": None}
        turn_models = models_used()

        answer = turn["answer"] or "_(no answer returned)_"
        _render_assistant(answer, turn["sql"], turn["result"], turn_models)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "sql": turn["sql"],
            "result": turn["result"],
            "models": turn_models,
        }
    )
