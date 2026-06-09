import os
import certifi
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


def _call_groq(prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def _call_gemini(prompt: str) -> str:
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY environment variable is not set")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text.strip()


def generate_sql(question: str, schema: dict) -> str:
    """Generate a SQL SELECT statement from a natural language question and a schema dict.

    Uses Groq (llama-3.3-70b-versatile) if GROQ_API_KEY is set, otherwise falls back
    to Gemini 2.0 Flash. Returns a single SQL SELECT statement with no markdown formatting.
    Returns the string "UNANSWERABLE" if the question cannot be answered from the schema.

    Args:
        question: The user's natural language question.
        schema: Schema dict as returned by get_schema().

    Returns:
        A SQL SELECT string, or "UNANSWERABLE", or {"error": str} on failure.
    """
    try:
        prompt = _PROMPT_TEMPLATE.format(
            schema=_format_schema(schema),
            question=question,
        )

        if os.getenv("GROQ_API_KEY"):
            sql = _call_groq(prompt)
        else:
            sql = _call_gemini(prompt)

        # Strip accidental markdown fences
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        return sql
    except Exception as e:
        return {"error": str(e)}
