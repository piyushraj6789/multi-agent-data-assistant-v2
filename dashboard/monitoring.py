"""Objective 4 — Live Audit Monitoring Dashboard.

Run as: streamlit run dashboard/monitoring.py
Reads the audit Delta table written by utils/audit.py. Read-only.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dashboard._data import WINDOWS, load_audit, apply_filters, render_kpi_rows
from dashboard._charts import (
    prep_df,
    chart_query_volume, chart_block_rate, chart_confidence_trend,
    chart_intent_distribution, chart_latency_by_intent,
    chart_score_distribution, chart_role_activity,
    chart_model_token_split, chart_cost_over_time,
    chart_feedback_distribution,
)

st.set_page_config(page_title="Audit Monitor", page_icon="📊", layout="wide")


def _render_query_explorer(df) -> None:
    """Three-tab interactive query explorer: recent, slowest, blocked/errors."""
    st.subheader("Query Explorer")
    tab1, tab2, tab3 = st.tabs(["Recent Queries", "Slowest Queries", "Blocked / Errors"])
    cols_base = ["ts", "question", "user_role", "intent", "eval_score", "elapsed_sec"]

    with tab1:
        kw = st.text_input("Search by keyword", placeholder="e.g. revenue, supplier…")
        view = df[cols_base].sort_values("ts", ascending=False)
        if kw:
            view = view[view["question"].fillna("").str.contains(kw, case=False)]
        st.dataframe(view.head(50), use_container_width=True)

    with tab2:
        st.dataframe(
            df[cols_base].sort_values("elapsed_sec", ascending=False).head(20),
            use_container_width=True,
        )

    with tab3:
        blocked = df[
            (df["eval_score"] == 0) | (df["error"].fillna("").str.strip() != "")
        ][["ts", "question", "user_role", "intent", "eval_score", "error"]].sort_values("ts", ascending=False)
        if blocked.empty:
            st.success("No blocked or errored queries in this window.")
        else:
            st.dataframe(blocked, use_container_width=True)


def main() -> None:
    """Entry point — renders the full monitoring dashboard."""
    st.title("📊 Audit Monitoring Dashboard")
    st.caption("Live view of query_audit_log · IST (UTC+5:30) · read-only · cache refreshes every 60 s")

    with st.sidebar:
        st.page_link("app.py", label="⬅️ Back to Assistant", use_container_width=True)
        st.markdown("---")
        st.header("Controls")
        window_label = st.selectbox("Time window", list(WINDOWS.keys()), index=0)
        st.markdown("---")
        st.subheader("Filters")

    df_raw = load_audit(WINDOWS[window_label])
    if df_raw.empty:
        st.info("No data returned. Run some queries through app.py first.")
        return

    df   = apply_filters(df_raw)
    df_t = prep_df(df)

    # ── 15 KPI tiles (3 rows × 5) ─────────────────────────────────────────────
    render_kpi_rows(df)
    st.markdown("---")

    # ── Activity charts ────────────────────────────────────────────────────────
    st.subheader("Activity")
    c1, c2 = st.columns(2)
    with c1: chart_query_volume(df_t)
    with c2: chart_block_rate(df_t)

    c3, c4 = st.columns(2)
    with c3: chart_confidence_trend(df_t)
    with c4: chart_score_distribution(df_t)

    # ── Distribution charts ────────────────────────────────────────────────────
    st.subheader("Distribution")
    c5, c6 = st.columns(2)
    with c5: chart_intent_distribution(df_t)
    with c6: chart_role_activity(df_t)

    c7, c8 = st.columns(2)
    with c7: chart_latency_by_intent(df_t)
    with c8: chart_feedback_distribution(df_t)

    # ── Model & Cost charts ────────────────────────────────────────────────────
    st.subheader("Model & Cost")
    c9, c10 = st.columns(2)
    with c9:  chart_model_token_split(df_t)
    with c10: chart_cost_over_time(df_t)

    st.markdown("---")

    # ── Query explorer ─────────────────────────────────────────────────────────
    _render_query_explorer(df)

    with st.expander("Raw audit data (all columns)"):
        st.dataframe(df_raw, use_container_width=True)


if __name__ == "__main__":
    main()
