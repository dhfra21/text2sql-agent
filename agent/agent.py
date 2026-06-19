import os
import litellm
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from agent.tools.schema_tool import get_schema
from agent.tools.sql_generator import generate_sql
from agent.tools.sql_validator import validate_sql
from agent.tools.query_executor import execute_query

# Retry up to 3 times on rate-limit errors, waiting up to 10 s between attempts
litellm.num_retries = 3
litellm.retry_after = 5

_prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")

root_agent = Agent(
    model=LiteLlm(model="groq/llama-3.3-70b-versatile"),
    name="text2sql_agent",
    description="Translates natural language questions into SQL and returns human-readable answers.",
    instruction=open(_prompt_path).read(),
    tools=[get_schema, generate_sql, validate_sql, execute_query],
)
