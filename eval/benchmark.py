"""BIRD benchmark evaluation runner for the Text2SQL Agent."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.schema_tool import get_schema
from agent.tools.sql_generator import generate_sql
from agent.tools.sql_validator import validate_sql
from agent.tools.query_executor import execute_query


def run_test_case(case: dict, schema: dict) -> dict:
    """Run a single test case through the tool pipeline and return the result."""
    question = case["question"]
    sql = generate_sql(question, schema)

    if isinstance(sql, dict) and "error" in sql:
        return {"id": case["id"], "question": question, "status": "error", "detail": sql["error"]}

    if sql == "UNANSWERABLE":
        return {"id": case["id"], "question": question, "status": "unanswerable", "sql": sql}

    validation = validate_sql(sql)
    if not validation["valid"]:
        return {"id": case["id"], "question": question, "status": "invalid_sql", "sql": sql, "reason": validation["reason"]}

    result = execute_query(sql)
    if "error" in result:
        return {"id": case["id"], "question": question, "status": "execution_error", "sql": sql, "detail": result["error"]}

    return {
        "id": case["id"],
        "question": question,
        "status": "success",
        "sql": sql,
        "row_count": result["row_count"],
    }


def main():
    cases_path = Path(__file__).parent / "test_cases.json"
    with open(cases_path) as f:
        cases = json.load(f)

    print(f"Loading schema...")
    schema = get_schema()
    if "error" in schema:
        print(f"Failed to load schema: {schema['error']}")
        sys.exit(1)

    results = []
    success = 0
    for case in cases:
        result = run_test_case(case, schema)
        results.append(result)
        status = result["status"]
        icon = "✓" if status == "success" else "✗"
        print(f"  [{icon}] Q{result['id']}: {result['question'][:60]}... → {status}")
        if status == "success":
            success += 1

    total = len(cases)
    accuracy = success / total * 100 if total > 0 else 0
    print(f"\nExecution Accuracy (EX): {success}/{total} = {accuracy:.1f}%")
    return results


if __name__ == "__main__":
    main()
