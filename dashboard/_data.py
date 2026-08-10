"""Data loading, sidebar filters, and KPI tile rows for the monitoring dashboard."""

import json
import streamlit as st
import pandas as pd
from db.connection import get_connection
from config.settings import AUDIT_TABLE

WINDOWS = {
    "Last 24 hours": "INTERVAL 1 DAY",
    "Last 7 days":   "INTERVAL 7 DAYS",
    "Last 30 days":  "INTERVAL 30 DAYS",
    "All time":      None,
}

# Claude API pricing ($ per token)
_H_IN, _H_OUT = 0.80 / 1_000_000, 4.00 / 1_000_000   # Haiku 4.5
_S_IN, _S_OUT = 3.00 / 1_000_000, 15.00 / 1_000_000   # Sonnet 4.6


@st.cache_data(ttl=60)
def load_audit(window_sql: str | None) -> pd.DataFrame:
    """Fetch all audit columns for the selected time window and enrich with cost cols. Cached 60 s."""
    where = f"WHERE ts >= CURRENT_TIMESTAMP - {window_sql}" if window_sql else ""
    query = f"""
        SELECT ts, question, user_role, intent, eval_score, eval_notes,
               elapsed_sec, error, generated_sql, answer_preview,
               total_input_tokens, total_output_tokens,
               token_calls, generator_model, evaluator_model, feedback
        FROM {AUDIT_TABLE}
        {where}
        ORDER BY ts ASC
    """
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        conn.close()
        df = pd.DataFrame(rows, columns=cols)
        if "ts" in df.columns and not df.empty:
            df["ts"] = (
                pd.to_datetime(df["ts"], utc=True)
                .dt.tz_convert("Asia/Kolkata")
                .dt.tz_localize(None)
            )
        return _enrich_costs(df) if not df.empty else df
    except Exception as e:
        st.error(f"Could not load audit data: {e}")
        return pd.DataFrame()


def _enrich_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-row haiku/sonnet token split and estimated cost.

    Sonnet tokens come from the 'evaluator' step in token_calls.
    Haiku tokens = total_input/output_tokens minus the Sonnet share.
    Using totals as the source of truth avoids undercounting from partial token_calls.
    """
    s_in_l, s_out_l = [], []
    for raw in df.get("token_calls", pd.Series(["[]"] * len(df))).fillna("[]"):
        s_in = s_out = 0
        try:
            for c in (json.loads(raw) if isinstance(raw, str) else []):
                if c.get("step") == "evaluator":
                    s_in += c.get("input", 0) or 0
                    s_out += c.get("output", 0) or 0
        except Exception:
            pass
        s_in_l.append(s_in); s_out_l.append(s_out)

    df = df.copy()
    s_in  = pd.array(s_in_l,  dtype="int64")
    s_out = pd.array(s_out_l, dtype="int64")
    h_in  = (df["total_input_tokens"].fillna(0).astype(int)  - s_in).clip(lower=0)
    h_out = (df["total_output_tokens"].fillna(0).astype(int) - s_out).clip(lower=0)

    df["haiku_tokens"]  = h_in + h_out
    df["sonnet_tokens"] = s_in + s_out
    df["haiku_cost"]    = h_in * _H_IN  + h_out * _H_OUT
    df["sonnet_cost"]   = s_in * _S_IN  + s_out * _S_OUT
    return df


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Render sidebar filters and return the filtered DataFrame."""
    roles   = ["All"] + sorted(df["user_role"].dropna().unique().tolist())
    intents = ["All"] + sorted(df["intent"].dropna().unique().tolist())
    role    = st.sidebar.selectbox("Role",   roles)
    intent  = st.sidebar.selectbox("Intent", intents)
    score_r = st.sidebar.slider("Eval score range", 0, 5, (0, 5))
    st.sidebar.caption("Filters apply to all charts and tables below.")
    if role   != "All": df = df[df["user_role"] == role]
    if intent != "All": df = df[df["intent"]    == intent]
    return df[(df["eval_score"] >= score_r[0]) & (df["eval_score"] <= score_r[1])]


def render_kpi_rows(df: pd.DataFrame) -> None:
    """Render three rows of five KPI tiles: Traffic · Performance · Model & Cost."""
    n = len(df)
    blocked      = int((df["eval_score"] == 0).sum()) if n else 0
    oos          = int((df["intent"] == "out_of_scope").sum()) if n else 0
    errors       = int(df["error"].fillna("").str.strip().ne("").sum()) if n else 0
    success_rate = round((df["eval_score"] >= 3).sum() / n * 100, 1) if n else None
    avg_score    = round(df["eval_score"].mean(), 2) if n else None
    avg_lat      = round(df["elapsed_sec"].mean(), 1) if n else None
    p95_lat      = round(df["elapsed_sec"].quantile(0.95), 1) if n else None
    top_role     = df["user_role"].mode()[0] if n else "—"
    top_intent   = df["intent"].mode()[0] if n else "—"
    total_tok    = int(df["total_input_tokens"].sum() + df["total_output_tokens"].sum()) if n else 0
    haiku_tok    = int(df["haiku_tokens"].sum()) if "haiku_tokens" in df else 0
    sonnet_tok   = int(df["sonnet_tokens"].sum()) if "sonnet_tokens" in df else 0
    haiku_cost   = df["haiku_cost"].sum() if "haiku_cost" in df else 0.0
    total_cost   = haiku_cost + (df["sonnet_cost"].sum() if "sonnet_cost" in df else 0.0)

    # Row 1 — Traffic & Safety
    st.caption("**Traffic & Safety**")
    c = st.columns(5)
    c[0].metric("Total Queries",       n)
    c[1].metric("Blocked (score=0)",   blocked, f"{blocked/n*100:.1f}%" if n else "")
    c[2].metric("Out-of-Scope",        oos)
    c[3].metric("Errors",              errors)
    c[4].metric("Success Rate (≥3/5)", f"{success_rate}%" if success_rate is not None else "—")

    # Row 2 — Quality & Performance
    st.caption("**Quality & Performance**")
    c = st.columns(5)
    c[0].metric("Avg Confidence",   f"{avg_score}/5" if avg_score is not None else "—")
    c[1].metric("Avg Latency",      f"{avg_lat}s"    if avg_lat   is not None else "—")
    c[2].metric("P95 Latency",      f"{p95_lat}s"    if p95_lat   is not None else "—")
    c[3].metric("Most Active Role", top_role)
    c[4].metric("Top Intent",       top_intent)

    # Row 3 — Model & Cost
    st.caption("**Model & Cost (est.)**")
    c = st.columns(5)
    c[0].metric("Total Tokens",  f"{total_tok:,}")
    c[1].metric("Haiku Tokens",  f"{haiku_tok:,}",  help="Generator model — all nodes except evaluator")
    c[2].metric("Sonnet Tokens", f"{sonnet_tok:,}", help="Evaluator model — scores each response")
    c[3].metric("Est. Haiku Cost",  f"${haiku_cost:.4f}")
    c[4].metric("Est. Total Cost",  f"${total_cost:.4f}")
