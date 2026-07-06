# Multi-Agent Data Assistant — Project Context for Claude Code

## Who I Am
- MSc Artificial Intelligence student at REVA University (RACE), Bengaluru
- Building this as Capstone 1 project (AI-08)
- Timeline: 2–3 weeks
- I need to understand every file you write — explain what each function does
- Do not over-engineer. Keep files under 100 lines where possible

---

## Project Goal
Build a multi-agent natural language assistant that lets non-technical users
query a Databricks analytics database by typing plain English questions.
The system routes questions to the right agent, retrieves context from PDFs,
generates validated SQL via Claude Haiku, executes on Databricks, and returns
results with a simple chart.

---

## Tech Stack — Use These Exactly, No Substitutions

| Layer | Tool | Notes |
|---|---|---|
| UI | Streamlit | Chat interface with role selector sidebar |
| Agent orchestration | LangGraph (StateGraph) | 3-week deadline, keep graph simple |
| LLM for SQL generation | Claude Haiku (`claude-haiku-4-5-20251001`) | Cheapest, fastest, good SQL accuracy |
| Vector DB | ChromaDB (local persistent) | Path: `data/chroma_db/` |
| Database | Databricks Community Edition | Dataset: `samples.tpch` (pre-loaded, free) |
| DB connector | `databricks-sql-connector` | Not Spark, not JDBC |
| PDF parsing | `pypdf` | Not pdfplumber, not PyMuPDF |
| Env management | `python-dotenv` | Load from `.env` file |
| Language | Python 3.10+ | Use type hints everywhere |

---

## Project Structure — Do Not Deviate From This

```
Capstone1_Implementation/
│
├── CLAUDE.md                   ← this file
├── .env                        ← secrets, never commit
├── .env.example                ← safe to commit
├── .gitignore
├── requirements.txt
├── test.ipynb                  ← scratch notebook
│
├── app.py                      ← Streamlit entry point
│
├── agents/
│   ├── __init__.py
│   ├── state.py                ← AgentState TypedDict
│   ├── orchestrator.py         ← LangGraph StateGraph
│   ├── guardrail.py            ← domain relevance check, first node, no API call
│   ├── intent_classifier.py    ← keyword routing, no API calls (3 intents)
│   ├── retrieval_agent.py      ← ChromaDB semantic search (module-level singleton)
│   ├── sql_agent.py            ← Claude Haiku SQL generation
│   ├── kpi_agent.py            ← hybrid RAG+SQL: extract formula → compute SQL
│   ├── response_agent.py       ← format final answer
│   └── evaluator.py            ← inline LLM-as-judge scoring node
│
├── db/
│   ├── __init__.py
│   ├── connection.py           ← get_connection() only
│   ├── schema.py               ← live schema pull + RBAC filter
│   └── execute.py              ← run_sql + self-correction loop
│
├── data/
│   ├── ingest.py               ← one-time PDF ingestion script
│   ├── chroma_db/              ← auto-created by ChromaDB
│   └── docs/
│       ├── metrics_definitions.pdf
│       └── data_dictionary.pdf
│
├── config/
│   ├── __init__.py
│   ├── rbac.py                 ← role → allowed tables mapping
│   ├── settings.py             ← model name + token limits + audit table name
│   └── prompts.py              ← centralised LLM prompt builder functions
│
├── utils/
│   ├── __init__.py
│   └── audit.py                ← Databricks Delta audit logger (token tracking + query log)
│
├── evaluation/
│   ├── __init__.py
│   ├── test_cases.py           ← 7 test cases (UC1–UC7)
│   ├── scorer.py               ← rule-based KPI scoring functions
│   └── run_eval.py             ← offline eval runner, reports 5 KPIs
│
├── tests/
│   └── test_graph.py           ← end-to-end test for 3 use cases
│
└── documentation/
    └── architecture.md         ← full architecture doc with diagrams
```

---

## Environment Variables

```bash
# .env — never commit this file
ANTHROPIC_API_KEY=sk-ant-api03-xxxx
DATABRICKS_HOST=community.cloud.databricks.com
DATABRICKS_TOKEN=dapi-xxxx
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/xxxx
```

Always load with:
```python
from dotenv import load_dotenv
load_dotenv()
```

---

## RBAC Configuration

