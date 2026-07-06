"""Databricks connection factory — reads credentials from .env and returns a live connection."""

import os

from databricks import sql
from databricks.sql.client import Connection
from dotenv import load_dotenv

load_dotenv()


def get_connection() -> Connection:
    """Open and return a Databricks SQL connection using env-var credentials."""
    host = os.getenv("DATABRICKS_HOST")
    token = os.getenv("DATABRICKS_TOKEN")
    http_path = os.getenv("DATABRICKS_HTTP_PATH")

    if not all([host, token, http_path]):
        missing = [k for k, v in {
            "DATABRICKS_HOST": host,
            "DATABRICKS_TOKEN": token,
            "DATABRICKS_HTTP_PATH": http_path,
        }.items() if not v]
        raise EnvironmentError(f"Missing required env vars: {missing}")

    try:
        conn = sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        )
        return conn
    except Exception as e:
        raise ConnectionError(f"Failed to connect to Databricks: {e}") from e
