# Multi-Agent Data Assistant

A conversational data assistant powered by Claude AI and LangGraph. Ask questions about your data in plain English — the system routes each query through the right pipeline (SQL, RAG, or KPI compute) and returns an answer with a confidence score.

## Overview

The assistant uses a multi-agent architecture with role-based access control (RBAC). Each user role (Analyst, Finance, Executive) can only query the tables they are authorised to access.

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
 Guardrail ──(off-topic)──► blocked
     │
     ▼
 Intent Classifier
     │
     ├── sql_query  ──► Load Schema ──► SQL Agent ──► Response Agent
     │
     ├── doc_lookup ──► Retrieve Context ──► Doc Answer
     │
     └── kpi_compute ──► KPI Agent ──► Response Agent
                                              │
                                              ▼
                                         Evaluator (0–5 score)
                                              │
                                              ▼
                                         Audit Log
```

## Tech Stack

- **LLM:** Claude Haiku (`claude-haiku-4-5`) via Anthropic API
- **Agent framework:** LangGraph
- **Vector store:** ChromaDB
- **Database:** Databricks SQL
- **UI:** Streamlit
- **PDF parsing:** PyPDF

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
```

### 5. Ingest documents into the vector store

```bash
python data/ingest.py
```

### 6. Run the app

```bash
streamlit run app.py
```

## Project Structure

```
├── agents/           # Individual agent nodes (intent classifier, SQL, KPI, etc.)
├── config/           # Settings, prompts, RBAC roles
├── data/             # Document ingestion and ChromaDB storage
├── db/               # Databricks connection and SQL execution
├── evaluation/       # Automated evaluation test cases and scorer
├── tests/            # Unit tests
├── utils/            # LLM client, audit logging
├── app.py            # Streamlit UI entry point
└── requirements.txt
```

## User Roles

| Role | Access |
|---|---|
| **Analyst** | Orders, line items, operational tables |
| **Finance** | Revenue, supplier cost, financial tables |
| **Executive** | All tables — cross-functional view |

## Evaluation

Each response is scored 0–5 by a separate evaluator agent:

| Score | Meaning |
|---|---|
| 0 | Blocked (off-topic or unauthorised) |
| 1 | Error |
| 2 | Low quality |
| 3 | Moderate |
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
