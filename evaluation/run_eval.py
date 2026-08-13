"""Offline evaluation runner — invokes the full agent graph and reports all 5 KPIs."""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langsmith import trace

from agents.orchestrator import agent_graph
from evaluation.test_cases import TEST_SUITE
from evaluation.scorer import score_intent, score_rbac, score_sql, aggregate_metrics


def _run_case(tc: dict) -> dict:
    """Invoke the agent graph for one test case and return a scored result dict."""
    start = time.time()
    try:
        # One trace per case — without this, every node's wrapped LLM call
        # (utils/llm_client.py) shows up as its own disconnected top-level
        # trace in LangSmith instead of nesting under this case's run.
        with trace(name=f"eval_case_{tc['id']}", inputs={"question": tc["question"]}):
            state = agent_graph.invoke({
                "question":  tc["question"],
                "user_role": tc["user_role"],
            })
        error  = state.get("error", "")
        intent = state.get("intent", "")
        answer = state.get("final_answer", "")
        # eval_score comes from the inline evaluator node in the graph
        eval_score = state.get("eval_score")
        eval_notes = state.get("eval_notes", [])
    except Exception as e:
        error, intent, answer, eval_score, eval_notes = str(e), "", "", 1, [str(e)]

    elapsed = round(time.time() - start, 2)

    return {
        "id":          tc["id"],
        "description": tc["description"],
        "intent_ok":   score_intent(intent, tc["expected_intent"]),
        "rbac_ok":     score_rbac(error, tc["expected_rbac_ok"]),
        "sql_ok":      score_sql(error, intent, tc["expected_rbac_ok"]),
        "eval_score":  eval_score,
        "eval_notes":  eval_notes,
        "latency":     elapsed,
        "intent":      intent,
        "answer":      answer[:120],
        "error":       error,
    }


def _print_report(results: list[dict]) -> None:
    """Print per-case results then the 5 aggregate KPIs."""
    print("\n" + "=" * 68)
    print("EVALUATION REPORT")
    print("=" * 68)

    for r in results:
        passed = r["intent_ok"] and r["rbac_ok"] and r["sql_ok"]
        print(f"\n[{'PASS' if passed else 'FAIL'}] {r['id']} — {r['description']}")
        print(f"  Intent     : {'✓' if r['intent_ok'] else '✗'}  (got: {r['intent']})")
        print(f"  RBAC       : {'✓' if r['rbac_ok']   else '✗'}")
        print(f"  SQL exec   : {'✓' if r['sql_ok']    else '✗'}")
        score_str = f"{r['eval_score']}/5" if r["eval_score"] is not None else "N/A"
        print(f"  Confidence : {score_str}  (LLM-as-judge)  {', '.join(r['eval_notes'])}")
        print(f"  Latency    : {r['latency']}s")
        if r["error"]:
            print(f"  Error      : {r['error'][:80]}")

    metrics = aggregate_metrics(results)
    print("\n" + "=" * 68)
    print("SUMMARY METRICS")
    print(f"  Intent Accuracy   : {metrics['intent_accuracy']}%")
    print(f"  RBAC Compliance   : {metrics['rbac_compliance']}%")
    print(f"  SQL Accuracy      : {metrics['sql_accuracy']}%")
    print(f"  Avg Relevance     : {metrics['avg_relevance']}/5  (LLM-as-judge, Haiku)")
    print(f"  Avg Latency       : {metrics['avg_latency_sec']}s")
    print("=" * 68)

    all_pass = all(r["intent_ok"] and r["rbac_ok"] and r["sql_ok"] for r in results)
    sys.exit(0 if all_pass else 1)


def main() -> None:
    """Run all evaluation test cases and output the metrics report."""
    print(f"Running evaluation suite ({len(TEST_SUITE)} test cases)…\n")
    results = []
    for tc in TEST_SUITE:
        print(f"→ {tc['id']}: {tc['question']}")
        results.append(_run_case(tc))
    _print_report(results)


if __name__ == "__main__":
    main()