Three roles. Enforced by filtering schema context sent to LLM.
Do NOT send tables to the LLM that the user's role cannot access.

```python
ROLE_CONFIG = {
    "analyst": {
        "allowed_tables": [
            "samples.tpch.orders",
            "samples.tpch.customer",
            "samples.tpch.nation",
            "samples.tpch.region"
        ],
        "description": "Sales and customer data only"
    },
    "finance": {
        "allowed_tables": [
            "samples.tpch.orders",
            "samples.tpch.lineitem",
            "samples.tpch.supplier",
            "samples.tpch.partsupp",
            "samples.tpch.nation",
            "samples.tpch.part"
        ],
        "description": "Financial and supply chain data"
    },
    "executive": {
        "allowed_tables": [
            "samples.tpch.orders",
            "samples.tpch.lineitem",
            "samples.tpch.customer",
            "samples.tpch.supplier",
            "samples.tpch.nation",
            "samples.tpch.region",
            "samples.tpch.part",
            "samples.tpch.partsupp"
        ],
        "description": "Full access to all tables"
    }
}
```

---

## LangGraph Agent State

```python
class AgentState(TypedDict):
    question: str         # user's original question
    user_role: str        # analyst | finance | executive
    intent: str           # doc_lookup | kpi_compute | sql_query | out_of_scope
    doc_context: str      # retrieved PDF chunks
    schema: dict          # live schema from Databricks, filtered by role
    generated_sql: str    # SQL produced by Claude Haiku
    result_df: object     # pandas DataFrame from Databricks
    final_answer: str     # text answer for doc_lookup intent
    error: str            # error message if something fails
    eval_score: int       # 0-5 confidence score from evaluator (0 = RBAC blocked)
    eval_notes: list      # flags e.g. ["empty result", "low relevance"]
    token_usage: dict     # {total_input, total_output, calls:[{step, input, output}]}
    kpi_formula: str      # KPI formula extracted from PDF (kpi_compute path only)
```

---

## Agent Routing Logic

```
question
  → guardrail (keyword check, no API call, ~0ms)
      ├── "out_of_scope" → END  (no ChromaDB, no Databricks hit)
      └── relevant
            → intent_classifier (keyword rules, no API call)
                ├── "kpi_compute"  → retrieve_context → load_schema → kpi_agent → END
                ├── "doc_lookup"   → retrieve_context → load_schema → doc_answer → END
                └── "sql_query"    → retrieve_context → load_schema → sql_agent → END
```

### Intent classification keywords

```python
doc_keywords      = ["what is", "define", "definition", "how is",
                     "what does", "explain", "meaning of", "describe"]

sql_override      = ["total", "count", "sum", "how many", "show me", "list",
                     "per", "top", "rank", "group", "aggregate", "compute",
                     "trend", "monthly", "quarterly", "yearly", "over time"]

time_qualifiers   = ["for q1/q2/q3/q4", "in 199x", "last year/quarter/month", ...]

# Priority: sql_override → (doc + time → kpi_compute) → doc_lookup → sql_query
```

---

## Prompt Templates — Centralised in `config/prompts.py`

All LLM prompt strings live in `config/prompts.py` as builder functions. Never write prompt strings inline in agent files — always import from here.

```python
# config/prompts.py — 8 builder functions
from config.prompts import (
    sql_generation_prompt,       # sql_agent.py
    doc_answer_prompt,           # orchestrator.py (answer_doc_question node)
    dataframe_summary_prompt,    # response_agent.py
    relevance_score_prompt,      # evaluator.py — accepts has_data flag
    sql_fix_prompt,              # db/execute.py
    kpi_formula_extract_prompt,  # kpi_agent.py (Step 1)
    kpi_sql_prompt,              # kpi_agent.py (Step 2)
)
```

Each function uses `textwrap.dedent(f"""...""").strip()` for clean multi-line strings. Example:

```python
import textwrap

def sql_generation_prompt(user_role, schema_str, doc_context, question):
    return textwrap.dedent(f"""
        You are a Databricks SQL expert.
        User role: {user_role}
        Allowed tables ONLY: {schema_str}
        ...
        TPCH date range 1992–1998 — never use CURRENT_DATE
        Trend rules: DATE_TRUNC, YEAR/MONTH, ORDER BY ASC
        SQL:
    """).strip()
```

---

## Self-Correction Loop (Critical Feature)

