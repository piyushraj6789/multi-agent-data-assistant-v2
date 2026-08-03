"""Shared LangGraph state schema passed between every agent node."""

from typing import Any
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    question: str        # user's original question
    user_role: str       # analyst | finance | executive
    intent: str          # doc_lookup | kpi_compute | sql_query
    doc_context: str     # retrieved PDF chunks
    schema: dict         # live schema from Databricks, filtered by role
    generated_sql: str   # SQL produced by Claude Haiku
    result_df: Any       # pandas DataFrame from Databricks
    final_answer: str    # text answer for doc_lookup intent
    error: str           # error message if something fails
    eval_score: int      # 0-5 confidence score from evaluator (0 = RBAC blocked)
    eval_notes: list     # flags e.g. ["empty result", "low relevance"]
    token_usage: dict    # accumulated LLM token counts {total_input, total_output, calls}
    kpi_formula: str     # KPI formula extracted from PDF — set by kpi_agent Step 1
    history: list        # Objective 1: last N turns — [{"question", "intent", "generated_sql", "result_summary"}]
