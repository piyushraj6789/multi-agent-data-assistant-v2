"""Shared Anthropic client with retry and timeout configured for the whole project.

The SDK retries on 429 (rate limit), 500, 502, 503, 529 (overloaded) using
exponential backoff with jitter. Every agent imports `llm_client` from here
instead of creating its own anthropic.Anthropic() instance.

LangSmith tracing: wrap_anthropic() makes every call through this client
(sql_agent, kpi_agent, evaluator, response_agent, ...) show up in LangSmith
automatically, nested under the LangGraph run — no changes needed at any of
the individual `llm_client.messages.create(...)` call sites. Controlled
entirely by the LANGSMITH_* env vars; if LANGSMITH_TRACING isn't set to
"true", wrap_anthropic() is a no-op passthrough and calls behave exactly as
before.
"""

import os

import anthropic
from dotenv import load_dotenv
from langsmith.wrappers import wrap_anthropic

load_dotenv()

# max_retries=4 → up to 4 automatic retries (~30 s total wait with backoff)
# timeout=60    → single request timeout in seconds
llm_client = wrap_anthropic(anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_retries=4,
    timeout=60.0,
))