When SQL fails on Databricks, send the error back to Claude Haiku to fix it.
Maximum 2 retries. This is a key differentiator from prior work.

```python
from config.settings import APP_MODEL, APP_MAX_TOKENS_FIX
from config.prompts import sql_fix_prompt

def run_with_correction(sql, original_question, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            return run_sql(sql)
        except Exception as e:
            if attempt == max_retries:
                raise
            fix_response = client.messages.create(
                model=APP_MODEL,
                max_tokens=APP_MAX_TOKENS_FIX,
                messages=[{"role": "user", "content":
                    sql_fix_prompt(sql, str(e), original_question)}]
            )
            sql = extract_sql(fix_response.content[0].text)
```

---

## ChromaDB Setup

All ChromaDB and ingestion constants are centralised in `config/settings.py`.
Do not hardcode paths or collection names in individual files.

```python
# config/settings.py — single source of truth
CHROMA_PATH       = "data/chroma_db"
CHROMA_COLLECTION = "knowledge_base"
CHROMA_N_RESULTS  = 3
DOCS_DIR          = "data/docs"
CHUNK_SIZE        = 800   # reference value; section splitter uses regex not char count
CHUNK_OVERLAP     = 0     # section boundaries are natural delimiters

# Ingestion (run once via: python -m data.ingest from project root)
# Chunking strategy: regex split on numbered headings (1.1 Total Revenue, 2. LINEITEM, etc.)
# Result: ~20 semantically complete chunks vs 57 fragmented character-split chunks previously

# Retrieval (in retrieval_agent.py) — uses a module-level singleton to avoid
# re-initialising PersistentClient (SQLite read + HNSW load) on every query
_collection: chromadb.Collection | None = None
def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_collection(CHROMA_COLLECTION)
    return _collection
```

PDF source files: `data/docs/metrics_definitions.pdf`,
`data/docs/data_dictionary.pdf`

---

## Three Use Cases to Demo (Build and Test These)

UC4 (Data Freshness) and UC5 (Schema Exploration) were removed — they are
technical/DBA concerns, not business persona questions. Scope reduced to 3.

### UC1 — KPI Definition Lookup
- Role: analyst
- Question: `"What is Average Order Value?"`
- Expected intent: `doc_lookup`
- Tests: RAG retrieval + doc answer agent

### UC2 — KPI Computation
- Role: finance
- Question: `"What is the Average Days to Ship for Q3 1996?"`
- Expected intent: `kpi_compute`
- Tests: Hybrid RAG+SQL — formula extracted from PDF → SQL with Q3 1996 time filter → DataFrame → summary

### UC3 — NL-SQL Query
- Role: finance
- Question: `"What was total revenue by nation last year?"`
- Expected intent: `sql_query`
- Expected SQL joins: `lineitem` + `orders` + `nation`
- Tests: SQL agent + self-correction + chart rendering

---

## Evaluation Plan (Week 3)

Run each use case 10 times and measure:

```python
metrics = {
    "sql_accuracy":      "% of queries that execute without error",
    "intent_accuracy":   "% correctly routed to right agent",
    "answer_relevance":  "manual score 1-5 per response",
    "avg_latency_sec":   "time from question to result",
    "rbac_compliance":   "% of queries respecting role boundaries"
}
```

Use this test script pattern:
```bash
python tests/test_graph.py
```

---

## Key Differentiators From Prior Work (Ganesh Rohan, AI-07)

Mention these if asked why this project is different:

1. **Multi-agent architecture** — LangGraph routes to specialized agents.
   Prior work used a single pipeline.
2. **RBAC enforcement** — schema filtered by role before LLM sees it.
   Prior work had no access control.
3. **Live metastore integration** — schema pulled from Databricks at
   query time. Prior work used static schema files.
4. **Multi-source knowledge layer** — PDFs + metastore combined.
   Prior work used schema docs only.
5. **Inline evaluator + offline eval framework** — Every response is scored by an LLM-as-judge node (relevance 1-5) before display, with a confidence badge shown to the user. Offline suite (`evaluation/run_eval.py`) reports 5 KPIs: Intent Accuracy, RBAC Compliance, SQL Accuracy, Avg Relevance, Avg Latency. Prior work measured syntax match only, had no inline quality gate.

---

## Coding Rules for Claude Code

