import os
import time
import certifi
from groq import Groq
from groq import RateLimitError
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

_PROMPT_TEMPLATE = """You are a SQL expert. Given the database schema below, write a single SQL SELECT query that answers the user's question.

Database schema:
{schema}

Rules:
- Return ONLY the SQL query, no explanation, no markdown code fences.
- Use only SELECT statements. Never use INSERT, UPDATE, DELETE, DROP, or any DDL.
- If the question cannot be answered from the schema, return exactly: UNANSWERABLE
- When the question asks to LIST or SHOW records (e.g. "list all orders", "show products"), select ALL columns of the main table.
- When the question asks for an AGGREGATE grouped by an entity (e.g. "total X per Y", "how many X per Y"), select ONLY the entity name and the aggregate value — no extra columns.
- When the question asks to IDENTIFY a single entity (e.g. "which customer placed the most orders"), return ONLY that entity's name — no extra columns.

User question: {question}

SQL:"""


def _format_schema(schema: dict) -> str:
    lines = []
    for table, columns in schema.items():
        col_defs = ", ".join(
            f"{c['column']} {c['type']}{'?' if c['nullable'] else ''}"
            for c in columns
        )
        lines.append(f"  {table}({col_defs})")
    return "\n".join(lines)


def generate_sql(question: str, schema: dict) -> str:
    """Generate a SQL SELECT statement from a natural language question and a schema dict.

    Uses Groq (llama-3.3-70b-versatile) to translate the question into SQL.
    Returns a single SQL SELECT statement with no markdown formatting.
    Returns the string "UNANSWERABLE" if the question cannot be answered from the schema.

    Args:
        question: The user's natural language question.
        schema: Schema dict as returned by get_schema().

    Returns:
        A SQL SELECT string, or "UNANSWERABLE", or {"error": str} on failure.
    """
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY environment variable is not set")

        prompt = _PROMPT_TEMPLATE.format(
            schema=_format_schema(schema),
            question=question,
        )

        client = Groq(api_key=api_key)
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                break
            except RateLimitError as e:
                if attempt == max_attempts - 1:
                    raise
                # Honour the Retry-After header if present, else exponential backoff
                wait = 10 * (2 ** attempt)  # 10s, 20s, 40s, 80s
                try:
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        wait = float(retry_after) + 1
                except Exception:
                    pass
                time.sleep(wait)
        sql = response.choices[0].message.content.strip()

        # Strip accidental markdown fences
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        return sql
    except Exception as e:
        return {"error": str(e)}
