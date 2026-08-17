"""Streamlit chat interface for the multi-agent data assistant."""

import time

import streamlit as st
import pandas as pd

from langsmith import trace

from agents.orchestrator import agent_graph_base
from agents.response_agent import stream_answer
from agents.evaluator import evaluate_result
from config.rbac import get_allowed_tables, ROLE_CONFIG
from utils.audit import log_query, update_feedback

st.set_page_config(
    page_title="Multi-Agent Data Assistant with Guardrails & Observability",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Header banner */
.main-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    padding: 1.4rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    color: white;
}
.main-header h1 { margin: 0; font-size: 1.75rem; font-weight: 700; }
.main-header p  { margin: 0.3rem 0 0; opacity: 0.7; font-size: 0.88rem; }

/* Confidence badge pills */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.badge-0 { background:#3d0000; color:#ff6b6b; }
.badge-1 { background:#3d1a00; color:#ffa94d; }
.badge-2 { background:#3d3200; color:#ffd43b; }
.badge-3 { background:#1e3d00; color:#a9e34b; }
.badge-4 { background:#0d3d1a; color:#69db7c; }
.badge-5 { background:#003d2a; color:#38d9a9; }

/* Intent chip */
.intent-chip {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.74rem;
    background: #1e2d40;
    color: #74c0fc;
    border: 1px solid #2c4a6e;
}

/* Sidebar role card */
.role-card {
    background: #1e2d40;
    border-radius: 8px;
    padding: 0.7rem 1rem;
    margin-top: 0.4rem;
    border-left: 3px solid #4a90d9;
}
.role-card h4 { margin: 0 0 0.2rem; color: #74c0fc; font-size: 0.88rem; }
.role-card p  { margin: 0; color: #8899aa; font-size: 0.76rem; }

/* Table tag chips */
.table-tag {
    display: inline-block;
    padding: 2px 8px;
    margin: 2px 2px 2px 0;
    border-radius: 4px;
    font-size: 0.7rem;
    background: #162030;
    color: #74c0fc;
    border: 1px solid #2c4a6e;
    font-family: monospace;
}

/* Session stat cards */
.stat-card {
    background: #1e2d40;
    border-radius: 8px;
    padding: 0.5rem 0.5rem 0.4rem;
    text-align: center;
}
.stat-num   { font-size: 1.4rem; font-weight: 700; color: #74c0fc; line-height: 1.1; }
.stat-label { font-size: 0.68rem; color: #8899aa; text-transform: uppercase; letter-spacing: 0.05em; }

/* Example question buttons */
div[data-testid="stButton"] button {
    width: 100%;
    text-align: left;
    background: #1a2840;
    border: 1px solid #2c4a6e;
    color: #a8d0f0;
    border-radius: 8px;
    padding: 0.55rem 0.8rem;
    font-size: 0.83rem;
    line-height: 1.4;
    transition: background 0.15s, border-color 0.15s;
}
div[data-testid="stButton"] button:hover {
    background: #243a56;
    border-color: #4a90d9;
    color: #ffffff;
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
ROLE_META = {
    "analyst":   {"icon": "📊", "label": "Analyst"},
    "finance":   {"icon": "💰", "label": "Finance"},
    "executive": {"icon": "👔", "label": "Executive"},
}

EXAMPLE_QUESTIONS = {
    "analyst": [
        "What is Average Order Value?",
        "What is the Average Order Value for Q1 1995?",
        "Show monthly order count trend for 1996",
    ],
    "finance": [
        "What was total revenue by nation last year?",
        "Show monthly revenue trend for 1995",
        "Which top 5 suppliers had the highest total supply cost?",
    ],
    "executive": [
        "Show quarterly revenue by region for 1995",
        "What is the definition of revenue?",
        "What are the top 10 orders by total price in 1996?",
    ],
}

SCORE_LABELS = {0: "Blocked", 1: "Error", 2: "Low", 3: "Moderate", 4: "Good", 5: "High"}
INTENT_LABELS = {
    "sql_query":   "🔢 SQL Query",
    "doc_lookup":  "📄 Doc Lookup",
    "kpi_compute": "📊 KPI Compute",
}


# ── Session state ─────────────────────────────────────────────────────────────
def _init_session() -> None:
    """Initialise session state keys on first load."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "role" not in st.session_state:
        st.session_state.role = "analyst"
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = None
    # Objective 1: persist conversation history across Streamlit reruns
    if "history" not in st.session_state:
        st.session_state.history = []


# ── Sidebar ───────────────────────────────────────────────────────────────────
def _render_sidebar() -> None:
    """Draw the role selector, table chips, and session stats."""
    st.sidebar.markdown("## ⚙️ Settings")

    roles = list(ROLE_META.keys())
    selected = st.sidebar.radio(
        "Active role",
        options=roles,
        index=roles.index(st.session_state.role),
        format_func=lambda r: f"{ROLE_META[r]['icon']}  {ROLE_META[r]['label']}",
    )
    if selected != st.session_state.role:
        st.session_state.role = selected
        st.session_state.messages = []
        st.session_state.history = []   # Objective 1: role switch resets conversation memory
        st.rerun()

    desc = ROLE_CONFIG[selected]["description"]
    st.sidebar.markdown(
        f'<div class="role-card">'
        f'<h4>{ROLE_META[selected]["icon"]} {ROLE_META[selected]["label"]}</h4>'
        f'<p>{desc}</p></div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<br>**Accessible tables:**", unsafe_allow_html=True)
    tables = [t.split(".")[-1] for t in get_allowed_tables(selected)]
    st.sidebar.markdown(
        "".join(f'<span class="table-tag">{t}</span>' for t in tables),
        unsafe_allow_html=True,
    )

    # Session stats
    assistant_msgs = [m for m in st.session_state.messages if m["role"] == "assistant"]
    if assistant_msgs:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Session stats:**")
        scores = [m["eval_score"] for m in assistant_msgs if m.get("eval_score") is not None]
        avg = f"{sum(scores)/len(scores):.1f}" if scores else "—"
        c1, c2 = st.sidebar.columns(2)
        c1.markdown(
            f'<div class="stat-card"><div class="stat-num">{len(assistant_msgs)}</div>'
            f'<div class="stat-label">Queries</div></div>',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f'<div class="stat-card"><div class="stat-num">{avg}</div>'
            f'<div class="stat-label">Avg score</div></div>',
            unsafe_allow_html=True,
        )

    st.sidebar.markdown("---")
    st.sidebar.page_link("pages/1_Monitoring_Dashboard.py", label="📊 Open Monitoring Dashboard", use_container_width=True)
    if st.sidebar.button("🗑️  Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.history = []   # Objective 1: clear also resets history
        st.rerun()


# ── Example questions ─────────────────────────────────────────────────────────
def _render_examples() -> None:
    """Show clickable example questions when the chat history is empty."""
    role = st.session_state.role
    st.markdown(f"#### 💡 Try asking as **{role}**:")
    cols = st.columns(3)
    for i, q in enumerate(EXAMPLE_QUESTIONS[role]):
        if cols[i].button(q, key=f"eg_{i}"):
            st.session_state.pending_question = q


# ── Agent runner ──────────────────────────────────────────────────────────────
def _run_graph(question: str, role: str) -> dict:
    """Run the LangGraph pipeline and return the accumulated state.

    Does NO LLM answer-generation — only the data-fetching nodes
    (intent classification, RAG retrieval, schema load, SQL execution).
    The answer is streamed separately so the user sees tokens as they arrive.

    Objective 1: seeds the graph with the session's conversation history so
    follow-up questions have prior-turn context available.
    """
    init: dict = {
        "question":  question,
        "user_role": role,
        "history":   list(st.session_state.get("history", [])),
    }
    final_state: dict = dict(init)
    with st.spinner("Thinking…"):
        try:
            for chunk in agent_graph_base.stream(init, stream_mode="updates"):
                for _, state_update in chunk.items():
                    final_state = {**final_state, **state_update}
        except Exception as e:
            final_state["error"] = str(e)
    return final_state


# ── Result rendering ──────────────────────────────────────────────────────────
def _render_meta(result: dict) -> None:
    """Render coloured intent chip, confidence badge, and elapsed time."""
    intent  = result.get("intent", "")
    score   = result.get("eval_score")
    elapsed = result.get("elapsed")
    notes   = result.get("eval_notes", [])

    parts = []
    if intent:
        parts.append(f'<span class="intent-chip">{INTENT_LABELS.get(intent, intent)}</span>')
    if score is not None:
        parts.append(
            f'<span class="badge badge-{score}">⬤ {score}/5 — {SCORE_LABELS.get(score, score)}</span>'
        )
    if elapsed is not None:
        parts.append(f'<span style="color:#8899aa;font-size:0.76rem">⏱ {elapsed}s</span>')

    if parts:
        st.markdown("&nbsp; ".join(parts), unsafe_allow_html=True)
    for n in notes:
        st.caption(f"⚠ {n}")


def _render_feedback(idx: int, msg: dict) -> None:
    """HITL: thumbs up/down under each answer, logged against its audit row.

    Feedback is only logged for now (not used to auto-retry or self-correct) —
    it feeds the same kind of manual "add to training data + retrain" loop
    used for the intent classifier. See utils/audit.py: update_feedback().
    """
    row_id = msg.get("row_id")
    if not row_id or not msg.get("content"):
        return

    fb = st.feedback("thumbs", key=f"feedback_{idx}")
    if fb is not None and msg.get("feedback_raw") != fb:
        msgs = list(st.session_state.messages)
        msgs[idx] = {**msgs[idx], "feedback_raw": fb}
        st.session_state.messages = msgs
        update_feedback(row_id, "correct" if fb == 1 else "incorrect")


def _render_dataframe(df: pd.DataFrame) -> None:
    """Show table and chart as switchable tabs; table-only if chart not applicable."""
    can_chart = len(df.columns) == 2 and pd.api.types.is_numeric_dtype(df.iloc[:, 1])

    if not can_chart:
        st.dataframe(df, use_container_width=True)
        return

    chart_df = df.copy()
    col0 = chart_df.iloc[:, 0]
    if pd.api.types.is_datetime64_any_dtype(col0):
        chart_df.iloc[:, 0] = col0.dt.strftime("%Y-%m")
    elif col0.dtype == object and hasattr(col0.iloc[0], "strftime"):
        # Timezone-aware Python datetime objects come back as object dtype
        chart_df.iloc[:, 0] = col0.apply(lambda d: d.strftime("%Y-%m"))

    tab_table, tab_chart = st.tabs(["📋 Table", "📊 Chart"])
    with tab_table:
        st.dataframe(df, use_container_width=True)
    with tab_chart:
        st.bar_chart(chart_df.set_index(chart_df.columns[0]))


def _render_chat_history() -> None:
    """Replay all past messages from session state."""
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg.get("error"):
                st.error(msg["error"])
            elif msg.get("content"):
                st.markdown(msg["content"])
                if msg.get("dataframe") is not None:
                    _render_dataframe(msg["dataframe"])
                if msg.get("sql"):
                    with st.expander("📋 View generated SQL"):
                        st.code(msg["sql"], language="sql")
            elif msg["role"] == "assistant":
                st.caption("_(response unavailable)_")
            _render_meta(msg)
            if msg["role"] == "assistant":
                _render_feedback(idx, msg)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    """Entry point: render the full Streamlit page."""
    _init_session()
    _render_sidebar()

    # Always render the same single header element so Streamlit's delta
    # positions stay consistent across every script run.  Branching between
    # a welcome banner and a compact header created different element counts
    # at the top of the page, shifting all downstream deltas and causing
    # ghost elements / disappearing chat bubbles.
    role = st.session_state.role
    st.markdown(
        f'<div class="main-header">'
        f'<h1>Multi-Agent Data Assistant with Guardrails &amp; Observability</h1>'
        f'<p>Logged in as <b>{role}</b> · ask anything about your data in plain English.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Replay all past messages from session state
    _render_chat_history()

    # Always render the input widget so it's visible after button-triggered answers
    typed_input = st.chat_input("Ask a question about your data…")

    question: str | None = st.session_state.pending_question
    if question:
        st.session_state.pending_question = None
    elif typed_input:
        question = typed_input

    # Show examples only when IDLE (no active question) AND the chat is empty.
    # Checking here — after resolving `question` — means examples are never
    # rendered during Q1's processing run. So the page layout during Q1's run
    # ([header][empty history][Q1 inline][A1 inline]) matches Q2's run
    # ([header][Q1 history][A1 history][Q2 inline][A2 inline]).
    # A1 stays at the same screen position; there is no position jump or flash.
    if not question and not st.session_state.messages:
        _render_examples()

    if question:
        t0 = time.time()

        # ── User message ──────────────────────────────────────────────────────
        st.session_state.messages = st.session_state.messages + [
            {"role": "user", "content": question}
        ]
        with st.chat_message("user"):
            st.markdown(question)

        # ── Assistant response ────────────────────────────────────────────────
        with st.chat_message("assistant"):

            # Steps 1-4 run inside one LangSmith trace so the graph invocation,
            # the streamed answer, and the evaluator's judging call all nest
            # under a single root run instead of showing up as unrelated
            # top-level traces — wrap_anthropic() alone doesn't bind them
            # together, since LangGraph nodes and this app-level code aren't
            # otherwise in the same tracing context.
            with trace(name="answer_question", inputs={"question": question, "role": role}) as run:
                # Step 1: run the data-fetching graph (spinner, no LLM answer yet)
                try:
                    final_state = _run_graph(question, role)
                except Exception as e:
                    final_state = {"question": question, "user_role": role, "error": str(e)}

                error = final_state.get("error", "")

                # Step 2: store a placeholder entry NOW — before streaming starts.
                # If Streamlit interrupts the script mid-stream (because the user
                # submits the next question), this entry already exists in session
                # state so _render_chat_history() will show it on the next run.
                placeholder_idx = len(st.session_state.messages)
                st.session_state.messages = st.session_state.messages + [{
                    "role":       "assistant",
                    "content":    "",          # filled in after streaming
                    "error":      error,
                    "intent":     final_state.get("intent", ""),
                    "dataframe":  final_state.get("result_df"),
                    "sql":        final_state.get("generated_sql", ""),
                    "elapsed":    0,
                    "eval_score": None,
                    "eval_notes": [],
                }]

                # Step 3: stream the LLM answer token-by-token
                answer_text = ""
                if error:
                    st.error(error)
                else:
                    try:
                        answer_text = st.write_stream(stream_answer(final_state))
                    except Exception as e:
                        error = str(e)
                        st.error(f"Failed to generate response: {e}")

                # Step 4: evaluate (needs the full answer text)
                final_state = {**final_state, "final_answer": answer_text}
                final_state = evaluate_result(final_state)

                run.add_outputs({
                    "intent":     final_state.get("intent", ""),
                    "eval_score": final_state.get("eval_score"),
                    "error":      error,
                })

            elapsed = round(time.time() - t0, 2)
            df      = final_state.get("result_df")
            sql     = final_state.get("generated_sql", "")

            # Step 5: update the stored entry with final content + eval results
            msgs = list(st.session_state.messages)
            msgs[placeholder_idx] = {
                **msgs[placeholder_idx],
                "content":    answer_text,
                "error":      error,
                "elapsed":    elapsed,
                "eval_score": final_state.get("eval_score"),
                "eval_notes": final_state.get("eval_notes", []),
            }
            st.session_state.messages = msgs

            # Step 6: render supplementary widgets below the streamed answer
            if isinstance(df, pd.DataFrame) and not df.empty:
                _render_dataframe(df)
            if sql:
                with st.expander("📋 View generated SQL"):
                    st.code(sql, language="sql")

            # Objective 1: the UI uses agent_graph_base (streaming graph) which does NOT
            # include format_response, so history is never updated inside the graph.
            # Always append the completed turn manually here — except when the output
            # guardrail (evaluate_result) flagged a prompt/schema leak in this answer;
            # a leaked fragment must not become "prior context" for the next question.
            if answer_text and not final_state.get("output_leak"):
                from config.settings import APP_HISTORY_TURNS
                prior = list(st.session_state.history)
                prior.append({
                    "question":       question,
                    "intent":         final_state.get("intent", ""),
                    "generated_sql":  final_state.get("generated_sql", ""),
                    "result_summary": answer_text[:200],
                })
                st.session_state.history = prior[-APP_HISTORY_TURNS:]

            final_msg = msgs[placeholder_idx]
            row_id = log_query(question, role, {
                **final_msg,
                "answer":      final_msg.get("content", ""),
                "token_usage": final_state.get("token_usage", {}),
            })
            if row_id:
                msgs = list(st.session_state.messages)
                msgs[placeholder_idx] = {**final_msg, "row_id": row_id}
                st.session_state.messages = msgs
                final_msg = msgs[placeholder_idx]

            _render_meta(final_msg)
            _render_feedback(placeholder_idx, final_msg)

            # Force one more rerun so this turn repaints through the exact same
            # path as every past message (_render_chat_history), instead of
            # staying on the "live" render above. Without this, the meta row
            # (intent/score/elapsed) rendered here can end up below the chat
            # container's auto-scroll position and stay invisible until the
            # next interaction forces a rerun anyway — this makes that repaint
            # happen immediately instead of waiting on the next question.
            st.rerun()


if __name__ == "__main__":
    main()
