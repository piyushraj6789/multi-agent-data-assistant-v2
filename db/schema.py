"""Fetch live table schemas from Databricks and filter them by the user's RBAC role."""

from typing import Any

from dotenv import load_dotenv

from config.rbac import get_allowed_tables
from db.connection import get_connection

load_dotenv()

# Cache keyed by role — schema doesn't change during a session, so one fetch
# per role per process avoids N Databricks round-trips on every user query.
_schema_cache: dict[str, dict[str, Any]] = {}


def _parse_table_ref(full_name: str) -> tuple[str, str, str]:
    """Split 'catalog.schema.table' into its three parts."""
    parts = full_name.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected 'catalog.schema.table', got: '{full_name}'")
    return parts[0], parts[1], parts[2]


def get_schema_for_role(role: str) -> dict[str, Any]:
    """Return a dict of {table_name: [columns]} for every table the role may access.

    Uses a single Databricks connection for all tables and caches the result per
    role so repeated queries skip the network entirely.
    """
    if role in _schema_cache:
        return _schema_cache[role]

    allowed = get_allowed_tables(role)
    schema: dict[str, Any] = {}
    conn = get_connection()

    try:
        for full_name in allowed:
            catalog, db_schema, table = _parse_table_ref(full_name)
            sql = (
                f"SELECT column_name, data_type "
                f"FROM {catalog}.information_schema.columns "
                f"WHERE table_schema = '{db_schema}' AND table_name = '{table}' "
                f"ORDER BY ordinal_position"
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    schema[full_name] = [{"column": r[0], "type": r[1]} for r in rows]
            except Exception as e:
                print(f"Warning: could not fetch schema for {full_name}: {e}")
                schema[full_name] = []
    finally:
        conn.close()

    _schema_cache[role] = schema
    return schema
