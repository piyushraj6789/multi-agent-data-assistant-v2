"""Execute SQL on Databricks with an automatic self-correction loop on failure."""

import re
import sqlglot
import sqlglot.expressions as exp
from sqlglot.errors import ErrorLevel

import pandas as pd


class WriteGuardError(ValueError):
    """Raised when SQL contains a write/DDL operation. Never retried by the correction loop."""
from config.prompts import sql_fix_prompt
from config.settings import APP_MODEL, APP_MAX_TOKENS_FIX
from db.connection import get_connection
from utils.llm_client import llm_client as _client


# Objective 2b: AST node types that indicate a write/DDL operation.
# Walking the full AST catches these even when nested inside a WITH clause.
_BLOCKED_NODE_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,
    exp.Grant, exp.Revoke, exp.Drop, exp.Alter,
    exp.Create, exp.TruncateTable,
)

# Keyword fallback — used only when sqlglot cannot produce any AST at all.
_BLOCKED_KEYWORDS = frozenset([
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP",
    "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE",
])


def _check_write_guard(sql: str) -> None:
    """Raise ValueError if sql contains any write/DDL node in its AST.

    Objective 2b: uses ErrorLevel.WARN so Databricks-specific syntax that sqlglot
    doesn't fully understand still produces a partial AST rather than an exception.
    AST walk catches write nodes even when hidden after a WITH clause.
    Falls back to keyword scan only if sqlglot returns no tree at all.
    """
    tree = None
    try:
        tree = sqlglot.parse_one(sql, dialect="databricks", error_level=ErrorLevel.WARN)
    except Exception:
        pass  # partial-parse failed entirely; keyword fallback below

    if tree is not None:
        for node in tree.walk():
            if isinstance(node, _BLOCKED_NODE_TYPES):
                raise WriteGuardError(
                    f"Mutating statement '{type(node).__name__}' is not allowed."
                )

    # Always run keyword scan — catches mutations after a natural-language preamble
    # where sqlglot parses only the preamble and returns a non-mutation tree.
    words = {w.upper().strip("();,./!?") for w in sql.split()}
    found = words & _BLOCKED_KEYWORDS
    if found:
        raise WriteGuardError(f"Mutating command {found} is not allowed.")

    if tree is None:
        print("[write_guard] Warning: SQL could not be parsed; keyword scan passed — allowing.")


def run_sql(sql: str) -> pd.DataFrame:
    """Run a SQL query on Databricks and return the result as a pandas DataFrame."""
    _check_write_guard(sql)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(rows, columns=columns)
            # Databricks returns DECIMAL columns as Python Decimal objects (object dtype).
            # Convert any object column that contains numeric values to float64 so charts work.
            for col in df.columns:
                if df[col].dtype == object:
                    converted = pd.to_numeric(df[col], errors="ignore")
                    if converted.dtype != object:
                        df[col] = converted
            return df
    finally:
        conn.close()


def extract_sql(text: str) -> str:
    """Strip markdown fences from LLM output and return bare SQL."""
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _ask_haiku_to_fix(sql: str, error: str, question: str, schema_str: str = ""):
    """Send broken SQL + error to Claude Haiku; return (corrected_sql, usage_object).

    schema_str: role-filtered schema passed through so Haiku keeps correct table names.
    Objective 2a: DB error text is sanitized before reaching the LLM prompt.
    """
    from agents.sanitizer import sanitize_text
    safe_error = sanitize_text(error, max_chars=300)
    response = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_FIX,
        messages=[{"role": "user", "content": sql_fix_prompt(sql, safe_error, question, schema_str=schema_str)}],
    )
    return extract_sql(response.content[0].text), response.usage


def run_with_correction(
    sql: str,
    original_question: str,
    max_retries: int = 2,
) -> tuple[pd.DataFrame, list]:
    """Execute SQL, retrying up to max_retries times with Haiku-powered fixes on error.

    Returns (DataFrame, list of usage objects) — list is empty on first-attempt success.
    """
    current_sql = sql
    fix_usages: list = []

    for attempt in range(max_retries + 1):
        try:
            return run_sql(current_sql), fix_usages
        except WriteGuardError:
            raise  # never ask Haiku to "fix" a blocked write — that converts DELETE → SELECT
        except Exception as e:
            if attempt == max_retries:
                raise RuntimeError(
                    f"SQL failed after {max_retries} correction attempts.\n"
                    f"Last SQL:\n{current_sql}\n"
                    f"Last error: {e}"
                ) from e
            print(f"Attempt {attempt + 1} failed: {e}. Asking Haiku to fix…")
            current_sql, usage = _ask_haiku_to_fix(current_sql, str(e), original_question)
            fix_usages.append(usage)

    raise RuntimeError("Unexpected exit from correction loop")
