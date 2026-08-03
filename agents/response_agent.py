"""Format the agent state into a final human-readable answer for the Streamlit UI."""

from collections.abc import Generator

from agents.state import AgentState
from config.prompts import dataframe_summary_prompt, doc_answer_prompt
from config.settings import (
    APP_MODEL, APP_MAX_TOKENS_RESPONSE, APP_MAX_TOKENS_ANSWER,
    TEMP_ANSWER, APP_HISTORY_TURNS,
)
from utils.audit import add_tokens
from utils.llm_client import llm_client as _client


def _summarise_dataframe(state: AgentState):
    """Ask Claude Haiku to summarise the SQL result; return (text, usage_object)."""
    df = state.get("result_df")
    if df is None or df.empty:
        return "The query returned no results.", None

    table_str = df.head(20).to_markdown(index=False)
    response = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_RESPONSE,
        temperature=TEMP_ANSWER,
        messages=[{"role": "user", "content": dataframe_summary_prompt(table_str, state["question"])}],
    )
    return response.content[0].text.strip(), response.usage


def _friendly_error(error: str) -> str:
    """Convert a technical error string into a plain-English user message."""
    low = error.lower()
    if "mutating statement" in low or "mutating command" in low:
        return (
            "I cannot execute this query. It contains a write or DDL operation "
            "(DELETE, INSERT, UPDATE, MERGE, DROP, etc.), which is not allowed. "
            "Please rephrase as a SELECT query."
        )
    if "rbac violation" in low or "not allowed to access" in low:
        return f"Access denied: your role does not have permission to query those tables."
    if "sql failed after" in low:
        return "The query could not be executed after multiple correction attempts. Please try rephrasing."
    return f"Something went wrong: {error}"


def stream_answer(state: AgentState) -> Generator[str, None, None]:
    """Yield text chunks for the final answer — used by the streaming UI path.

    Handles doc_lookup, sql_query, kpi_compute, and out_of_scope intents.
    The caller collects chunks via st.write_stream().
    """
    intent = state.get("intent", "sql_query")

    if intent == "out_of_scope":
        yield state.get("final_answer", "I can only answer questions about the TPC-H business data.")
        return

    if intent == "doc_lookup":
        doc_context = state.get("doc_context", "")
        if not doc_context:
            yield "No relevant documentation found for that question."
            return
        with _client.messages.stream(
            model=APP_MODEL,
            max_tokens=APP_MAX_TOKENS_ANSWER,
            temperature=TEMP_ANSWER,
            messages=[{
                "role": "user",
                "content": doc_answer_prompt(doc_context, state["question"], history=state.get("history") or []),
            }],
        ) as stream:
            yield from stream.text_stream
        return

    # sql_query or kpi_compute — check for errors before trying the DataFrame
    error = state.get("error", "")
    if error:
        yield _friendly_error(error)
        return

    df = state.get("result_df")
    if df is None or df.empty:
        yield "The query returned no results."
        return

    table_str = df.head(20).to_markdown(index=False)
    with _client.messages.stream(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_RESPONSE,
        temperature=TEMP_ANSWER,
        messages=[{"role": "user", "content": dataframe_summary_prompt(table_str, state["question"])}],
    ) as stream:
        yield from stream.text_stream


def format_response(state: AgentState) -> AgentState:
    """Build the final_answer string based on intent and what the previous agents produced."""
    intent = state.get("intent", "sql_query")
    error  = state.get("error", "")
    tu     = state.get("token_usage") or {}

    if error:
        final_answer = f"Something went wrong: {error}"

    elif intent == "metadata":
        final_answer = state.get("final_answer", "No metadata available.")

    elif intent == "doc_lookup":
        final_answer = state.get("final_answer", "No documentation context found.")

    elif intent == "schema_lookup":
        final_answer = state.get("final_answer", "No schema information available.")

    else:  # sql_query or kpi_compute — both produce a result_df
        final_answer, usage = _summarise_dataframe(state)
        if usage:
            tu = add_tokens(tu, "df_summary", usage)

    # Objective 1: append this turn to history, keeping only the last APP_HISTORY_TURNS entries.
    prior_history: list[dict] = list(state.get("history") or [])
    new_turn: dict = {
        "question":       state.get("question", ""),
        "intent":         intent,
        "generated_sql":  state.get("generated_sql", ""),
        "result_summary": final_answer[:200],   # compact — don't paste full DataFrames
    }
    history = (prior_history + [new_turn])[-APP_HISTORY_TURNS:]

    return {**state, "final_answer": final_answer, "token_usage": tu, "history": history}
