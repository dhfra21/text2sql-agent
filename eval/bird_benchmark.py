"""BIRD benchmark evaluation runner for the Text2SQL agent.

Measures Execution Accuracy (EX) against the official BIRD dev set using SQLite.

Download BIRD from: https://bird-bench.github.io/
Expected directory layout after extracting:
  <bird_path>/
    dev.json
    dev_databases/
      california_schools/
        california_schools.sqlite
      card_games/
        card_games.sqlite
      ...  (11 databases total)

Usage examples:
  # 50 random questions across all databases
  python eval/bird_benchmark.py --bird-path C:/data/BIRD/dev

  # 50 questions from one database only
  python eval/bird_benchmark.py --bird-path C:/data/BIRD/dev --db california_schools

  # Filter by difficulty, save results
  python eval/bird_benchmark.py --bird-path C:/data/BIRD/dev --n 30 --difficulty simple --output results.json
"""
import argparse
import json
import random
import sqlite3
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.sql_generator import generate_sql
from agent.tools.sql_validator import validate_sql

_ROW_LIMIT = 500
_DEFAULT_DELAY = 3  # seconds between Groq API calls (30 RPM free-tier safety)


# ── SQLite helpers ────────────────────────────────────────────────────────────

def _db_path(bird_path: Path, db_id: str) -> Path:
    # Standard layout: <bird_path>/dev_databases/<db_id>/<db_id>.sqlite
    standard = bird_path / "dev_databases" / db_id / f"{db_id}.sqlite"
    if standard.exists():
        return standard
    # Nested layout (e.g. dev_20240627): <bird_path>/dev_databases/dev_databases/<db_id>/<db_id>.sqlite
    nested = bird_path / "dev_databases" / "dev_databases" / db_id / f"{db_id}.sqlite"
    return nested


def get_schema_sqlite(db_path: Path) -> dict:
    """Return column metadata for all tables in a SQLite database.

    Uses PRAGMA table_info — no information_schema needed.
    Returns {"table": [{"column": str, "type": str, "nullable": bool}]}
    """
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = [r[0] for r in cur.fetchall()]
    schema: dict = {}
    for table in tables:
        cur.execute(f'PRAGMA table_info("{table}")')
        schema[table] = [
            {"column": col[1], "type": col[2] or "TEXT", "nullable": not col[3]}
            for col in cur.fetchall()
        ]
    conn.close()
    return schema


def execute_sqlite(db_path: Path, sql: str, trusted: bool = False) -> dict:
    """Execute a SELECT query against a SQLite database and return the result set.

    For agent SQL (trusted=False) the query is wrapped in a LIMIT subquery with
    a fallback to direct execution when the wrapper fails on complex queries.
    For gold SQL (trusted=True) the query runs directly; rows are capped via fetchmany.

    Returns {"columns": list, "rows": list[list], "row_count": int}
    or      {"error": str} on failure.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        if trusted:
            cur.execute(sql.rstrip(";"))
        else:
            try:
                cur.execute(f"SELECT * FROM ({sql.rstrip(';')}) AS _q LIMIT {_ROW_LIMIT}")
            except sqlite3.Error:
                cur.execute(sql.rstrip(";"))

        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchmany(_ROW_LIMIT)]
        conn.close()
        return {"columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"error": str(e)}


# ── EX comparison ─────────────────────────────────────────────────────────────

def _norm(v) -> str:
    """Canonical string for a single cell value."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float, Decimal)):
        try:
            return f"{float(v):.4f}"
        except Exception:
            pass
    try:
        return f"{float(Decimal(str(v))):.4f}"
    except (InvalidOperation, ValueError, TypeError):
        pass
    return str(v).strip().lower()


def _norm_rows(rows: list) -> frozenset:
    """Return a frozenset of normalised row tuples.

    Using a frozenset (not a sorted list) matches the official BIRD EX metric,
    which compares result sets as deduplicated, order-independent collections.
    This correctly handles cases where the agent omits DISTINCT but returns the
    same unique values as the gold SQL.
    """
    return frozenset(tuple(_norm(c) for c in row) for row in rows)


