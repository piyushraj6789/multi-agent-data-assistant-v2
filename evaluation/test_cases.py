"""Evaluation test suite — 6 cases covering all 3 intents, roles, and RBAC scenarios."""

from typing import TypedDict


class TestCase(TypedDict):
    id: str
    description: str
    question: str
    user_role: str
    expected_intent: str
    expected_rbac_ok: bool  # True = normal response, False = expect RBAC block


TEST_SUITE: list[TestCase] = [
    # ── Primary use cases (UC1–UC3): one per intent ───────────────────────────
    {
        "id": "UC1",
        "description": "KPI Definition Lookup",
        "question": "What is Average Order Value?",
        "user_role": "analyst",
        "expected_intent": "doc_lookup",
        "expected_rbac_ok": True,
    },
    {
        "id": "UC2",
        "description": "KPI Computation — Avg Days to Ship for Q3 1996",
        "question": "What is the Average Days to Ship for Q3 1996?",
        "user_role": "finance",
        "expected_intent": "kpi_compute",
        "expected_rbac_ok": True,
    },
    {
        "id": "UC3",
        "description": "NL-SQL Query — Revenue by Nation",
        "question": "What was total revenue by nation last year?",
        "user_role": "finance",
        "expected_intent": "sql_query",
        "expected_rbac_ok": True,
    },
    # ── Supplementary cases: edge cases and additional coverage ───────────────
    {
        "id": "UC4",
        "description": "RBAC Violation — Finance accessing Customer names",
        "question": "What are the names and market segments of our top 5 customers by total spending?",
        "user_role": "finance",
        "expected_intent": "sql_query",
        "expected_rbac_ok": False,
    },
    {
        "id": "UC5",
        "description": "Supply Chain SQL Query",
        "question": "Which top 5 suppliers had the highest total supply cost?",
        "user_role": "finance",
        "expected_intent": "sql_query",
        "expected_rbac_ok": True,
    },
    {
        "id": "UC6",
        "description": "Metric Definition Lookup",
        "question": "What does lineitem mean?",
        "user_role": "executive",
        "expected_intent": "doc_lookup",
        "expected_rbac_ok": True,
    },
]
