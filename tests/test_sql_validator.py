"""Unit tests for validate_sql()."""
import pytest
from agent.tools.sql_validator import validate_sql


def test_valid_select():
    result = validate_sql("SELECT id, name FROM customers WHERE country = 'France'")
    assert result["valid"] is True


def test_valid_select_with_join():
    result = validate_sql(
        "SELECT c.name, COUNT(o.id) FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name"
    )
    assert result["valid"] is True


def test_blocked_drop():
    result = validate_sql("DROP TABLE customers")
    assert result["valid"] is False
    assert "DROP" in result["reason"]


def test_blocked_delete():
    result = validate_sql("DELETE FROM customers WHERE id = 1")
    assert result["valid"] is False
    assert "DELETE" in result["reason"]


def test_blocked_update():
    result = validate_sql("UPDATE customers SET name = 'hacked' WHERE id = 1")
    assert result["valid"] is False


def test_blocked_insert():
    result = validate_sql("INSERT INTO customers (name) VALUES ('hacker')")
    assert result["valid"] is False


def test_blocked_create():
    result = validate_sql("CREATE TABLE evil (id INT)")
    assert result["valid"] is False


def test_sql_injection_comment():
    result = validate_sql("SELECT * FROM customers -- DROP TABLE customers")
    assert result["valid"] is False
    assert "comment" in result["reason"].lower()


def test_sql_injection_multistatement():
    result = validate_sql("SELECT 1; DROP TABLE customers")
    assert result["valid"] is False
    assert "Multiple" in result["reason"]


def test_empty_sql():
    result = validate_sql("")
    assert result["valid"] is False


def test_non_select_statement():
    result = validate_sql("EXEC xp_cmdshell('dir')")
    assert result["valid"] is False
