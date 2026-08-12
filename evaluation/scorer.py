"""Rule-based scoring helpers and aggregate metrics for the offline evaluation runner."""

from typing import Any


def score_intent(actual: str, expected: str) -> bool:
    """Return True if the classified intent matches what was expected."""
    return actual == expected


def score_rbac(error: str, expected_rbac_ok: bool) -> bool:
    """Return True when the RBAC outcome matches expectation.

    - expected_rbac_ok=True  → no violation should have fired
    - expected_rbac_ok=False → a violation should have fired
    """
    has_violation = "rbac violation" in error.lower()
    return has_violation != expected_rbac_ok


def score_sql(error: str, intent: str, expected_rbac_ok: bool) -> bool:
    """Return True if a sql_query ran without an unexpected error.

    RBAC blocks that were expected are treated as successes, not failures.
    """
    if intent != "sql_query":
        return True
    if not expected_rbac_ok:
        return True  # RBAC block was expected — not a SQL failure
    return error == ""


def aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, float]:
    """Compute the five capstone KPIs from a list of per-case result dicts."""
    n = len(results)
    sql_cases = [r for r in results if r.get("intent") == "sql_query"]
    # Exclude RBAC-blocked cases (eval_score=0) from relevance average
    scored_cases = [r for r in results if (r.get("eval_score") or 0) > 0]

    intent_acc = sum(r["intent_ok"] for r in results) / n * 100
    rbac_acc   = sum(r["rbac_ok"]   for r in results) / n * 100
    sql_acc    = (
        sum(r["sql_ok"] for r in sql_cases) / len(sql_cases) * 100
        if sql_cases else 0.0
    )
    avg_rel = (
        sum(r.get("eval_score", 0) for r in scored_cases) / len(scored_cases)
        if scored_cases else 0.0
    )
    avg_latency = sum(r["latency"] for r in results) / n

    return {
        "intent_accuracy": round(intent_acc, 1),
        "rbac_compliance": round(rbac_acc, 1),
        "sql_accuracy":    round(sql_acc, 1),
        "avg_relevance":   round(avg_rel, 2),
        "avg_latency_sec": round(avg_latency, 2),
    }
