"""End-to-end tests for the three capstone use cases. Run with: python tests/test_graph.py"""

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.orchestrator import agent_graph

# ── Test definitions ────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "id":              "UC1",
        "description":     "KPI Definition Lookup",
        "question":        "What is Average Order Value?",
        "user_role":       "analyst",
        "expected_intent": "doc_lookup",
    },
    {
        "id":              "UC2",
        "description":     "KPI Computation",
        "question":        "What is the Average Days to Ship for Q3 1996?",
        "user_role":       "finance",
        "expected_intent": "kpi_compute",
    },
    {
        "id":              "UC3",
        "description":     "NL-SQL Query",
        "question":        "What was total revenue by nation last year?",
        "user_role":       "finance",
        "expected_intent": "sql_query",
    },
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_case(tc: dict) -> dict:
    """Invoke the agent graph for one test case and return a result summary."""
    start = time.time()

    state = agent_graph.invoke({
        "question":  tc["question"],
        "user_role": tc["user_role"],
    })

    elapsed = round(time.time() - start, 2)
    intent_ok = state.get("intent") == tc["expected_intent"]
    has_answer = bool(state.get("final_answer", "").strip())
    sql_ok = (
        state.get("error", "") == ""
        if tc["expected_intent"] == "sql_query"
        else True
    )

    return {
        "id":           tc["id"],
        "description":  tc["description"],
        "intent_ok":    intent_ok,
        "has_answer":   has_answer,
        "sql_ok":       sql_ok,
        "latency_sec":  elapsed,
        "intent":       state.get("intent"),
        "answer":       state.get("final_answer", "")[:120],
        "error":        state.get("error", ""),
    }


def _print_result(r: dict) -> None:
    """Print a formatted result block for one test case."""
    passed = r["intent_ok"] and r["has_answer"] and r["sql_ok"]
    status = "PASS" if passed else "FAIL"

    print(f"\n{'='*60}")
    print(f"[{status}] {r['id']} — {r['description']}")
    print(f"  Intent match : {'✓' if r['intent_ok'] else '✗'} (got: {r['intent']})")
    print(f"  Has answer   : {'✓' if r['has_answer'] else '✗'}")
    print(f"  SQL success  : {'✓' if r['sql_ok'] else '✗'}")
    print(f"  Latency      : {r['latency_sec']}s")
    print(f"  Answer       : {r['answer']}")
    if r["error"]:
        print(f"  Error        : {r['error']}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run all test cases and print a summary with pass/fail counts."""
    print("Running end-to-end tests…\n")
    results = []

    for tc in TEST_CASES:
        print(f"→ Running {tc['id']}: {tc['question']}")
        try:
            result = _run_case(tc)
        except Exception as e:
            result = {
                "id": tc["id"], "description": tc["description"],
                "intent_ok": False, "has_answer": False, "sql_ok": False,
                "latency_sec": 0, "intent": None, "answer": "", "error": str(e),
            }
        results.append(result)
        _print_result(result)

    # Summary
    passed = sum(1 for r in results if r["intent_ok"] and r["has_answer"] and r["sql_ok"])
    avg_latency = round(sum(r["latency_sec"] for r in results) / len(results), 2)

    print(f"\n{'='*60}")
    print(f"Results : {passed}/{len(results)} passed")
    print(f"Avg latency : {avg_latency}s")
    print("="*60)

    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
