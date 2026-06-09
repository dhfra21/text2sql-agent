"""Unit tests for get_schema()."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_engine(monkeypatch):
    """Fixture that replaces the DB engine with a mock returning fake schema rows."""
    fake_rows = [
        ("customers", "id",         "integer",          "NO"),
        ("customers", "name",       "character varying","NO"),
        ("customers", "email",      "character varying","NO"),
        ("customers", "country",    "character varying","YES"),
        ("products",  "id",         "integer",          "NO"),
        ("products",  "name",       "character varying","NO"),
        ("products",  "price",      "numeric",          "NO"),
    ]

    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchall.return_value = fake_rows

    mock_eng = MagicMock()
    mock_eng.connect.return_value = mock_conn

    monkeypatch.setattr("agent.tools.schema_tool._get_engine", lambda: mock_eng)
    return mock_eng


def test_get_schema_returns_all_tables(mock_engine):
    from agent.tools.schema_tool import get_schema
    result = get_schema()
    assert "customers" in result
    assert "products" in result


def test_get_schema_column_structure(mock_engine):
    from agent.tools.schema_tool import get_schema
    result = get_schema()
    col = result["customers"][0]
    assert "column" in col
    assert "type" in col
    assert "nullable" in col


def test_get_schema_nullable_flag(mock_engine):
    from agent.tools.schema_tool import get_schema
    result = get_schema()
    id_col = next(c for c in result["customers"] if c["column"] == "id")
    country_col = next(c for c in result["customers"] if c["column"] == "country")
    assert id_col["nullable"] is False
    assert country_col["nullable"] is True


def test_get_schema_returns_error_on_db_failure(monkeypatch):
    from agent.tools.schema_tool import get_schema
    monkeypatch.setattr("agent.tools.schema_tool._get_engine", lambda: (_ for _ in ()).throw(Exception("connection refused")))
    result = get_schema()
    assert "error" in result
