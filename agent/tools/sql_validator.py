import re
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DDL, DML


_BLOCKED_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "TRUNCATE", "CREATE", "EXEC", "EXECUTE",
}


def _contains_blocked_keyword(statement: Statement) -> str | None:
    for token in statement.flatten():
        if token.ttype in (Keyword, DDL, DML):
            upper = token.value.upper()
            if upper in _BLOCKED_KEYWORDS:
                return upper
    return None


def validate_sql(sql: str) -> dict:
    """Check whether a SQL string is safe to execute.

    Blocks any statement that is not a pure SELECT: DDL, DML mutations,
    multi-statement inputs, and common SQL-injection patterns.

    Args:
        sql: The SQL string to validate.

    Returns:
        {"valid": bool, "reason": str}
    """
    if not sql or not sql.strip():
        return {"valid": False, "reason": "Empty SQL string"}

    # Block comment-based injection patterns
    if "--" in sql or "/*" in sql or "*/" in sql:
        return {"valid": False, "reason": "SQL comment detected — possible injection attempt"}

    # Block multiple statements (semicolon not at the very end)
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        return {"valid": False, "reason": "Multiple statements detected — only single SELECT allowed"}

    parsed = sqlparse.parse(sql)
    if not parsed or not parsed[0].tokens:
        return {"valid": False, "reason": "Could not parse SQL"}

    if len(parsed) > 1:
        return {"valid": False, "reason": "Multiple statements detected — only single SELECT allowed"}

    statement = parsed[0]

    blocked = _contains_blocked_keyword(statement)
    if blocked:
        return {"valid": False, "reason": f"Blocked keyword detected: {blocked}"}

    # Require the statement to start with SELECT
    first_meaningful = next(
        (t for t in statement.flatten() if t.ttype not in (sqlparse.tokens.Whitespace, sqlparse.tokens.Newline, sqlparse.tokens.Comment.Single, sqlparse.tokens.Comment.Multiline)),
        None,
    )
    if first_meaningful is None or first_meaningful.value.upper() != "SELECT":
        return {"valid": False, "reason": "Only SELECT statements are allowed"}

    return {"valid": True, "reason": "OK"}
