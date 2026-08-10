"""Classify user questions into one of three intents using a trained ML model.

TF-IDF + Logistic Regression pipeline, trained offline in
data/train_intent_classifier.py on data/intent_training_data.json (~1000
LLM-generated + real UAT examples). Replaces the keyword-rule classifier,
which is kept at agents/intent_classifier_keyword.py for comparison — see
that file's docstring and the training script's printed accuracy report.

An earlier version of this file also layered a hand-written history-aware
override on top for context-free follow-ups (e.g. "calculate it for last
year?"). That version was removed: the trained model already routes bare
follow-up fragments to the right intent on its own, and the override was
actively wrong on other cases — e.g. "How is it calculated?" is textbook
doc_lookup phrasing that the override force-routed to kpi_compute.

One narrower override remains below (_is_bare_kpi_continuation): the model
has no access to conversation history, so a question like "compare 1995 vs
1996" right after an AOV conversation is genuinely ambiguous from text
alone (46% kpi_compute vs 49% sql_query) — "compare" reads as an ad-hoc
aggregation cue in the training data. The override only fires when the
model's own top call was sql_query, the prior turn was a KPI computation,
and the question names no ad-hoc entity of its own (nation/region/supplier/
etc.) — i.e. there's nothing else for it to be about. A question like
"compare revenue by nation for 1995 vs 1996" is left alone: it introduces
its own grouping dimension and the model is confidently right (69%)."""

import os
import re

import joblib

from agents.state import AgentState

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "intent_classifier.pkl")
_pipeline = joblib.load(_MODEL_PATH)

# Entities that mean the question is introducing its own ad-hoc grouping/
# filter, not just re-running the prior turn's KPI over a new time range.
_AD_HOC_ENTITY_WORDS = [
    "nation", "region", "supplier", "customer", "segment", "part", "product",
]
_MAX_CONTINUATION_WORDS = 8


def _is_bare_kpi_continuation(question: str, prior_intent: str | None) -> bool:
    """True if this looks like a short, entity-free follow-up re-running the prior KPI."""
    if prior_intent != "kpi_compute":
        return False
    words = re.findall(r"[a-z']+", question.lower())
    if len(words) > _MAX_CONTINUATION_WORDS:
        return False
    return not any(w in _AD_HOC_ENTITY_WORDS for w in words)


def classify_intent(state: AgentState) -> AgentState:
    """Set state['intent'] to doc_lookup | kpi_compute | sql_query via the trained model."""
    question = state["question"]
    intent = str(_pipeline.predict([question])[0])

    if intent == "sql_query":
        history = state.get("history") or []
        prior_intent = history[-1].get("intent") if history else None
        if _is_bare_kpi_continuation(question, prior_intent):
            intent = "kpi_compute"

    return {**state, "intent": intent}
