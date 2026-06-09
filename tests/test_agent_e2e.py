"""End-to-end tests for the Text2SQL Agent pipeline.

These tests run the full tool chain (schema → generate → validate → execute)
against a real test database. Set TEST_DB_* environment variables to point
to your test DB before running.
"""
import os
import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("DB_HOST"),
    reason="No DB_HOST set — skipping e2e tests (requires a running PostgreSQL instance)",
)


QUESTIONS = [
    "How many customers are there?",
    "List all products in the Electronics category.",
    "What is the total revenue from completed orders?",
    "Which customer placed the most orders?",
    "Show the top 3 most expensive products.",
]


@pytest.fixture(scope="module")
def schema():
    from agent.tools.schema_tool import get_schema
    s = get_schema()
    assert "error" not in s, f"Schema fetch failed: {s}"
    return s


@pytest.mark.parametrize("question", QUESTIONS)
def test_full_pipeline(question, schema):
    from agent.tools.sql_generator import generate_sql
    from agent.tools.sql_validator import validate_sql
    from agent.tools.query_executor import execute_query

    sql = generate_sql(question, schema)
    assert isinstance(sql, str), f"generate_sql returned non-string: {sql}"
    assert sql != "UNANSWERABLE", f"Question was unanswerable: {question}"

    validation = validate_sql(sql)
    assert validation["valid"], f"SQL failed validation: {validation['reason']}\nSQL: {sql}"

    result = execute_query(sql)
    assert "error" not in result, f"Query execution failed: {result['error']}"
    assert "columns" in result
    assert result["row_count"] >= 0
