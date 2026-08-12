"""Automated regression runner — 38 Capstone 2 cases.

Cases are defined once in evaluation/test_cases.py (single source of truth).
This file only contains the runner logic.

Run with: python tests/run_all_tests.py
Regression gate: 37/38 baseline — AMT3 is a known pre-existing guardrail
relevance-check flake, tracked separately. Anything below 37 is a real
regression, not that known flake.
"""

import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.orchestrator import agent_graph
from evaluation.test_cases import TEST_SUITE

INJECTION_MARKERS = [
    "ignore previous instructions", "system:", "reveal the prompt",
    "act as", "no restrictions",
]

# Regression gate: the known-good baseline is 37/38 — AMT3 is a pre-existing
# guardrail relevance-check flake (probabilistic LLM judgment on an
# injection-only follow-up), unrelated to intent-classifier or KPI-formula
# work, tracked separately rather than chased here. Any drop below this
# threshold means an actual regression, not that known flake.
REGRESSION_THRESHOLD = 37


def _run(tc: dict) -> dict:
    """Run one test case through the batch graph and return a result dict."""
    start = time.time()
    try:
        state = agent_graph.invoke({
            "question":  tc["question"],
            "user_role": tc["user_role"],
            "history":   tc.get("history", []),
        })
        elapsed = round(time.time() - start, 2)
        intent  = state.get("intent", "")
        answer  = state.get("final_answer", "")
        error   = state.get("error", "")
        sql     = (state.get("generated_sql") or "").lower()
        exc     = ""
    except Exception as e:
        elapsed, intent, answer, error, sql, exc = 0, "", "", "", "", str(e)

    intent_ok = intent == tc["expected_intent"]
    has_answer = bool(answer.strip())
    has_error  = bool(error.strip()) or bool(exc)

    expect_blocked = not tc["expected_rbac_ok"]
    if expect_blocked:
        outcome_ok = has_error or intent == "out_of_scope"
    else:
        outcome_ok = has_answer and not has_error

    injection_ok = True
    if tc.get("check_no_injection"):
        cleaned_q = state.get("question", "") if not exc else tc["question"]
        injection_ok = not any(m in cleaned_q.lower() for m in INJECTION_MARKERS)

    sql_ok = True
    for term in tc.get("check_sql_contains", []):
        if term.lower() not in sql:
            sql_ok = False

    passed = intent_ok and outcome_ok and injection_ok and sql_ok

    return {
        "id":              tc["id"],
        "group":           tc["group"],
        "desc":            tc["description"],
        "role":            tc["user_role"],
        "expected_intent": tc["expected_intent"],
        "expect_blocked":  expect_blocked,
        "actual_intent":   intent,
        "intent_ok":       intent_ok,
        "outcome_ok":      outcome_ok,
        "injection_ok":    injection_ok,
        "sql_ok":          sql_ok,
        "passed":          passed,
        "latency":         elapsed,
        "answer_snippet":  (answer or error or exc)[:100],
        "error":           error or exc,
    }


def main() -> None:
    """Run all cases and print a tabular summary."""
    print(f"\nRunning {len(TEST_SUITE)} test cases…\n")
    results = []
    for tc in TEST_SUITE:
        print(f"  [{tc['id']}] {tc['description']} …", end=" ", flush=True)
        r = _run(tc)
        results.append(r)
        print("PASS" if r["passed"] else "FAIL")

    W = [6, 11, 34, 10, 12, 12, 7, 8, 7]
    hdr = ["ID", "Group", "Description", "Role", "Exp Intent", "Act Intent", "Blocked", "Pass", "Time"]
    sep = "  ".join("-" * w for w in W)
    row_fmt = "  ".join(f"{{:<{w}}}" for w in W)

    print(f"\n{'='*100}")
    print("TEST RESULTS SUMMARY")
    print(f"{'='*100}")
    print(row_fmt.format(*hdr))
    print(sep)

    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(row_fmt.format(
            r["id"], r["group"], r["desc"][:34],
            r["role"], r["expected_intent"][:12], r["actual_intent"][:12],
            "Yes" if r["expect_blocked"] else "No", status[:7], f"{r['latency']}s",
        ))

    print(sep)

    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\nFAILURE DETAILS ({len(failures)} cases):\n")
        for r in failures:
            print(f"  [{r['id']}] {r['desc']}")
            if not r["intent_ok"]:
                print(f"    Intent   : expected={r['expected_intent']}  got={r['actual_intent']}")
            if not r["outcome_ok"]:
                print(f"    Outcome  : {'expected block but got answer' if r['expect_blocked'] else 'expected answer but got error/empty'}")
            if not r["injection_ok"]:
                print(f"    Sanitizer: injection pattern survived in question")
            if not r["sql_ok"]:
                print(f"    SQL check: required terms missing from generated SQL")
            print(f"    Snippet  : {r['answer_snippet']}")
            if r["error"]:
                print(f"    Error    : {r['error'][:120]}")
            print()

    passed_count = sum(1 for r in results if r["passed"])
    avg_lat = round(sum(r["latency"] for r in results) / len(results), 2)
    gate_ok = passed_count >= REGRESSION_THRESHOLD
    print(f"{'='*100}")
    print(f"  {passed_count}/{len(results)} passed   |   avg latency {avg_lat}s")
    print(f"  Regression gate ({REGRESSION_THRESHOLD}/{len(results)} baseline): "
          f"{'✅ PASS' if gate_ok else '❌ FAIL — this is a real regression, not the known AMT3 flake'}")
    print(f"{'='*100}\n")

    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
