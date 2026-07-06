"""Shared Anthropic client with retry and timeout configured for the whole project.

The SDK retries on 429 (rate limit), 500, 502, 503, 529 (overloaded) using
exponential backoff with jitter. Every agent imports `llm_client` from here
instead of creating its own anthropic.Anthropic() instance.
"""

import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

# max_retries=4 → up to 4 automatic retries (~30 s total wait with backoff)
# timeout=60    → single request timeout in seconds
llm_client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_retries=4,
    timeout=60.0,
)