0. **Auto-update this file** — after every 10 messages in a conversation, update CLAUDE.md to reflect any new files created, code changes, or project decisions made during that session
1. **Explain every function** — add a one-line docstring to every function
2. **No files over 120 lines** — split if needed
3. **Test incrementally** — after each file, run a quick smoke test
4. **No unnecessary dependencies** — if it is not in requirements.txt, don't import it
5. **Type hints everywhere** — all function signatures must have types
6. **Never hardcode credentials** — always use os.getenv()
7. **Print meaningful errors** — wrap Databricks calls in try/except
   with descriptive messages
8. **One responsibility per file** — connection.py only connects,
   schema.py only fetches schema, etc.

---

## Commands Reference

```bash
# Install dependencies
pip install -r requirements.txt

# Ingest PDFs into ChromaDB (run from project root — NOT python data/ingest.py)
python -m data.ingest

# Run end-to-end test (no UI)
python tests/test_graph.py

# Run full evaluation suite (6 cases, 5 KPIs, LLM-as-judge scoring)
python evaluation/run_eval.py

# Launch Streamlit app
streamlit run app.py

# Test Databricks connection only
python -c "from db.connection import get_connection; \
           conn = get_connection(); print('Connected:', conn)"

# Test schema pull
python -c "from db.schema import get_schema_for_role; \
           import json; \
           print(json.dumps(get_schema_for_role('analyst'), indent=2))"
```

---

## What NOT to Build (Scope Control)

- ❌ No user authentication system
- ❌ No database writes or mutations
- ❌ No Confluence / SharePoint integration (mention as future scope)
- ❌ No real-time streaming responses
- ❌ No Docker / containerisation
- ❌ No deployment to cloud (run locally for demo)
- ❌ No fine-tuning of any model
- ❌ No Pygwalker (use Streamlit native charts)

---

## Viva Preparation Notes

Questions you will likely be asked and how to answer:

**"How is your project different from Ganesh Rohan's AI-07?"**
→ Multi-agent routing, RBAC enforcement, live metastore, multi-source RAG.
   AI-07 was a single pipeline with no access control and static schema files.

**"Why Claude Haiku and not GPT-4?"**
→ Cost efficiency for a capstone project. Haiku achieves comparable SQL
   accuracy at 1/20th the cost. Anthropic API also has better rate limits
   for development.

**"Why LangGraph over LangChain agents?"**
→ LangGraph gives explicit control over routing logic via a typed state
   machine. Better for debugging, easier to explain the flow, and more
   suitable for a system where routing correctness matters.

**"How does RBAC work?"**
→ The schema fed to the LLM is filtered by the user's role before the
   prompt is constructed. The SQL Agent never sees tables the user cannot
   access, so it cannot generate queries for them. Additionally, SQL is
   validated post-generation before execution.

**"What would you add with more time?"**
→ Real Unity Catalog RBAC integration, Confluence ingestion, RAGAS
   automated evaluation, and a feedback loop that improves prompts
   from user corrections.

---

## Build Status (updated as files are created)

