import os

import sqlalchemy
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

_ROW_LIMIT = 500


def _get_engine() -> sqlalchemy.engine.Engine:
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    missing = [
        k
        for k, v in {
            "DB_HOST": host,
            "DB_NAME": name,
            "DB_USER": user,
            "DB_PASSWORD": password,
        }.items()
        if not v
    ]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    # default_transaction_read_only makes every statement on this connection read-only
    # at the server level, regardless of the role's privileges — a second safety net
    # behind validate_sql().
    connect_args = {"options": "-c default_transaction_read_only=on"}
    # Managed Postgres (Neon, Supabase, Cloud SQL) requires SSL. Set DB_SSLMODE=require
    # in the cloud; leave it unset for local development.
    sslmode = os.getenv("DB_SSLMODE")
    if sslmode:
        connect_args["sslmode"] = sslmode
    return sqlalchemy.create_engine(
        url,
        execution_options={"isolation_level": "AUTOCOMMIT"},
        connect_args=connect_args,
    )


def execute_query(sql: str) -> dict:
    """Execute a validated SELECT query and return the result set.

    Connects with a read-only session (default_transaction_read_only=on) and
    enforces a hard row limit of 500.
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
