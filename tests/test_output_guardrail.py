"""Output guardrail test — zero API cost.

detect_prompt_leak() and its evaluate_result() short-circuit are pure Python
(no LLM call on the leak path), so this doesn't need the full graph or a
real Anthropic/Databricks call, unlike tests/run_all_tests.py's 40 cases.
A real LLM can't be made to leak its prompt deterministically, so this
fabricates the answer text directly instead of generating one.

Run with: python tests/test_output_guardrail.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.sanitizer import detect_prompt_leak
from agents.evaluator import evaluate_result

CASES = [
    {
        "id": "OG1",
        "description": "Leaked SQL-agent system instructions + schema",
        "final_answer": (
            "You are a Databricks SQL expert. User role: analyst. "
            "Allowed tables ONLY: samples.tpch.orders, samples.tpch.customer."
        ),
        "expect_leak": True,
    },
    {
        "id": "OG2",
        "description": "Leaked KPI-formula-extraction instructions",
        "final_answer": "From the documentation below, extract the calculation formula for the KPI.",
        "expect_leak": True,
    },
    {
        "id": "OG3",
        "description": "Normal, clean answer — must NOT false-positive",
        "final_answer": "The average order value for 1997 was $2,847.32, based on 15,230 orders.",
        "expect_leak": False,
    },
    {
        "id": "OG4",
        "description": "Answer mentioning 'role' in a normal business sense — must NOT false-positive",
        "final_answer": "Finance and executive roles can both see supplier cost data.",
        "expect_leak": False,
    },
]


def _run(tc: dict) -> dict:
    detected = detect_prompt_leak(tc["final_answer"])

    if tc["expect_leak"]:
        # Only route leak-positive cases through evaluate_result(): the leak
        # check short-circuits BEFORE any LLM call, so this stays free. A
        # clean answer would instead fall through to the real Sonnet
        # relevance-scoring branch — genuinely calling the API — so
        # false-positive cases (below) are checked via detect_prompt_leak()
        # directly instead, never touching evaluate_result().
        state = {
            "intent": "sql_query", "final_answer": tc["final_answer"],
            "question": "irrelevant for this check", "error": "", "result_df": None,
        }
        result = evaluate_result(state)
        leak_flagged = result.get("output_leak", False)
        passed = leak_flagged == True and result.get("eval_score") == 0
        eval_score = result.get("eval_score")
    else:
        leak_flagged = bool(detected)
        passed = leak_flagged == tc["expect_leak"]
        eval_score = "n/a (skipped — would call Sonnet)"

    return {**tc, "detected_markers": detected, "leak_flagged": leak_flagged,
            "eval_score": eval_score, "passed": passed}


def main() -> None:
    results = [_run(tc) for tc in CASES]
    print(f"{'ID':5s} {'PASS':6s} {'leak?':7s} {'score':6s}  description")
    for r in results:
        print(f"{r['id']:5s} {'PASS' if r['passed'] else 'FAIL':6s} "
              f"{str(r['leak_flagged']):7s} {str(r['eval_score']):6s}  {r['description']}")
        if r["detected_markers"]:
            print(f"      matched markers: {r['detected_markers']}")

    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} passed")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
