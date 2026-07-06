"""Run all 37 UAT test cases through the agent graph and print results for the UAT document."""

import os, sys, time, textwrap
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from agents.orchestrator import agent_graph

TEST_CASES = [
    # (tc_num, role, question)
    # Section 1 — Doc Lookup
    (1,  "analyst",   "What is Average Order Value?"),
    (2,  "analyst",   "What is the definition of revenue?"),
    (3,  "finance",   "How is Average Days to Ship calculated?"),
    (4,  "executive", "What does order fulfillment rate mean?"),
    (5,  "finance",   "Explain supply cost"),
    (6,  "executive", "What is supplier performance?"),
    # Section 2 — KPI Compute
    (7,  "analyst",   "What is the Average Order Value for Q1 1995?"),
    (8,  "finance",   "What is the Average Days to Ship for Q3 1996?"),
    (9,  "finance",   "What was the order fulfillment rate in 1995?"),
    (10, "executive", "What is the Average Order Value for 1996?"),
    # Section 3 — SQL Query
    (11, "finance",   "What was total revenue by nation last year?"),
    (12, "finance",   "Show monthly revenue trend for 1995"),
    (13, "analyst",   "Show monthly order count trend for 1996"),
    (14, "finance",   "Which top 5 suppliers had the highest total supply cost?"),
    (15, "executive", "Show quarterly revenue by region for 1995"),
    (16, "analyst",   "What are the top 10 orders by total price in 1995?"),
    # Section 4 — Complex SQL
    (17, "finance",   "Show cumulative revenue by month for 1996"),
    (18, "finance",   "Show monthly revenue for 1996 and the change from the previous month"),
    (19, "finance",   "Rank the top 10 nations by total revenue in 1996"),
    (20, "executive", "What percentage of total 1997 revenue did each nation contribute?"),
    (21, "finance",   "Show the 3-month moving average of monthly revenue for 1996"),
    (22, "analyst",   "Which customers placed more than 5 orders in 1996?"),
    # Section 5 — RBAC (should be blocked)
    (23, "analyst",   "What was total revenue by nation last year?"),
    (24, "analyst",   "Show me average days to ship for 1996"),
    (25, "finance",   "Show top 10 customer names by order value"),
    (26, "analyst",   "Which suppliers had the highest supply cost?"),
    # Section 6 — Guardrail
    (27, "analyst",   "give me 2+2"),
    (28, "analyst",   "who is the president of USA?"),
    (29, "analyst",   "write me a python script"),
    (30, "analyst",   "hello how are you"),
    (31, "analyst",   "what is the capital of France?"),
    # Section 7 — Edge cases (intent only)
    (32, "analyst",   "What is Average Order Value?"),
    (33, "analyst",   "What is the Average Order Value for Q1 1995?"),
    (34, "finance",   "Calculate monthly revenue for 1996"),
    (35, "finance",   "How is Average Days to Ship calculated?"),
    (36, "finance",   "Show me total revenue"),
    (37, "executive", "What was revenue last year?"),
]

SEP = "-" * 90

def summarise_answer(state: dict) -> str:
    """Return a short one-liner summary of what the agent produced."""
    error = state.get("error", "")
    if error:
        return f"ERROR: {error[:120]}"

    intent = state.get("intent", "")
    if intent == "out_of_scope":
        ans = state.get("final_answer", "")
        return f"Out-of-scope rejection: {ans[:100]}"

    df = state.get("result_df")
    answer = state.get("final_answer", "")

    parts = []
    if df is not None and hasattr(df, "__len__"):
        parts.append(f"{len(df)} rows returned")
        cols = list(df.columns)
        parts.append(f"cols={cols}")
        if len(df) > 0:
            parts.append(f"first row={df.iloc[0].to_dict()}")

    if answer:
        parts.append(f"answer={answer[:200].strip()}")

    return " | ".join(parts) if parts else "(no output)"


def run_all():
    results = []
    for tc, role, question in TEST_CASES:
        print(f"\nTC{tc:02d} [{role}] {question}")
        t0 = time.time()
        try:
            state = agent_graph.invoke({"question": question, "user_role": role})
        except Exception as e:
            state = {"question": question, "user_role": role, "error": str(e), "intent": "ERROR"}
        elapsed = round(time.time() - t0, 2)

        intent     = state.get("intent", "—")
        score      = state.get("eval_score")
        score_str  = f"{score}/5" if score is not None else "—"
        summary    = summarise_answer(state)

        print(f"  intent={intent}  score={score_str}  time={elapsed}s")
        print(f"  {textwrap.shorten(summary, 120)}")
        results.append((tc, role, question, intent, score_str, elapsed, summary))

    print(f"\n\n{'='*90}")
    print("RESULTS TABLE (copy into UAT doc)")
    print(f"{'='*90}")
    print(f"{'TC':<4} {'Role':<10} {'Intent':<14} {'Score':<8} {'Time':>6}  Summary")
    print(SEP)
    for tc, role, question, intent, score, elapsed, summary in results:
        short_q = textwrap.shorten(question, 45)
        print(f"TC{tc:<3} {role:<10} {intent:<14} {score:<8} {elapsed:>5}s  {textwrap.shorten(summary, 60)}")

    return results


if __name__ == "__main__":
    run_all()
