"""Seed the audit table with results from both test tiers for the dashboard demo.

Tier 1 — 38 automated cases (evaluation/test_cases.py)
Tier 2 — 37 Capstone 1 UAT cases (evaluation/uat_cases_c1.py)

Total: 75 rows inserted into data_assistant.audit.query_audit_log

Run once before a viva/demo:  python tests/seed_audit.py
Uses the same agent_graph and log_query as app.py — results are real.
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.orchestrator import agent_graph
from utils.audit import log_query
from evaluation.test_cases import TEST_SUITE
from evaluation.uat_cases_c1 import UAT_C1


def _run_and_log(tc: dict, tier: str) -> None:
    """Invoke the graph for one case and log the result to the audit table."""
    start = time.time()
    try:
        state = agent_graph.invoke({
            "question":  tc["question"],
            "user_role": tc["user_role"],
            "history":   tc.get("history", []),
        })
        elapsed = round(time.time() - start, 2)
        log_query(tc["question"], tc["user_role"], {
            "intent":      state.get("intent", ""),
            "eval_score":  state.get("eval_score"),
            "eval_notes":  state.get("eval_notes", []),
            "elapsed":     elapsed,
            "error":       state.get("error", ""),
            "sql":         state.get("generated_sql", ""),
            "answer":      state.get("final_answer", ""),
            "token_usage": state.get("token_usage", {}),
        })
        status = "ok"
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        status = f"ERROR: {e}"

    label = tc.get("id") or tc.get("question", "")[:30]
    print(f"  [{tier}] {label:<12} {elapsed:>6.1f}s  {status}")


def main() -> None:
    """Seed Tier 1 (38 automated) then Tier 2 (37 C1 UAT) into the audit table."""
    total = len(TEST_SUITE) + len(UAT_C1)
    print(f"\nSeeding {total} audit rows ({len(TEST_SUITE)} Tier 1 + {len(UAT_C1)} Tier 2)…\n")

    print("── Tier 1: Automated test suite (evaluation/test_cases.py) ──")
    for tc in TEST_SUITE:
        _run_and_log(tc, "T1")

    print("\n── Tier 2: Capstone 1 UAT cases (evaluation/uat_cases_c1.py) ──")
    for tc in UAT_C1:
        _run_and_log(tc, "T2")

    print(f"\n✅  Done — {total} rows written to audit table.")
    print("   Open the dashboard to verify: streamlit run dashboard/monitoring.py\n")


if __name__ == "__main__":
    main()
