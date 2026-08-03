"""LangGraph StateGraph that routes questions through the right sequence of agents."""

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from config.prompts import doc_answer_prompt
from agents.sanitizer import sanitize_input
from agents.guardrail import check_relevance
from agents.intent_classifier import classify_intent
from agents.retrieval_agent import retrieve_context
from agents.sql_agent import run_sql_agent
from agents.kpi_agent import run_kpi_agent
from agents.response_agent import format_response
from agents.evaluator import evaluate_result
from db.schema import get_schema_for_role
from config.settings import APP_MODEL, APP_MAX_TOKENS_ANSWER, TEMP_ANSWER
from utils.audit import add_tokens


def _load_schema(state: AgentState) -> AgentState:
    """Fetch the live Databricks schema filtered by the user's role."""
    try:
        schema = get_schema_for_role(state["user_role"])
    except Exception as e:
        print(f"Warning: schema fetch failed: {e}")
        schema = {}
    return {**state, "schema": schema}


def _answer_doc_question(state: AgentState) -> AgentState:
    """Ask Claude Haiku to answer a definition question using only the retrieved PDF context."""
    from utils.llm_client import llm_client as client
    doc_context = state.get("doc_context", "")
    tu = state.get("token_usage") or {}

    if not doc_context:
        return {**state, "final_answer": "No relevant documentation found for that question."}

    response = client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_ANSWER,
        temperature=TEMP_ANSWER,
        messages=[{"role": "user", "content": doc_answer_prompt(doc_context, state["question"])}],
    )
    tu = add_tokens(tu, "doc_answer", response.usage)
    return {**state, "final_answer": response.content[0].text.strip(), "token_usage": tu}


def _route_by_intent(state: AgentState) -> str:
    """Return the next node name based on the classified intent."""
    return state.get("intent", "sql_query")


def build_graph() -> StateGraph:
    """Construct and compile the LangGraph agent graph (batch mode, used by eval/tests)."""
    graph = StateGraph(AgentState)

    graph.add_node("sanitize_input",      sanitize_input)    # Objective 2a: entry node
    graph.add_node("guardrail",           check_relevance)
    graph.add_node("classify_intent",     classify_intent)
    graph.add_node("retrieve_context",    retrieve_context)
    graph.add_node("load_schema",         _load_schema)
    graph.add_node("answer_doc_question", _answer_doc_question)
    graph.add_node("run_sql_agent",       run_sql_agent)
    graph.add_node("kpi_agent",           run_kpi_agent)
    graph.add_node("format_response",     format_response)
    graph.add_node("evaluate_result",     evaluate_result)

    graph.set_entry_point("sanitize_input")
    graph.add_edge("sanitize_input", "guardrail")

    graph.add_conditional_edges(
        "guardrail",
        lambda s: "out_of_scope" if s.get("intent") == "out_of_scope" else "relevant",
        {"out_of_scope": END, "relevant": "classify_intent"},
    )

    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {
            "doc_lookup":  "retrieve_context",
            "sql_query":   "retrieve_context",
            "kpi_compute": "retrieve_context",
        },
    )

    graph.add_edge("retrieve_context", "load_schema")

    graph.add_conditional_edges(
        "load_schema",
        _route_by_intent,
        {
            "doc_lookup":  "answer_doc_question",
            "sql_query":   "run_sql_agent",
            "kpi_compute": "kpi_agent",
        },
    )

    graph.add_edge("answer_doc_question", "format_response")
    graph.add_edge("run_sql_agent",        "format_response")
    graph.add_edge("kpi_agent",            "format_response")
    graph.add_edge("format_response",      "evaluate_result")
    graph.add_edge("evaluate_result",      END)

    return graph.compile()


def build_base_graph() -> StateGraph:
    """Streaming-friendly graph — stops before the final answer LLM call.

    Runs: guardrail → classify_intent → retrieve_context → load_schema →
          (run_sql_agent | kpi_agent | END for doc_lookup | END for out_of_scope)

    The caller streams the final answer separately with stream_answer().
    """
    graph = StateGraph(AgentState)

    graph.add_node("sanitize_input",   sanitize_input)    # Objective 2a: entry node
    graph.add_node("guardrail",        check_relevance)
    graph.add_node("classify_intent",  classify_intent)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("load_schema",      _load_schema)
    graph.add_node("run_sql_agent",    run_sql_agent)
    graph.add_node("kpi_agent",        run_kpi_agent)

    graph.set_entry_point("sanitize_input")
    graph.add_edge("sanitize_input", "guardrail")

    graph.add_conditional_edges(
        "guardrail",
        lambda s: "out_of_scope" if s.get("intent") == "out_of_scope" else "relevant",
        {"out_of_scope": END, "relevant": "classify_intent"},
    )

    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {
            "doc_lookup":  "retrieve_context",
            "sql_query":   "retrieve_context",
            "kpi_compute": "retrieve_context",
        },
    )

    graph.add_edge("retrieve_context", "load_schema")

    graph.add_conditional_edges(
        "load_schema",
        _route_by_intent,
        {
            "doc_lookup":  END,              # doc answer streamed by app.py
            "sql_query":   "run_sql_agent",
            "kpi_compute": "kpi_agent",
        },
    )

    graph.add_edge("run_sql_agent", END)
    graph.add_edge("kpi_agent",     END)

    return graph.compile()


# Batch graph for eval/tests; streaming graph for the UI
agent_graph      = build_graph()
agent_graph_base = build_base_graph()
