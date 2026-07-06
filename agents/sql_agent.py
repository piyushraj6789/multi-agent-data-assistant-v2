"""Generate a Databricks SQL query from a natural language question using Claude Haiku."""

from agents.state import AgentState
from config.rbac import get_allowed_tables, check_metric_access
from config.prompts import sql_generation_prompt
from db.execute import run_with_correction, extract_sql
from config.settings import APP_MODEL, APP_MAX_TOKENS_SQL, TEMP_SQL
from utils.audit import add_tokens
from utils.llm_client import llm_client as _client


def _build_schema_str(schema: dict) -> str:
    """Format the schema dict into a readable string for the prompt."""
    lines: list[str] = []
    for table, columns in schema.items():
        col_str = ", ".join(f"{c['column']} ({c['type']})" for c in columns)
        lines.append(f"  {table}: {col_str}")
    return "\n".join(lines)


def _generate_sql(question: str, user_role: str, schema: dict, doc_context: str):
    """Send the prompt to Claude Haiku; return (sql_string, usage_object)."""
    schema_str = _build_schema_str(schema)
    prompt = sql_generation_prompt(user_role, schema_str, doc_context, question)
    response = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_SQL,
        temperature=TEMP_SQL,
        messages=[{"role": "user", "content": prompt}],
    )
    return extract_sql(response.content[0].text), response.usage


def _check_rbac(sql: str, user_role: str) -> None:
    """Raise PermissionError if the SQL references a table the role cannot access."""
    allowed = set(get_allowed_tables(user_role))
    sql_lower = sql.lower()
    all_tables = {
        "samples.tpch.orders", "samples.tpch.lineitem", "samples.tpch.customer",
        "samples.tpch.supplier", "samples.tpch.nation", "samples.tpch.region",
        "samples.tpch.part", "samples.tpch.partsupp",
    }
    forbidden = [t for t in all_tables if t not in allowed and t in sql_lower]
    if forbidden:
        raise PermissionError(
            f"RBAC violation: role '{user_role}' is not allowed to access: {forbidden}"
        )


def run_sql_agent(state: AgentState) -> AgentState:
    """Generate SQL with Haiku, validate RBAC, execute with self-correction, store DataFrame."""
    tu = state.get("token_usage") or {}
    try:
        check_metric_access(state["question"], state["user_role"])
        sql, gen_usage = _generate_sql(
            question=state["question"],
            user_role=state["user_role"],
            schema=state.get("schema", {}),
            doc_context=state.get("doc_context", ""),
        )
        tu = add_tokens(tu, "sql_generation", gen_usage)
        _check_rbac(sql, state["user_role"])
        result_df, fix_usages = run_with_correction(sql, state["question"])
        for usage in fix_usages:
            tu = add_tokens(tu, "sql_fix", usage)
        return {**state, "generated_sql": sql, "result_df": result_df, "error": "", "token_usage": tu}
    except Exception as e:
        return {**state, "generated_sql": "", "result_df": None, "error": str(e), "token_usage": tu}
