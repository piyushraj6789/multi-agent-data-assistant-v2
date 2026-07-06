"""Hybrid RAG+SQL agent: extract KPI formula from PDF context, then compute via SQL."""

from agents.state import AgentState
from agents.sql_agent import _build_schema_str, _check_rbac
from config.prompts import kpi_formula_extract_prompt, kpi_sql_prompt
from config.settings import APP_MODEL, APP_MAX_TOKENS_ANSWER, APP_MAX_TOKENS_SQL, TEMP_SQL, TEMP_ANSWER
from db.execute import run_with_correction, extract_sql
from utils.audit import add_tokens
from utils.llm_client import llm_client as _client


def _extract_formula(doc_context: str, question: str) -> tuple[str, object]:
    """Step 1: ask Haiku to pull the KPI formula from PDF chunks. Returns (formula, usage)."""
    response = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_ANSWER,
        temperature=TEMP_ANSWER,
        messages=[{"role": "user", "content": kpi_formula_extract_prompt(doc_context, question)}],
    )
    return response.content[0].text.strip(), response.usage


def _generate_kpi_sql(kpi_formula: str, schema_str: str, question: str) -> tuple[str, object]:
    """Step 2: ask Haiku to write SQL that implements the formula with a time filter. Returns (sql, usage)."""
    response = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_SQL,
        temperature=TEMP_SQL,
        messages=[{"role": "user", "content": kpi_sql_prompt(kpi_formula, schema_str, question)}],
    )
    return extract_sql(response.content[0].text), response.usage


def run_kpi_agent(state: AgentState) -> AgentState:
    """Run the two-step KPI agent: formula extraction → SQL generation → execution."""
    tu = state.get("token_usage") or {}
    try:
        doc_context = state.get("doc_context", "")
        schema_str = _build_schema_str(state.get("schema", {}))

        # Step 1 — extract KPI formula from RAG context
        kpi_formula, formula_usage = _extract_formula(doc_context, state["question"])
        tu = add_tokens(tu, "kpi_formula", formula_usage)

        # Step 2 — generate SQL using the extracted formula
        sql, sql_usage = _generate_kpi_sql(kpi_formula, schema_str, state["question"])
        tu = add_tokens(tu, "kpi_sql", sql_usage)

        _check_rbac(sql, state["user_role"])
        result_df, fix_usages = run_with_correction(sql, state["question"])
        for usage in fix_usages:
            tu = add_tokens(tu, "sql_fix", usage)

        return {
            **state,
            "kpi_formula":   kpi_formula,
            "generated_sql": sql,
            "result_df":     result_df,
            "error":         "",
            "token_usage":   tu,
        }
    except Exception as e:
        return {**state, "generated_sql": "", "result_df": None, "error": str(e), "token_usage": tu}
