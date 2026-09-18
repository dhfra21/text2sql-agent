import os

import litellm
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from agent.litellm_compat import GroqReasoningClient
from agent.tools.query_executor import execute_query
from agent.tools.schema_tool import get_schema
from agent.tools.sql_generator import generate_sql
from agent.tools.sql_validator import validate_sql

# Groq model used by the orchestrating agent. Override with GROQ_MODEL in .env.
_GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Retry up to 3 times on rate-limit errors, waiting up to 10 s between attempts
litellm.num_retries = 3
litellm.retry_after = 5

_prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")

root_agent = Agent(
    model=LiteLlm(model=f"groq/{_GROQ_MODEL}", llm_client=GroqReasoningClient()),
    name="text2sql_agent",
    description="Translates natural language questions into SQL and returns human-readable answers.",
    instruction=open(_prompt_path, encoding="utf-8").read(),
    tools=[get_schema, generate_sql, validate_sql, execute_query],
)
