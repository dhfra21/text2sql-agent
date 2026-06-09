import os
import sqlalchemy
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

_ROW_LIMIT = 500


def _get_engine() -> sqlalchemy.engine.Engine:
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    missing = [k for k, v in {"DB_HOST": host, "DB_NAME": name, "DB_USER": user, "DB_PASSWORD": password}.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    return sqlalchemy.create_engine(url, execution_options={"isolation_level": "AUTOCOMMIT"})


def execute_query(sql: str) -> dict:
    """Execute a validated SELECT query and return the result set.

    Connects with a read-only role and enforces a hard row limit of 500.
    Never call this function without first calling validate_sql().

    Args:
        sql: A validated SELECT SQL string.

    Returns:
        {"columns": list[str], "rows": list[list], "row_count": int}
        or {"error": str} on connection/execution failure.
    """
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            # Enforce row limit by wrapping query
            limited_sql = f"SELECT * FROM ({sql.rstrip(';')}) AS _q LIMIT {_ROW_LIMIT}"
            result = conn.execute(text(limited_sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]

        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": str(e)}
