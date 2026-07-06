"""Query Databricks DESCRIBE HISTORY to report when a table was last updated."""

import os
import anthropic
from dotenv import load_dotenv

from agents.state import AgentState
from config.rbac import get_allowed_tables
from config.prompts import table_name_prompt
from config.settings import APP_MODEL, APP_MAX_TOKENS_TABLE
from db.execute import run_sql
from utils.audit import add_tokens

load_dotenv()
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_ACCESS_KEYWORDS = [
    "tables i have", "what tables", "my access", "my permissions",
    "which tables", "access to", "have access",
]


def _is_access_question(question: str) -> bool:
    """Return True if the question is asking about the user's table permissions."""
    q = question.lower()
    return any(kw in q for kw in _ACCESS_KEYWORDS)


def _extract_table_name(question: str, user_role: str):
    """Use Claude Haiku to resolve which allowed table the question refers to.

    Returns (table_name_or_None, usage_object).
    """
    allowed = get_allowed_tables(user_role)
    table_list = "\n".join(f"- {t}" for t in allowed)
    prompt = table_name_prompt(table_list, question)
    resp = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_TABLE,
        messages=[{"role": "user", "content": prompt}],
    )
    name = resp.content[0].text.strip()
    return (name if name in allowed else None), resp.usage


def get_metadata(state: AgentState) -> AgentState:
    """Run DESCRIBE HISTORY on the detected table, or return RBAC table list for access questions."""
    question = state["question"]
    tu = state.get("token_usage") or {}

    if _is_access_question(question):
        role   = state.get("user_role", "unknown")
        tables = get_allowed_tables(role)
        table_list = "\n".join(f"- `{t}`" for t in tables)
        return {**state, "final_answer": (
            f"As **{role}**, you have access to **{len(tables)} tables**:\n\n{table_list}"
        ), "token_usage": tu}

    table, usage = _extract_table_name(question, state.get("user_role", "executive"))
    if usage:
        tu = add_tokens(tu, "table_name", usage)

    if not table:
        return {**state, "final_answer": (
            "I could not identify which table you are asking about. "
            "Please name a specific table (e.g. 'orders', 'lineitem')."
        ), "token_usage": tu}

    try:
        df = run_sql(f"DESCRIBE HISTORY {table} LIMIT 1")
        if df.empty:
            return {**state, "final_answer": f"No history found for {table}.", "token_usage": tu}

        row       = df.iloc[0]
        timestamp = row.get("timestamp", "unknown")
        operation = row.get("operation", "unknown")
        return {**state, "final_answer": (
            f"Table `{table}` was last updated on **{timestamp}** "
            f"via operation: `{operation}`."
        ), "token_usage": tu}
    except Exception as e:
        return {**state, "final_answer": f"Could not retrieve metadata for {table}: {e}", "token_usage": tu}
