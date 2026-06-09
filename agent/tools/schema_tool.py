import os
from typing import Optional
import sqlalchemy
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()


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
    return sqlalchemy.create_engine(url)


def get_schema(table_names: Optional[list[str]] = None) -> dict:
    """Return column metadata for the specified tables (or all tables if none given).

    Queries information_schema.columns to retrieve table/column structure.
    Returns a dict mapping table name to a list of column descriptors.

    Args:
        table_names: Optional list of table names to inspect. If None, returns all tables.

    Returns:
        {"table_name": [{"column": str, "type": str, "nullable": bool}]}
        or {"error": str} on failure.
    """
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            if table_names:
                query = text(
                    "SELECT table_name, column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tables) "
                    "ORDER BY table_name, ordinal_position"
                )
                rows = conn.execute(query, {"tables": table_names}).fetchall()
            else:
                query = text(
                    "SELECT table_name, column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "ORDER BY table_name, ordinal_position"
                )
                rows = conn.execute(query).fetchall()

        schema: dict[str, list] = {}
        for table, column, dtype, nullable in rows:
            schema.setdefault(table, []).append(
                {"column": column, "type": dtype, "nullable": nullable == "YES"}
            )
        return schema
    except Exception as e:
        return {"error": str(e)}
