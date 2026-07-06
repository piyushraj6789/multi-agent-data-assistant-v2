"""Centralised prompt templates for all LLM calls in the system."""

import textwrap


def sql_generation_prompt(user_role: str, schema_str: str, doc_context: str, question: str) -> str:
    """Build the Claude Haiku prompt for generating a Databricks SQL query."""
    return textwrap.dedent(f"""
        You are a Databricks SQL expert.

        User role: {user_role}
        Allowed tables ONLY (do not query anything else):
        {schema_str}

        Business context from documentation:
        {doc_context}

        IMPORTANT — Dataset date range:
        The samples.tpch dataset contains data with order dates between 1992 and 1998.
        There is NO data beyond 1998. Interpret relative time references against 1998.
        For example: "last year" → 1997, "this year" → 1998, "recent 2 years" → 1997–1998.
        Never use CURRENT_DATE or NOW() for date filtering on this dataset.

        Rules:
        - CRITICAL: Use ONLY the tables listed in the schema above. Never reference a table that
          is not explicitly listed, even if the query seems to logically require it.
          If a join path through an unavailable table comes to mind, find an alternative path
          using only the tables you have been given.
        - Use fully qualified names: catalog.schema.table
        - Databricks SQL syntax only
        - SELECT queries only, no mutations
        - Do NOT add filters the user did not explicitly request
        - Return ONLY the SQL query, no explanation or markdown

        Ranking rules:
        - For "top N" questions: use ORDER BY <metric> DESC LIMIT N — do NOT add RANK()
        - Only add a RANK() column when the question explicitly uses the word "rank":
          wrap in a subquery so the alias is resolvable:
          SELECT rank, name, metric FROM (
            SELECT RANK() OVER (ORDER BY SUM(...) DESC) AS rank, name, SUM(...) AS metric ...
            GROUP BY name
          ) ORDER BY rank LIMIT N
        - Place the rank column first in the SELECT list

        Trend and time-series rules:
        - Use DATE_TRUNC('month', col) or DATE_TRUNC('year', col) for time grouping
        - Use YEAR(col), MONTH(col) for date part extraction
        - Always ORDER BY the time column ASC for trend queries

        Question: {question}

        SQL:
    """).strip()


def doc_answer_prompt(doc_context: str, question: str) -> str:
    """Build the prompt for answering a definition question from PDF context."""
    return textwrap.dedent(f"""
        Answer the following question using ONLY the context below.
        Always follow this exact output format — no extra sections, no deviations:

        **[Metric or Term Name]** is [one-sentence definition].

        **Formula:** [formula if mentioned in context, otherwise omit this line]

        **Tables used:** [comma-separated table names if mentioned in context, otherwise omit this line]

        **Interpretation:** [one sentence on what the value means for a business user]

        Rules:
        - Include "Formula:" only if a formula appears in the context
        - Include "Tables used:" only if specific table names appear in the context
        - Use plain English; the audience is a non-technical business user
        - Do NOT add any sections beyond the four above

        Context:
        {doc_context}

        Question: {question}

        Answer:
    """).strip()


def table_name_prompt(table_list: str, question: str) -> str:
    """Build the prompt for resolving a table name from the user's question."""
    return textwrap.dedent(f"""
        Available Databricks tables for this user:
        {table_list}

        Which single table is the user referring to?
        Question: "{question}"

        Rules:
        - Return ONLY the full table name exactly as listed above (e.g. 'samples.tpch.orders')
        - If no table clearly matches, return 'unknown'
    """).strip()


def dataframe_summary_prompt(table_str: str, question: str) -> str:
    """Build the prompt for summarising a SQL result DataFrame in plain English."""
    return textwrap.dedent(f"""
        Summarise these query results in 2-3 sentences for a business user:

        {table_str}

        Original question: {question}
    """).strip()


def relevance_score_prompt(question: str, answer: str, has_data: bool = False) -> str:
    """Build the LLM-as-judge prompt for scoring answer relevance (1–5)."""
    data_note = (
        "Note: the answer is a text summary of a data table that was also shown to the user. "
        "If the summary describes data that matches the question topic, score it 4 or 5.\n\n"
        if has_data else ""
    )
    return textwrap.dedent(f"""
        Rate the relevance of this answer to the question on a scale of 1-5.
        5=Directly and completely answers  4=Mostly answers  3=Partially
        2=Tangentially related  1=Irrelevant or empty

        {data_note}Question: {question}
        Answer: {answer[:400]}

        Return ONLY a single digit (1-5).
    """).strip()


def sql_fix_prompt(sql: str, error: str, question: str) -> str:
    """Build the prompt for asking Claude Haiku to fix a broken SQL query."""
    return textwrap.dedent(f"""
        Fix this Databricks SQL:
        {sql}

        Error: {error}
        Question: {question}

        Return ONLY the corrected SQL.
    """).strip()


def kpi_formula_extract_prompt(doc_context: str, question: str) -> str:
    """Step 1 of kpi_agent: extract the KPI formula from PDF context."""
    return textwrap.dedent(f"""
        From the documentation below, extract the calculation formula for the KPI
        the user is asking about.

        Documentation:
        {doc_context}

        Question: {question}

        Return ONLY a concise formula description.
        Example: "AOV = SUM(o_totalprice) / COUNT(o_orderkey)"
        If no formula is found, return: "Formula not found in documentation."
    """).strip()


def kpi_sql_prompt(kpi_formula: str, schema_str: str, question: str) -> str:
    """Step 2 of kpi_agent: generate SQL using the extracted KPI formula and time filter."""
    return textwrap.dedent(f"""
        You are a Databricks SQL expert. Compute a KPI for a specific time period.

        KPI formula to implement:
        {kpi_formula}

        Available tables and columns (use ONLY these):
        {schema_str}

        IMPORTANT — Dataset date range:
        The samples.tpch dataset contains data with order dates between 1992 and 1998.
        Never use CURRENT_DATE or NOW().
        Q1 = Jan–Mar, Q2 = Apr–Jun, Q3 = Jul–Sep, Q4 = Oct–Dec.

        Rules:
        - Translate the formula above into SQL using the schema provided
        - Apply the exact time filter from the question
        - Use fully qualified table names: catalog.schema.table
        - Databricks SQL syntax only, SELECT queries only
        - Return ONLY the SQL query, no explanation
        - For percentage/rate formulas use explicit CASE WHEN, NOT boolean casting:
          CORRECT: SUM(CASE WHEN col = 'F' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
          WRONG:   COUNT(col = 'F') / COUNT(*) * 100

        Question: {question}

        SQL:
    """).strip()
