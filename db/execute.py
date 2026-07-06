"""Execute SQL on Databricks with an automatic self-correction loop on failure."""

import re

import pandas as pd
from config.prompts import sql_fix_prompt
from config.settings import APP_MODEL, APP_MAX_TOKENS_FIX
from db.connection import get_connection
from utils.llm_client import llm_client as _client


_BLOCKED_COMMANDS = ("DELETE", "DROP", "TRUNCATE", "UPDATE", "INSERT", "ALTER", "CREATE", "REPLACE")


def run_sql(sql: str) -> pd.DataFrame:
    """Run a SQL query on Databricks and return the result as a pandas DataFrame."""
    first_word = sql.strip().split()[0].upper() if sql.strip() else ""
    if first_word in _BLOCKED_COMMANDS:
        raise ValueError(f"Mutating command '{first_word}' is not allowed.")
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


def _ask_haiku_to_fix(sql: str, error: str, question: str):
    """Send broken SQL + error to Claude Haiku; return (corrected_sql, usage_object)."""
    response = _client.messages.create(
        model=APP_MODEL,
        max_tokens=APP_MAX_TOKENS_FIX,
        messages=[{"role": "user", "content": sql_fix_prompt(sql, error, question)}],
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