| File | Status | Notes |
|---|---|---|
| `config/__init__.py` | ✅ Done | |
| `config/rbac.py` | ✅ Done | ROLE_CONFIG + get_allowed_tables(); analyst 4 tables, finance 6 tables (orders, lineitem, supplier, partsupp, nation, part), executive all 8 |
| `config/settings.py` | ✅ Done | Central config: APP_MODEL, 6× APP_MAX_TOKENS_*, CHROMA_PATH, CHROMA_COLLECTION, CHROMA_N_RESULTS, DOCS_DIR, CHUNK_SIZE=800, CHUNK_OVERLAP=0, AUDIT_CATALOG, AUDIT_SCHEMA, AUDIT_TABLE |
| `db/__init__.py` | ✅ Done | |
| `db/connection.py` | ✅ Done | get_connection() reads from .env |
| `db/schema.py` | ✅ Done | get_schema_for_role() via INFORMATION_SCHEMA; per-role in-memory cache (_schema_cache); single connection for all tables per call (was N connections) |
| `db/execute.py` | ✅ Done | run_sql() blocks mutating commands; run_with_correction() returns (DataFrame, fix_usages) for token tracking; _ask_haiku_to_fix() returns (sql, usage_object) |
| `agents/__init__.py` | ✅ Done | |
| `agents/state.py` | ✅ Done | AgentState TypedDict with eval_score (0-5), eval_notes, token_usage, and kpi_formula fields |
| `agents/guardrail.py` | ✅ Done | check_relevance(): keyword match against DOMAIN_KEYWORDS + DOC_KEYWORDS; sets intent="out_of_scope" and routes to END if off-topic; no API call, ~0ms; first node in both graphs |
| `agents/intent_classifier.py` | ✅ Done | 3 intents only: sql_override → (doc+time → kpi_compute) → doc_lookup → sql_query; "calculate" and "compute" removed from sql_override (caused false RBAC blocks on "how is X calculated?") |
| `agents/retrieval_agent.py` | ✅ Done | ChromaDB semantic search; module-level _collection singleton — avoids re-initialising PersistentClient on every query (saves 1–3s) |
| `agents/sql_agent.py` | ✅ Done | Haiku SQL gen + RBAC check + self-correction; captures sql_generation + sql_fix tokens into state["token_usage"] |
| `agents/kpi_agent.py` | ✅ Done | run_kpi_agent(): Step 1 _extract_formula() → kpi_formula via Haiku; Step 2 _generate_kpi_sql() → SQL using formula; executes with run_with_correction(); tokens tracked as kpi_formula + kpi_sql steps |
| `agents/response_agent.py` | ✅ Done | _summarise_dataframe() returns (text, usage); handles out_of_scope intent (yields final_answer directly, no LLM call); captures df_summary tokens into state["token_usage"] |
| `agents/evaluator.py` | ✅ Done | _score_relevance(has_data) — passes data context flag; out_of_scope intent returns score=2 immediately without LLM call; APP_MAX_TOKENS_EVAL=10 |
| `agents/orchestrator.py` | ✅ Done | guardrail is entry point; conditional edge routes out_of_scope → END, relevant → classify_intent; both batch and base graph updated |
| `agents/metadata_agent.py` | ⚠️ Unused | File exists but not imported — removed from routing (DBA use case, not business persona) |
| `agents/schema_agent.py` | ⚠️ Unused | File exists but not imported — removed from routing (DBA use case, not business persona) |
| `data/ingest.py` | ✅ Done | Section-based chunking via regex split on numbered headings (1.1 Revenue, 2. LINEITEM etc.); 20 complete chunks vs 57 fragmented ones; run with `python -m data.ingest` from project root |
| `data/docs/.gitkeep` | ✅ Done | place your PDFs here, dir tracked in git |
| `app.py` | ✅ Done | Dark-theme UI; role radio; confidence badges; _render_dataframe() with st.tabs; example questions rendered after resolving `question` (prevents layout shift / "A1 shows up again" flash); no st.rerun() after processing |
| `evaluation/__init__.py` | ✅ Done | package marker |
| `config/prompts.py` | ✅ Done | 8 prompt builder functions; relevance_score_prompt accepts has_data flag; kpi_formula_extract_prompt + kpi_sql_prompt added; table_name_prompt removed |
| `utils/__init__.py` | ✅ Done | package marker |
| `utils/audit.py` | ✅ Done | add_tokens() helper + _ensure_table() (CREATE CATALOG/SCHEMA/TABLE) + log_query() INSERT into data_assistant.audit.query_audit_log; fails silently |
| `evaluation/test_cases.py` | ✅ Done | 6 test cases: UC1–UC3 (primary, one per intent) + UC4–UC6 (supplementary: RBAC violation, supply chain SQL, metric definition) |
| `evaluation/scorer.py` | ✅ Done | score_intent, score_rbac, score_sql, aggregate_metrics — rule-based, no API calls |
| `evaluation/run_eval.py` | ✅ Done | Offline runner: invokes full graph (incl. inline evaluator) for all 6 cases; reports Intent Accuracy, RBAC Compliance, SQL Accuracy, Avg Relevance (LLM-as-judge), Avg Latency |
| `requirements.txt` | ✅ Done | pinned versions |
| `tests/test_graph.py` | ✅ Done | end-to-end UC1/UC2/UC3 tests only |
| `.env.example` | ✅ Done | safe template, commit this not .env |
| `documentation/architecture.md` | ✅ Done | Updated June 2026: guardrail node, section-based chunking, ChromaDB singleton, schema cache, latency optimisation table, intent classifier fix note |