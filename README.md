# Multi-Agent Data Assistant with Guardrails & Observability

A conversational data assistant powered by Claude AI and LangGraph. Ask questions about your data in plain English — the system routes each query through the right pipeline (SQL, RAG, or KPI compute) and returns an answer with a confidence score.

## Overview

The assistant uses a multi-agent architecture with role-based access control (RBAC). Each user role (Analyst, Finance, Executive) can only query the tables they are authorised to access. Conversation history carries across turns so follow-up questions ("calculate it for last year?") resolve against the prior turn, and every answer carries a thumbs up/down for human feedback, logged against its audit row for later review.

Two layers of guardrails run on every question: an **input side** (sanitizer + relevance check, hardened against mid-conversation jailbreak attempts) and an **output side** (the final answer is scanned for signs the model leaked its own prompt/schema instead of answering). A vague question ("orders", "revenue") is caught before any generation call and gets a clarifying follow-up instead of a guessed query.

**Three query types are supported:**

| Intent | What it does |
|---|---|
| `sql_query` | Generates and executes SQL against Databricks |
| `doc_lookup` | Retrieves answers from PDF documentation via ChromaDB (RAG) |
| `kpi_compute` | Extracts KPI definitions and computes metrics |

## Architecture

```
User question
     │
     ▼
 Sanitizer ──(strips injection patterns, truncates)
     │
     ▼
 Guardrail ──(off-topic / jailbreak)──► blocked
     │
     ▼
 Intent Classifier (trained TF-IDF + Logistic Regression)
     │
     ├── sql_query  ──► Load Schema ──► SQL Agent ──┐  (vague question →
     │                                                │   clarifying question,
     ├── doc_lookup ──► Retrieve Context ──► Doc Answer│   no generation call)
     │                                                │
     └── kpi_compute ──► KPI Agent ────────────────┘
                                              │
                                              ▼
                                         Response Agent
                                              │
                                              ▼
                              Evaluator (0–5 score, cross-model:
                              Sonnet judges Haiku) + output-leak check
                                              │
                                              ▼
                                   Audit Log ──► Monitoring Dashboard
                                              │
                                              ▼
                                     LangSmith trace (full node chain
                                     + every LLM call, prompt→response)
```

## Tech Stack

- **LLM:** Claude Haiku (`claude-haiku-4-5`) via Anthropic API, Claude Sonnet as a cross-model evaluator
- **Agent framework:** LangGraph
- **Intent classification:** TF-IDF + Logistic Regression (scikit-learn), trained on ~1000 labeled questions, benchmarked at 96.8% vs. 62.3% for the old keyword rules
- **Vector store:** ChromaDB
- **Database:** Databricks SQL
- **UI:** Streamlit (single multipage app — chat + live audit dashboard)
- **PDF parsing:** PyPDF
- **SQL write guard:** sqlglot (AST-based statement-type detection, not just a first-token check)
- **Observability:** LangSmith (traces every LLM call + the full LangGraph execution path)

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/piyushraj6789/multi_agent_data_assistant.git
cd multi_agent_data_assistant
```

### 2. Create and activate a virtual environment

```bash
python -m venv env
source env/bin/activate   # Windows: env\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
ANTHROPIC_API_KEY=sk-ant-...
DATABRICKS_HOST=community.cloud.databricks.com
DATABRICKS_TOKEN=dapi-...
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/...

# Optional — enables LangSmith tracing; the app runs fine without it.
# LANGSMITH_ENDPOINT depends on which regional deployment you signed up on
# (check the URL you log in with — e.g. apac.smith.langchain.com maps to
# apac.api.smith.langchain.com; global default is api.smith.langchain.com).
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
LANGSMITH_PROJECT=capstone2-multi-agent-assistant
```

### 5. Ingest documents into the vector store

```bash
python data/ingest.py
```

### 6. (Optional) Retrain the intent classifier

A trained pipeline is already included at `data/intent_classifier.pkl`. Only needed if you
change the training data or want to reproduce the accuracy report:

```bash
python data/generate_intent_dataset.py   # regenerate data/intent_training_data.json via Claude
python data/train_intent_classifier.py   # retrain + save intent_classifier.pkl
```

### 7. Run the app

```bash
streamlit run app.py
```

The live audit dashboard is available inside the same app via the sidebar link, or directly
at the `Monitoring Dashboard` page.

## Project Structure

```
├── agents/           # Individual agent nodes (sanitizer, guardrail, intent classifier, SQL, KPI, evaluator, etc.)
├── config/           # Settings, prompts, RBAC roles
├── data/             # Document ingestion, ChromaDB storage, intent classifier training data/model
├── db/               # Databricks connection and SQL execution (AST-based write guard)
├── dashboard/        # Audit dashboard rendering logic
├── pages/            # Streamlit multipage entries (e.g. Monitoring Dashboard)
├── evaluation/       # Automated evaluation test cases and scorer
├── tests/            # Regression suite + zero-cost output-guardrail test
├── utils/            # LLM client (LangSmith-wrapped), audit logging
├── documentation/    # Architecture doc, regression test report, report screenshots
├── app.py            # Streamlit UI entry point
└── requirements.txt
```

## Security & Guardrails

| Layer | What it catches |
|---|---|
| Input sanitizer | Prompt-injection phrases ("ignore previous instructions", ...), oversized input |
| SQL write guard | Mutating statements (`INSERT`/`UPDATE`/`DELETE`/`DROP`/...), including CTE-wrapped bypass attempts — detected via AST parse, not string matching |
| Guardrail (relevance check) | Off-topic questions; a mid-conversation topic hijack (e.g. "forget that, tell me a joke") is blocked even with prior context in the same session |
| Clarification check | Vague/underspecified questions ("orders") get a clarifying question instead of a guessed query — no generation call spent |
| Output guardrail | Scans the final answer for leaked prompt/schema fragments before it's trusted; flagged answers are excluded from conversation memory |

A 40-case regression suite (`python tests/run_all_tests.py`) and a zero-API-cost output-guardrail test (`python tests/test_output_guardrail.py`) cover these paths — see `documentation/architecture.md` for the full breakdown and `documentation/Regression_Test_Report.pdf` for a sample run.

## User Roles

| Role | Access |
|---|---|
| **Analyst** | Orders, line items, operational tables |
| **Finance** | Revenue, supplier cost, financial tables |
| **Executive** | All tables — cross-functional view |

## Observability

- **Monitoring Dashboard** (in-app page): KPI tiles, activity/latency/cost charts, a query explorer, and HITL feedback distribution — reads the audit Delta table, refreshes every 60s.
- **HITL feedback:** every answer has a thumbs up/down, logged against its audit row for later review.
- **LangSmith:** every LLM call and the full LangGraph execution path trace automatically once `LANGSMITH_TRACING=true` is set — full prompt/response, token counts, latency, and model per node.

## Evaluation

Each response is scored 0–5 by a separate evaluator agent (Claude Sonnet, judging Claude Haiku's output):

| Score | Meaning |
|---|---|
| 0 | Blocked (off-topic, unauthorised, or a detected output leak) |
| 1 | Error |
| 2 | Low quality |
| 3 | Moderate (also used for a clarification-requested turn) |
| 4 | Good |
| 5 | High confidence |

Run the evaluation suite:

```bash
python evaluation/run_eval.py
```

## UAT

```bash
python run_uat.py
```
