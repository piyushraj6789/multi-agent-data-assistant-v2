"""Generate a synthetic intent-classification training set via Claude.

One-time offline data-prep step (not part of the live app graph). Produces
~1000 labeled (question, intent) pairs across the three intents used by
agents/intent_classifier.py — doc_lookup, kpi_compute, sql_query — by
asking Claude Sonnet for diverse batches per class, then merges in the 38
real UAT questions from evaluation/test_cases.py so the set isn't 100%
LLM-style phrasing.

Output: data/intent_training_data.json — feeds the (separate) training
script that fits the scikit-learn classifier.

Run: python data/generate_intent_dataset.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import APP_MODEL_EVAL
from utils.llm_client import llm_client

_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(_DIR, "intent_training_data.json")
KPI_NAMES: list[str] = json.load(open(os.path.join(_DIR, "kpi_names.json")))

TARGET_PER_INTENT = 330   # 3 x 330 = 990 LLM-generated + 38 real ≈ 1028 total
BATCH_SIZE = 30
MAX_ATTEMPTS = 20

INTENT_SPECS: dict[str, dict[str, str]] = {
    "doc_lookup": {
        "description": (
            "The user is asking for a DEFINITION or EXPLANATION of a business term, "
            "KPI, or concept — not asking for a computed number. E.g. 'what is average "
            "order value?', 'how is order fulfillment rate calculated?', 'define gross revenue'."
        ),
        "notes": "Mix questions that name a specific KPI with generic business-glossary questions.",
    },
    "kpi_compute": {
        "description": (
            "The user wants a COMPUTED VALUE for a named KPI, optionally with a time "
            "filter, e.g. 'what was AOV in Q1 1998?', 'total order count last year', "
            "'gross revenue for 1996'."
        ),
        "notes": (
            "Always reference one of the known KPI names, sometimes with a time "
            "qualifier (year 1992-1998, a quarter, 'last year', 'YTD')."
        ),
    },
    "sql_query": {
        "description": (
            "The user wants an AD-HOC AGGREGATE / LOOKUP over the data, not a named "
            "KPI — e.g. 'total revenue by nation in 1997', 'top 5 suppliers by order "
            "volume', 'how many orders were placed by customers in Germany?', 'list "
            "customers in the furniture segment'. Involves grouping, filtering, "
            "ranking, or counting over entities like nation, region, customer "
            "segment, supplier, order, part."
        ),
        "notes": "Vary aggregation type (sum/count/avg/rank/compare), entity, and time range.",
    },
}

PROMPT_TEMPLATE = """You are generating training data for a 3-class intent classifier used by a \
business data-assistant chatbot over a TPC-H-style dataset (orders, customers, suppliers, \
nations, regions, parts, line items).

Generate {n} DIVERSE natural-language questions a business user (finance/ops/exec role) might \
type, that should ALL be classified as intent = "{intent}".

Intent definition: {description}
Guidance: {notes}

Known KPI names you may reference: {kpi_names}

Requirements:
- Vary sentence structure, tense, formality, and length (some short, some detailed).
- Include {n_tricky} deliberately tricky/ambiguous examples that are still clearly this intent \
on close reading (borderline phrasing, no obvious keyword cue).
- Do not repeat a question style more than twice.
- Output ONLY a JSON array of strings, no other text, no markdown fences.

Example output shape: ["question one?", "question two?", ...]
"""


def _extract_json_array(text: str) -> list[str]:
    """Strip markdown fences if present and parse the JSON array Claude returned."""
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def generate_batch(intent: str, n: int, n_tricky: int) -> list[str]:
    """One API call — ask Claude for n questions of a given intent, return the parsed list."""
    spec = INTENT_SPECS[intent]
    prompt = PROMPT_TEMPLATE.format(
        n=n, intent=intent, description=spec["description"], notes=spec["notes"],
        kpi_names=", ".join(KPI_NAMES), n_tricky=n_tricky,
    )
    resp = llm_client.messages.create(
        model=APP_MODEL_EVAL,
        max_tokens=4000,
        temperature=1.0,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    try:
        return _extract_json_array(raw)
    except json.JSONDecodeError:
        print(f"  ! failed to parse a batch for {intent} ({len(raw)} chars) — skipping")
        return []


def generate_synthetic() -> list[dict]:
    """Generate ~TARGET_PER_INTENT examples per class, deduping across batches."""
    rows: list[dict] = []
    seen: set[str] = set()

    for intent in INTENT_SPECS:
        collected = 0
        attempts = 0
        print(f"Generating {intent} …")
        while collected < TARGET_PER_INTENT and attempts < MAX_ATTEMPTS:
            attempts += 1
            n = min(BATCH_SIZE, TARGET_PER_INTENT - collected)
            questions = generate_batch(intent, n, n_tricky=max(1, n // 6))
            new = 0
            for q in questions:
                q = q.strip()
                key = q.lower()
                if q and key not in seen:
                    seen.add(key)
                    rows.append({"question": q, "intent": intent, "source": "llm_generated"})
                    collected += 1
                    new += 1
            print(f"  batch {attempts}: +{new} (total {collected}/{TARGET_PER_INTENT})")
            time.sleep(0.5)
        if collected < TARGET_PER_INTENT:
            print(f"  ! only got {collected}/{TARGET_PER_INTENT} for {intent} after {attempts} attempts")

    return rows


def load_real_examples() -> list[dict]:
    """Pull the 38 hand-labeled (question, expected_intent) pairs already in the UAT suite."""
    from evaluation.test_cases import TEST_SUITE
    return [
        {"question": c["question"], "intent": c["expected_intent"], "source": "real_uat"}
        for c in TEST_SUITE
        if c.get("expected_intent") in INTENT_SPECS
    ]


def main() -> None:
    synthetic = generate_synthetic()
    real = load_real_examples()

    seen = {r["question"].strip().lower() for r in synthetic}
    merged = synthetic + [r for r in real if r["question"].strip().lower() not in seen]

    with open(OUT_PATH, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"\nSaved {len(merged)} examples to {OUT_PATH}")
    for intent in INTENT_SPECS:
        c = sum(1 for r in merged if r["intent"] == intent)
        real_c = sum(1 for r in merged if r["intent"] == intent and r["source"] == "real_uat")
        print(f"  {intent}: {c} total ({real_c} real, {c - real_c} synthetic)")


if __name__ == "__main__":
    main()
