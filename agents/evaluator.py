"""Inline evaluator node — checks the result before it reaches the user."""

from agents.state import AgentState
from config.prompts import relevance_score_prompt
from config.settings import APP_MODEL_EVAL, APP_MAX_TOKENS_EVAL, TEMP_EVAL
from utils.audit import add_tokens
from utils.llm_client import llm_client as _client


def _score_relevance(question: str, answer: str, has_data: bool = False):
    """Ask Claude Sonnet to rate answer relevance (1–5); return (score, usage_object).

    Objective 3: uses APP_MODEL_EVAL (Sonnet) instead of APP_MODEL (Haiku) so a
    different model judges Haiku's output, eliminating correlated self-grading bias.
    """
    if not answer.strip():
        return 1, None
    prompt = relevance_score_prompt(question, answer, has_data)
    resp = _client.messages.create(
        model=APP_MODEL_EVAL,
        max_tokens=APP_MAX_TOKENS_EVAL,
        temperature=TEMP_EVAL,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        score = int(resp.content[0].text.strip()[0])
    except (ValueError, IndexError):
        score = 3
    return score, resp.usage


def evaluate_result(state: AgentState) -> AgentState:
    """Score the result on RBAC compliance, data quality, and answer relevance."""
    notes: list[str] = []
    error        = state.get("error", "")
    intent       = state.get("intent", "")
    final_answer = state.get("final_answer", "")
    df           = state.get("result_df")
    question     = state.get("question", "")
    tu           = state.get("token_usage") or {}

    # 0. Out-of-scope — guardrail blocked it, no LLM call needed
    if intent == "out_of_scope":
        return {**state, "eval_score": 2, "eval_notes": ["Question outside data domain"], "token_usage": tu}

    # 1. RBAC violation — hard block, score 0
    if "rbac violation" in error.lower():
        return {**state, "eval_score": 0, "eval_notes": ["RBAC violation — access denied"], "token_usage": tu}

    # 2. Other execution error
    if error:
        return {**state, "eval_score": 1, "eval_notes": [f"Execution error: {error[:80]}"], "token_usage": tu}

    # 3. Empty SQL result — penalise relevance score by 1
    has_data = df is not None and not getattr(df, "empty", True)
    if intent in ("sql_query", "kpi_compute") and not has_data:
        notes.append("Query returned no results")
        rel, usage = _score_relevance(question, final_answer)
        if usage:
            tu = add_tokens(tu, "evaluator", usage)
        return {**state, "eval_score": max(1, rel - 1), "eval_notes": notes, "token_usage": tu}

    # 4. LLM-as-judge relevance score for successful responses
    score, usage = _score_relevance(question, final_answer, has_data) if final_answer else (2, None)
    if usage:
        tu = add_tokens(tu, "evaluator", usage)
    if score <= 2:
        notes.append("Answer may not fully address the question")

    return {**state, "eval_score": score, "eval_notes": notes, "token_usage": tu}
