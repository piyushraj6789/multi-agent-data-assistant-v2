# config/settings.py

# ── LLM ──────────────────────────────────────────────
APP_MODEL      = "claude-haiku-4-5-20251001"   # generation model (all nodes except evaluator)
APP_MODEL_EVAL = "claude-sonnet-4-6"           # Objective 3: cross-model evaluator judge
APP_MAX_TOKENS_SQL      = 600   # SQL generation
APP_MAX_TOKENS_ANSWER   = 400   # doc answer + KPI formula extraction
APP_MAX_TOKENS_FIX      = 700   # SQL self-correction — must exceed SQL limit so fixed query isn't truncated
APP_MAX_TOKENS_RESPONSE = 300   # DataFrame summary (2-3 sentences)
APP_MAX_TOKENS_EVAL     = 10    # single-digit relevance score
APP_MAX_TOKENS_TABLE    = 20    # table name extraction (metadata agent)

# Temperature per call type (Anthropic default is 1.0)
TEMP_SQL      = 0.0   # SQL must be deterministic and syntactically correct
TEMP_ANSWER   = 0.3   # doc answers and KPI summaries allow slight variation
TEMP_EVAL     = 0.0   # evaluator outputs a single digit — fully deterministic

# ── ChromaDB ─────────────────────────────────────────
CHROMA_PATH       = "data/chroma_db"
CHROMA_COLLECTION = "knowledge_base"
CHROMA_N_RESULTS  = 3

# ── PDF ingestion ─────────────────────────────────────
DOCS_DIR      = "data/docs"
CHUNK_SIZE    = 800   # max chars per paragraph-merged chunk (was 400)
CHUNK_OVERLAP = 0     # paragraph splitting preserves boundaries; overlap not needed

# ── Audit log (Databricks Delta) ───────────────────────
AUDIT_CATALOG = "data_assistant"
AUDIT_SCHEMA  = "audit"
AUDIT_TABLE   = "data_assistant.audit.query_audit_log"

# ── Conversational memory (Objective 1) ───────────────
APP_HISTORY_TURNS = 4   # max turns kept in state["history"] before oldest is trimmed

# ── Input sanitization (Objective 2a) ─────────────────
APP_MAX_INPUT_CHARS = 500   # truncation limit for user questions and retrieved text

# Patterns that indicate prompt-injection attempts.
# Each entry is a lowercase substring; matching is case-insensitive.
# Add new patterns here — do not hardcode them inside sanitizer.py.
INJECTION_PATTERNS: list[str] = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "forget previous instructions",
    "system:",
    "system prompt",
    "reveal the prompt",
    "print the prompt",
    "show me the prompt",
    "override instructions",
    "new instructions:",
    "act as",
    "you are now",
    "jailbreak",
]

# ── Output guardrail ───────────────────────────────────
# Fingerprints of OUR OWN prompt templates (config/prompts.py) — not attacker
# phrasing. If any of these show up in a generated final_answer, the model has
# echoed back part of its instructions/schema instead of answering normally.
# Deliberately distinct from INJECTION_PATTERNS above: that list catches what
# an attacker sends IN, this one catches what would leak back OUT.
PROMPT_LEAK_MARKERS: list[str] = [
    "you are a databricks sql expert",
    "allowed tables only",
    "user role:",
    "conversation history (prior turns)",
    "standard tpc-h join paths",
    "critical: use only the tables listed",
    "from the documentation below, extract",
]
