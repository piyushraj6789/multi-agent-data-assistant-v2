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

_OUT_OF_SCOPE_MSG = (
    "I'm a data assistant for the TPC-H analytics platform. "
    "I can only answer questions about orders, revenue, customers, "
    "suppliers, nations, and related business metrics. "
    "Please ask something related to the data."
)


def check_relevance(state: AgentState) -> AgentState:
    """Block queries with no TPC-H domain terms; let definition questions pass."""
    q = state["question"].lower()

    has_domain   = any(kw in q for kw in DOMAIN_KEYWORDS)
    has_doc      = any(kw in q for kw in DOC_KEYWORDS)
    is_off_topic = any(kw in q for kw in OFF_TOPIC_MARKERS)

    # Off-topic markers always block — even when domain words appear incidentally
    # ("weather forecast for the orders region" is still a weather question).
    if is_off_topic:
        return {**state, "intent": "out_of_scope", "final_answer": _OUT_OF_SCOPE_MSG}

    if has_domain or has_doc:
        return state  # relevant — proceed normally

    return {**state, "intent": "out_of_scope", "final_answer": _OUT_OF_SCOPE_MSG}