def ex_match(actual: dict, expected: dict) -> bool:
    """Return True if both result dicts have identical normalised result sets (BIRD EX)."""
    if "error" in actual or "error" in expected:
        return False
    return _norm_rows(actual["rows"]) == _norm_rows(expected["rows"])


# ── Per-case runner ───────────────────────────────────────────────────────────

def run_case(case: dict, bird_path: Path) -> dict:
    """Run a single BIRD question through the agent pipeline and return a result dict."""
    qid = case["question_id"]
    db_id = case["db_id"]
    question = case["question"]
    evidence = case.get("evidence", "").strip()
    gold_sql = case["SQL"]
    difficulty = case.get("difficulty", "unknown")

    db = _db_path(bird_path, db_id)
    if not db.exists():
        return {
            "id": qid, "db_id": db_id, "question": question,
            "difficulty": difficulty, "status": "db_missing", "ex": 0,
        }

    # Gold execution (ground truth — run trusted, no validation needed)
    gold_result = execute_sqlite(db, gold_sql, trusted=True)
    if "error" in gold_result:
        return {
            "id": qid, "db_id": db_id, "question": question,
            "difficulty": difficulty, "status": "gold_error",
            "detail": gold_result["error"], "ex": 0,
        }

    # Schema for this database
    schema = get_schema_sqlite(db)

    # Augment question with BIRD evidence hint and SQLite syntax note
    augmented = question
    if evidence:
        augmented += f"\nHint: {evidence}"
    augmented += "\n[Generate SQLite SQL. Use backticks to quote column names that contain spaces or special characters.]"

    # Agent pipeline: generate → validate → execute
    agent_sql = generate_sql(augmented, schema)

    base = {"id": qid, "db_id": db_id, "question": question,
            "difficulty": difficulty, "gold_sql": gold_sql}

    if isinstance(agent_sql, dict) and "error" in agent_sql:
        return {**base, "status": "generate_error",
                "detail": agent_sql["error"], "agent_sql": None, "ex": 0}

    if agent_sql == "UNANSWERABLE":
        return {**base, "status": "unanswerable", "agent_sql": agent_sql, "ex": 0}

    validation = validate_sql(agent_sql)
    if not validation["valid"]:
        return {**base, "status": "invalid_sql",
                "detail": validation["reason"], "agent_sql": agent_sql, "ex": 0}

    agent_result = execute_sqlite(db, agent_sql)
    if "error" in agent_result:
        return {**base, "status": "execution_error",
                "detail": agent_result["error"], "agent_sql": agent_sql, "ex": 0}

    ex = 1 if ex_match(agent_result, gold_result) else 0
    return {
        **base,
        "status": "match" if ex else "mismatch",
        "agent_sql": agent_sql,
        "gold_rows": gold_result["row_count"],
        "agent_rows": agent_result["row_count"],
        "ex": ex,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BIRD benchmark evaluation for Text2SQL Agent")
    parser.add_argument("--bird-path", required=True, type=Path,
                        help="Path to the BIRD dev directory (contains dev.json + dev_databases/)")
    parser.add_argument("--n", type=int, default=50,
                        help="Number of questions to evaluate (default: 50)")
    parser.add_argument("--db", type=str, default=None,
                        help="Restrict to one database ID, e.g. california_schools")
    parser.add_argument("--difficulty", choices=["simple", "moderate", "challenging"],
                        default=None, help="Filter by question difficulty")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for sampling (default: 42)")
    parser.add_argument("--delay", type=float, default=_DEFAULT_DELAY,
                        help=f"Seconds between API calls (default: {_DEFAULT_DELAY})")
    parser.add_argument("--output", type=Path, default=None,
                        help="Save full results to this JSON file")
    args = parser.parse_args()

    dev_json = args.bird_path / "dev.json"
    if not dev_json.exists():
        print(f"ERROR: {dev_json} not found.")
        print("Download BIRD from https://bird-bench.github.io/ and pass the dev/ directory.")
        sys.exit(1)

    with open(dev_json, encoding="utf-8") as f:
        all_cases = json.load(f)

    # Filters
    if args.db:
        all_cases = [c for c in all_cases if c["db_id"] == args.db]
    if args.difficulty:
        all_cases = [c for c in all_cases if c.get("difficulty") == args.difficulty]

    if not all_cases:
        print("ERROR: No matching questions found. Check --db / --difficulty filters.")
        sys.exit(1)

    # Sample and sort for reproducible output
    random.seed(args.seed)
    cases = random.sample(all_cases, min(args.n, len(all_cases)))
    cases.sort(key=lambda c: c["question_id"])

    # Header
    print(f"BIRD Evaluation — {len(cases)} questions")
    if args.db:
        print(f"  Database  : {args.db}")
    if args.difficulty:
        print(f"  Difficulty: {args.difficulty}")
    print(f"  API delay : {args.delay}s between calls")
    print()

    results = []
    ex_total = 0
    diff_stats: dict[str, list] = {
        "simple": [0, 0], "moderate": [0, 0], "challenging": [0, 0]
    }
    status_counts: dict[str, int] = {}

    for i, case in enumerate(cases):
        if i > 0:
            time.sleep(args.delay)

        r = run_case(case, args.bird_path)
        results.append(r)
        ex_total += r["ex"]

        diff = r.get("difficulty", "unknown")
        if diff in diff_stats:
            diff_stats[diff][0] += r["ex"]
            diff_stats[diff][1] += 1

        status = r.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        icon = "PASS" if r["ex"] else "FAIL"
        db_label = f"{r['db_id']:<22}"
        diff_label = f"{diff:<11}"
        q_preview = r["question"][:48]
        print(f"  [{icon}] Q{r['id']:04d} [{db_label}] [{diff_label}] {q_preview}", flush=True)

        if not r["ex"]:
            agent_sql = (r.get("agent_sql") or "")[:90].replace("\n", " ")
            gold_sql = r.get("gold_sql", "")[:90].replace("\n", " ")
            if agent_sql:
                print(f"         agent : {agent_sql}")
                print(f"         gold  : {gold_sql}")
            if r.get("detail"):
                print(f"         error : {r['detail']}")

    # Summary
    total = len(cases)
    ex_pct = ex_total / total * 100 if total else 0
    sep = "-" * 72

    print(f"\n{sep}")
    print(f"  Execution Accuracy (EX) : {ex_total}/{total} = {ex_pct:.1f}%")
    print(f"  Target (Week 5-6)       : 60.0%")
    print(f"  {'PASS' if ex_pct >= 60 else 'BELOW TARGET'}")
    print()

    # Breakdown by difficulty
    any_diff = any(v[1] > 0 for v in diff_stats.values())
    if any_diff:
        print("  By difficulty:")
        for diff, (passed, count) in diff_stats.items():
            if count:
                bar = "#" * int(passed / count * 20)
                print(f"    {diff:<12}: {passed:>3}/{count:<3} = {passed/count*100:5.1f}%  [{bar:<20}]")
        print()

    # Breakdown by failure mode
    print("  Status breakdown:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"    {status:<20}: {count}")

    print(f"{sep}\n")

    # Save results
    if args.output:
        payload = {
            "summary": {
                "ex": ex_total, "total": total, "ex_pct": round(ex_pct, 1),
                "db": args.db, "difficulty": args.difficulty, "n": args.n,
            },
            "by_difficulty": {k: {"passed": v[0], "total": v[1]} for k, v in diff_stats.items() if v[1]},
            "status_counts": status_counts,
            "results": results,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"Results saved to {args.output}")

    return results


if __name__ == "__main__":
    main()
