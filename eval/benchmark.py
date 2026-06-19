"""Benchmark runner for the Text2SQL Agent — Execution Accuracy (EX) metric.

For each test case:
  1. Run the agent's generate_sql() on the question.
  2. validate_sql() the result.
  3. execute_query() the agent SQL and the gold SQL.
  4. Compare result sets (order-independent, value-normalised) — this is EX.

EX = 1 if the agent's result set matches the gold result set, else 0.
Final score = percentage of cases where EX = 1.
"""
import json
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Minimum seconds to wait between generate_sql() calls to stay within Groq's RPM limit.
# Groq free tier: 30 RPM = 1 request per 2 seconds minimum. Set slightly higher for safety.
_INTER_REQUEST_DELAY = 3

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.schema_tool import get_schema
from agent.tools.sql_generator import generate_sql
from agent.tools.sql_validator import validate_sql
from agent.tools.query_executor import execute_query


# ── Result-set comparison ─────────────────────────────────────────────────────

def _normalize_value(v) -> str:
    """Convert a cell value to a canonical string for comparison.

    Numeric types (int, float, Decimal) are rounded to 4 decimal places so that
    AVG(total) = 521.5900000 compares equal to 521.59.
    Strings are lower-cased and stripped.
    None maps to the empty string.
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float, Decimal)):
        try:
            return f"{float(v):.4f}"
        except (ValueError, TypeError):
            pass
    # Try to parse strings that look numeric (e.g. values returned as strings by some drivers)
    try:
        return f"{float(Decimal(str(v))):.4f}"
    except (InvalidOperation, ValueError, TypeError):
        pass
    return str(v).strip().lower()


def _normalize_rows(rows: list[list]) -> list[tuple]:
    """Return a sorted list of normalised row tuples — order-independent comparison."""
    return sorted(tuple(_normalize_value(cell) for cell in row) for row in rows)


def results_match(actual: dict, expected: dict) -> bool:
    """Return True if both result dicts have identical normalised row sets (strict EX)."""
    if "error" in actual or "error" in expected:
        return False
    if len(actual["rows"]) != len(expected["rows"]):
        return False
    return _normalize_rows(actual["rows"]) == _normalize_rows(expected["rows"])


def results_match_lax(actual: dict, expected: dict) -> bool:
    """Return True if every gold row's values are a subset of the corresponding agent row (lax EX).

    Handles cases where the agent returns extra columns beyond what the gold SQL selects.
    Rows are matched by sorting on the first column before comparing.
    """
    if "error" in actual or "error" in expected:
        return False
    if len(actual["rows"]) != len(expected["rows"]):
        return False
    actual_sorted = sorted(actual["rows"], key=lambda r: str(r[0]))
    expected_sorted = sorted(expected["rows"], key=lambda r: str(r[0]))
    for agent_row, gold_row in zip(actual_sorted, expected_sorted):
        agent_vals = {_normalize_value(v) for v in agent_row}
        gold_vals = {_normalize_value(v) for v in gold_row}
        if not gold_vals.issubset(agent_vals):
            return False
    return True


# ── Per-case runner ───────────────────────────────────────────────────────────

def run_case(case: dict, schema: dict) -> dict:
    """Run one test case through the full pipeline and return a result dict."""
    qid = case["id"]
    question = case["question"]
    gold_sql = case["gold_sql"]

    # --- gold execution (ground truth) ---
    gold_result = execute_query(gold_sql)
    if "error" in gold_result:
        return {
            "id": qid, "question": question,
            "status": "gold_error", "detail": gold_result["error"],
            "ex": 0,
        }

    # --- agent pipeline ---
    agent_sql = generate_sql(question, schema)

    if isinstance(agent_sql, dict) and "error" in agent_sql:
        return {
            "id": qid, "question": question,
            "status": "generate_error", "detail": agent_sql["error"],
            "gold_sql": gold_sql, "agent_sql": None, "ex": 0,
        }

    if agent_sql == "UNANSWERABLE":
        return {
            "id": qid, "question": question,
            "status": "unanswerable",
            "gold_sql": gold_sql, "agent_sql": agent_sql, "ex": 0,
        }

    validation = validate_sql(agent_sql)
    if not validation["valid"]:
        return {
            "id": qid, "question": question,
            "status": "invalid_sql", "detail": validation["reason"],
            "gold_sql": gold_sql, "agent_sql": agent_sql, "ex": 0,
        }

    agent_result = execute_query(agent_sql)
    if "error" in agent_result:
        return {
            "id": qid, "question": question,
            "status": "execution_error", "detail": agent_result["error"],
            "gold_sql": gold_sql, "agent_sql": agent_sql, "ex": 0,
        }

    ex_strict = 1 if results_match(agent_result, gold_result) else 0
    ex_lax = 1 if (ex_strict or results_match_lax(agent_result, gold_result)) else 0

    if ex_strict:
        status = "match"
    elif ex_lax:
        status = "lax_match"
    else:
        status = "mismatch"

    return {
        "id": qid, "question": question,
        "status": status,
        "gold_sql": gold_sql,
        "agent_sql": agent_sql,
        "gold_rows": gold_result["row_count"],
        "agent_rows": agent_result["row_count"],
        "ex_strict": ex_strict,
        "ex_lax": ex_lax,
        "ex": ex_strict,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cases_path = Path(__file__).parent / "test_cases.json"
    with open(cases_path) as f:
        cases = json.load(f)

    print("Loading schema...")
    schema = get_schema()
    if "error" in schema:
        print(f"ERROR: failed to load schema — {schema['error']}")
        sys.exit(1)
    print(f"Schema loaded: {list(schema.keys())}\n")

    results = []
    ex_strict_total = 0
    ex_lax_total = 0

    for i, case in enumerate(cases):
        if i > 0:
            time.sleep(_INTER_REQUEST_DELAY)
        r = run_case(case, schema)
        results.append(r)
        ex_strict_total += r["ex_strict"]
        ex_lax_total += r["ex_lax"]

        status = r["status"]
        if status == "match":
            icon = "PASS"
        elif status == "lax_match":
            icon = "LAX "
        else:
            icon = "FAIL"

        agent_sql_preview = (r.get("agent_sql") or "")[:80].replace("\n", " ")
        print(f"  [{icon}] Q{r['id']:02d} [{status:<16}] {r['question'][:55]:<55}", flush=True)
        if r["ex_strict"] == 0 and r.get("agent_sql"):
            print(f"         agent : {agent_sql_preview}")
            print(f"         gold  : {r['gold_sql'][:80]}")
        if r.get("detail"):
            print(f"         error : {r['detail']}")

    total = len(cases)
    strict_pct = ex_strict_total / total * 100 if total > 0 else 0
    lax_pct = ex_lax_total / total * 100 if total > 0 else 0

    sep = "-" * 60
    print(f"\n{sep}")
    print(f"  Strict EX (exact columns):  {ex_strict_total}/{total} = {strict_pct:.1f}%")
    print(f"  Lax EX   (correct values):  {ex_lax_total}/{total} = {lax_pct:.1f}%")
    print(f"  Target (Week 5-6):          60.0%")
    print(f"  {'PASS' if strict_pct >= 60 else 'BELOW TARGET'}")
    print(f"{sep}\n")

    return results


if __name__ == "__main__":
    main()
