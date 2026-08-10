"""Chart rendering functions for the monitoring dashboard.

Each chart has a distinct color so the dashboard is readable at a glance.
All charts use Streamlit native elements — no additional dependencies.
"""

import streamlit as st
import pandas as pd

# One distinct color per chart topic
_BLUE   = "#3B82F6"   # volume / traffic
_RED    = "#EF4444"   # blocks / security
_GREEN  = "#10B981"   # quality / confidence
_PURPLE = "#8B5CF6"   # Haiku tokens / cost
_ORANGE = "#F97316"   # latency / performance
_AMBER  = "#F59E0B"   # intent categories
_INDIGO = "#6366F1"   # score distribution
_PINK   = "#EC4899"   # role activity
_TEAL   = "#14B8A6"   # Sonnet tokens
_ROSE   = "#F43F5E"   # total cost

# HITL feedback status triad — validated as an all-pairs-safe categorical set
# (scripts/validate_palette.js from the dataviz skill), not the single ad-hoc
# hue used per chart elsewhere in this file, since this is the one chart that
# needs 3 distinguishable colors within a single plot.
_FEEDBACK_COLORS = {
    "Correct":     "#1baf7a",
    "Incorrect":   "#eb6834",
    "No feedback": "#2a78d6",
}


def prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """Parse ts and add an 'hour' floor column for time-series grouping."""
    df = df.copy()
    df["ts"]   = pd.to_datetime(df["ts"])
    df["hour"] = df["ts"].dt.floor("H")
    return df


def chart_query_volume(df: pd.DataFrame) -> None:
    """Bar (blue): queries per hour — traffic pattern over the window."""
    st.subheader("Query Volume Over Time")
    vol = df.groupby("hour").size().reset_index(name="Queries")
    st.bar_chart(vol.set_index("hour")["Queries"], color=_BLUE)


def chart_block_rate(df: pd.DataFrame) -> None:
    """Line (red): % blocked (score=0) per hour — security signal."""
    st.subheader("Block Rate Over Time (%)")
    br = (
        df.assign(blocked=df["eval_score"] == 0)
        .groupby("hour").agg(pct=("blocked", lambda x: x.mean() * 100))
        .reset_index()
    )
    st.line_chart(br.set_index("hour")["pct"], color=_RED)


def chart_confidence_trend(df: pd.DataFrame) -> None:
    """Line (green): hourly mean eval_score — answer quality over time."""
    st.subheader("Avg Confidence Score (Hourly)")
    sc = df.groupby("hour")["eval_score"].mean().reset_index(name="Avg Score")
    st.line_chart(sc.set_index("hour")["Avg Score"], color=_GREEN)


def chart_latency_by_intent(df: pd.DataFrame) -> None:
    """Bar (orange): mean latency per intent — reveals slowest paths."""
    st.subheader("Avg Latency by Intent (s)")
    li = df.groupby("intent")["elapsed_sec"].mean().reset_index(name="Avg Latency")
    st.bar_chart(li.set_index("intent")["Avg Latency"], color=_ORANGE)


def chart_intent_distribution(df: pd.DataFrame) -> None:
    """Bar (amber): query count per intent — what users ask most."""
    st.subheader("Intent Distribution")
    ic = df["intent"].value_counts().reset_index()
    ic.columns = ["Intent", "Count"]
    st.bar_chart(ic.set_index("Intent")["Count"], color=_AMBER)


def chart_score_distribution(df: pd.DataFrame) -> None:
    """Bar (indigo): count per eval_score value 0–5 — quality histogram."""
    st.subheader("Eval Score Distribution (0–5)")
    sd = df["eval_score"].value_counts().sort_index().reset_index()
    sd.columns = ["Score", "Count"]
    sd["Score"] = sd["Score"].astype(str)
    st.bar_chart(sd.set_index("Score")["Count"], color=_INDIGO)


def chart_role_activity(df: pd.DataFrame) -> None:
    """Bar (pink): query count per role — which roles use the system most."""
    st.subheader("Query Volume by Role")
    ra = df["user_role"].value_counts().reset_index()
    ra.columns = ["Role", "Count"]
    st.bar_chart(ra.set_index("Role")["Count"], color=_PINK)


def chart_model_token_split(df: pd.DataFrame) -> None:
    """Line (purple + teal): Haiku vs Sonnet tokens per hour — model usage split."""
    st.subheader("Token Usage by Model (Hourly)")
    if "haiku_tokens" not in df.columns:
        st.caption("No token_calls data available.")
        return
    tok = (
        df.groupby("hour")[["haiku_tokens", "sonnet_tokens"]].sum()
        .rename(columns={"haiku_tokens": "Haiku (gen)", "sonnet_tokens": "Sonnet (eval)"})
        .reset_index()
    )
    st.line_chart(tok.set_index("hour"), color=[_PURPLE, _TEAL])


def chart_feedback_distribution(df: pd.DataFrame) -> None:
    """Bar (status triad): HITL thumbs feedback — correct / incorrect / not yet rated."""
    st.subheader("HITL Feedback")
    if "feedback" not in df.columns:
        st.caption("No feedback data available.")
        return
    labels = df["feedback"].map({"correct": "Correct", "incorrect": "Incorrect"}).fillna("No feedback")
    fc = (
        labels.value_counts()
        .reindex(["Correct", "Incorrect", "No feedback"], fill_value=0)
        .reset_index()
    )
    fc.columns = ["Status", "Count"]
    fc["Color"] = fc["Status"].map(_FEEDBACK_COLORS)
    st.bar_chart(fc, x="Status", y="Count", color="Color")


def chart_cost_over_time(df: pd.DataFrame) -> None:
    """Line (rose): estimated total cost ($) per hour — spend trend."""
    st.subheader("Estimated Cost Over Time ($)")
    if "haiku_cost" not in df.columns:
        st.caption("No cost data available.")
        return
    df = df.copy()
    df["total_cost"] = df["haiku_cost"] + df["sonnet_cost"]
    cost = df.groupby("hour")["total_cost"].sum().reset_index(name="Cost ($)")
    st.line_chart(cost.set_index("hour")["Cost ($)"], color=_ROSE)
