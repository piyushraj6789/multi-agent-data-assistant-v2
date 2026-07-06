"""Role-based access control: maps each user role to the tables it may query."""

from typing import TypedDict


class RoleConfig(TypedDict):
    allowed_tables: list[str]
    description: str


ROLE_CONFIG: dict[str, RoleConfig] = {
    "analyst": {
        "allowed_tables": [
            "samples.tpch.orders",
            "samples.tpch.customer",
            "samples.tpch.nation",
            "samples.tpch.region",
        ],
        "description": "Sales and customer data only",
    },
    "finance": {
        "allowed_tables": [
            "samples.tpch.orders",
            "samples.tpch.lineitem",
            "samples.tpch.supplier",
            "samples.tpch.partsupp",
            "samples.tpch.nation",
            "samples.tpch.part",
        ],
        "description": "Financial and supply chain data",
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
            "samples.tpch.partsupp",
        ],
        "description": "Full access to all tables",
    },
}


def get_allowed_tables(role: str) -> list[str]:
    """Return the list of tables the given role is permitted to query."""
    if role not in ROLE_CONFIG:
        raise ValueError(f"Unknown role '{role}'. Valid roles: {list(ROLE_CONFIG)}")
    return ROLE_CONFIG[role]["allowed_tables"]


# Maps question-level concepts to the tables they semantically require.
# Used by sql_agent to block questions whose meaning can't be preserved using
# only the role's allowed tables (i.e. an LLM workaround would give wrong data).
METRIC_TABLE_REQUIREMENTS: dict[str, list[str]] = {
    "revenue":       ["samples.tpch.lineitem"],
    "days to ship":  ["samples.tpch.lineitem"],
    "average days":  ["samples.tpch.lineitem"],
    "supply cost":   ["samples.tpch.partsupp"],
    "supplier cost": ["samples.tpch.partsupp"],
}


def check_metric_access(question: str, user_role: str) -> None:
    """Raise PermissionError if the question requires a table the role cannot access.

    Applied to sql_query intent only — prevents RBAC bypass via proxy columns.
    """
    allowed = set(get_allowed_tables(user_role))
    q = question.lower()
    for metric, required_tables in METRIC_TABLE_REQUIREMENTS.items():
        if metric in q:
            blocked = [t for t in required_tables if t not in allowed]
            if blocked:
                raise PermissionError(
                    f"RBAC violation: '{metric}' requires {blocked} "
                    f"which role '{user_role}' cannot access."
                )
