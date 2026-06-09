"""Unit tests for execute_query()."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_engine(monkeypatch):
    """Fixture that returns fake query results without hitting a real DB."""
    fake_keys = ["id", "name", "country"]
    fake_rows = [(1, "Alice", "France"), (2, "Bob", "USA")]

    mock_result = MagicMock()
    mock_result.keys.return_value = fake_keys
    mock_result.fetchall.return_value = fake_rows

    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value = mock_result

    mock_eng = MagicMock()
    mock_eng.connect.return_value = mock_conn

    monkeypatch.setattr("agent.tools.query_executor._get_engine", lambda: mock_eng)
    return mock_eng


def test_execute_returns_columns_and_rows(mock_engine):
    from agent.tools.query_executor import execute_query
    result = execute_query("SELECT id, name, country FROM customers")
    assert result["columns"] == ["id", "name", "country"]
    assert len(result["rows"]) == 2
    assert result["row_count"] == 2


def test_execute_returns_error_on_db_failure(monkeypatch):
    from agent.tools.query_executor import execute_query
    monkeypatch.setattr("agent.tools.query_executor._get_engine", lambda: (_ for _ in ()).throw(Exception("timeout")))
    result = execute_query("SELECT 1")
    assert "error" in result


def test_execute_wraps_query_with_limit(mock_engine):
    from agent.tools.query_executor import execute_query
    execute_query("SELECT * FROM customers")
    call_args = mock_engine.connect.return_value.execute.call_args
    executed_sql = str(call_args[0][0])
    assert "LIMIT" in executed_sql.upper()
