"""Return column-level schema information for a table the user asks about."""

from agents.state import AgentState


def get_schema_info(state: AgentState) -> AgentState:
    """Match the question to an accessible table and return its columns as final_answer."""
    question = state["question"].lower()
    schema = state.get("schema", {})

    if not schema:
        return {**state, "final_answer": "Schema information is not available right now."}

    # Match the first table whose short name appears in the question
    matched_table: str | None = None
    for full_name in schema:
        short_name = full_name.split(".")[-1]   # e.g. "orders"
        if short_name in question:
            matched_table = full_name
            break

    if not matched_table:
        table_list = ", ".join(f"`{t.split('.')[-1]}`" for t in schema)
        return {**state, "final_answer": (
            f"Please specify which table you'd like to explore.\n\n"
            f"Your accessible tables are: {table_list}."
        )}

    columns = schema.get(matched_table, [])
    if not columns:
        return {**state, "final_answer": f"No column information available for `{matched_table}`."}

    col_lines = "\n".join(f"- **`{c['column']}`** — {c['type']}" for c in columns)
    return {**state, "final_answer": (
        f"**`{matched_table}`** has **{len(columns)} columns**:\n\n{col_lines}"
    )}
