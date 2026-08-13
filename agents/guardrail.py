"""Guardrail node: reject queries unrelated to the TPC-H business domain before
they reach ChromaDB or Databricks."""

from agents.state import AgentState

# At least one of these must appear in the question for it to be considered
# relevant to the TPC-H analytics platform.
DOMAIN_KEYWORDS: list[str] = [
    # TPC-H tables / entities
    "order", "lineitem", "line item", "customer", "supplier",
    "nation", "region", "part", "partsupp",
    # Business / financial terms
    "revenue", "sale", "sales", "price", "discount", "cost",
    "supply", "ship", "shipment", "delivery", "fulfillment",
    # Named KPIs
    "aov", "kpi", "metric",
    "average order value", "days to ship", "order count",
    "fulfillment rate", "supply cost", "order value",
    # Analytical / reporting terms
    "trend", "monthly", "quarterly", "yearly", "annual",
    "by month", "by year", "by quarter",
    "top", "rank", "total", "sum", "average",
    # Business context
    "market", "segment", "data", "query", "database",
    "analytics", "report", "dashboard",
    # Dataset identifiers
    "tpch", "tpc-h", "databricks",
]

# Definition-style questions ("what is X?") get a pass — UNLESS the subject
# is clearly outside the business-data domain (weather, sports, etc.).
DOC_KEYWORDS: list[str] = [
    "what is", "what was", "define", "definition",
    "how is", "what does", "explain", "meaning of", "describe",
]

# Questions containing any of these AND no domain term are rejected immediately.
OFF_TOPIC_MARKERS: list[str] = [
    "weather", "forecast", "temperature", "rain", "snow", "sunny",
    "sport", "cricket", "football", "soccer", "basketball", "tennis",
    "movie", "film", "actor", "actress", "celebrity", "song", "music",
    "recipe", "food", "restaurant", "cooking", "travel", "hotel",
    "politics", "election", "president", "government",
    "stock price", "bitcoin", "crypto",
]

# Requests for code/scripts/tooling still mention domain words (e.g. "write a
# Python script to scrape TPC-H data") but aren't a question about the data
# itself — they'd otherwise pass has_domain and only get rejected two SQL
# self-correction attempts later, wasting API calls. Same override pattern as
# OFF_TOPIC_MARKERS: blocks regardless of domain keywords present.
NON_DATA_REQUEST_MARKERS: list[str] = [
    "write a script", "write a python", "write code", "write a program",
    "build an app", "build a script", "web scraping", "scrape", "scraper",
]

_OUT_OF_SCOPE_MSG = (
    "I'm a data assistant for the TPC-H analytics platform. "
    "I can only answer questions about orders, revenue, customers, "
    "suppliers, nations, and related business metrics. "
    "Please ask something related to the data."
)


def check_relevance(state: AgentState) -> AgentState:
    """Block queries with no TPC-H domain terms; let definition questions pass."""
    q = state["question"].lower()

    has_domain      = any(kw in q for kw in DOMAIN_KEYWORDS)
    has_doc         = any(kw in q for kw in DOC_KEYWORDS)
    is_off_topic    = any(kw in q for kw in OFF_TOPIC_MARKERS)
    is_non_data_req = any(kw in q for kw in NON_DATA_REQUEST_MARKERS)

    # Off-topic markers always block — even when domain words appear incidentally
    # ("weather forecast for the orders region" is still a weather question).
    # Same for code/script requests ("write a Python script to scrape TPC-H
    # data" mentions the dataset but isn't a data question).
    if is_off_topic or is_non_data_req:
        return {**state, "intent": "out_of_scope", "final_answer": _OUT_OF_SCOPE_MSG}

    if has_domain or has_doc:
        return state  # relevant — proceed normally

    # A prior turn in this session only reaches history once it passed the
    # guardrail (out_of_scope questions end the graph before format_response
    # appends to history). So a non-empty history means the conversation is
    # already anchored in-domain, and short follow-ups like "for last year?"
    # or "and last quarter?" carry no domain keyword of their own but still
    # refer back to that anchor — only reject them if they explicitly pivot
    # to an off-topic subject.
    if state.get("history"):
        return state

    return {**state, "intent": "out_of_scope", "final_answer": _OUT_OF_SCOPE_MSG}
