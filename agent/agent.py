import os
from google.adk.agents import Agent
from agent.tools.schema_tool import get_schema
from agent.tools.sql_generator import generate_sql
from agent.tools.sql_validator import validate_sql
from agent.tools.query_executor import execute_query

_prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")

root_agent = Agent(
    model="gemini-2.0-flash",
    name="text2sql_agent",
    description="Translates natural language questions into SQL and returns human-readable answers.",
    instruction=open(_prompt_path).read(),
    tools=[get_schema, generate_sql, validate_sql, execute_query],
)
