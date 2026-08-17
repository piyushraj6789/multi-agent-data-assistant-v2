"""Objective 2a — Prompt injection sanitization.

First node in the graph. Cleans the raw user question before any other
agent touches it, and exposes sanitize_text() for reuse on PDF chunks
and DB error strings at their point of use.
"""

import re
from agents.state import AgentState
from config.settings import APP_MAX_INPUT_CHARS, INJECTION_PATTERNS, PROMPT_LEAK_MARKERS


def sanitize_text(text: str, max_chars: int = APP_MAX_INPUT_CHARS) -> str:
    """Strip injection patterns and truncate text to max_chars.

    Used both for the user question (via sanitize_input node) and for
    retrieved PDF chunks / DB error strings at their point of use.
    """
    if not text:
        return text

    # Remove known injection patterns (case-insensitive) — strip, don't replace with a
    # placeholder. Leaving "[removed]" in the text garbles the question enough that the
    # SQL generator loses schema context and picks wrong table names.
    cleaned = text
    for pattern in INJECTION_PATTERNS:
        cleaned = re.sub(re.escape(pattern), "", cleaned, flags=re.IGNORECASE)

    # Strip triple-backtick blocks embedded in user input (prompt structure attack)
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.DOTALL)

    # Clean up punctuation artifacts left by removal (e.g. ", . Show me…" → "Show me…")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)          # collapse double spaces
    cleaned = re.sub(r"^[\s,.:;!?]+", "", cleaned)     # strip leading junk
    cleaned = re.sub(r"[\s,.:;!?]+$", "", cleaned)     # strip trailing junk
    cleaned = cleaned.strip()

    # Truncate to max length — hard cap
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]

    return cleaned


def detect_prompt_leak(answer: str) -> list[str]:
    """Output guardrail: return which PROMPT_LEAK_MARKERS (if any) appear in a final answer.

    Checked by evaluator.py against the fully-assembled answer text, after streaming
    completes. Can't stop a leak from being displayed live (the streaming path yields
    tokens straight to the UI), but lets the evaluator score it, log it, and app.py
    keep it out of state["history"] so a leaked fragment can't poison a follow-up turn.
    """
    if not answer:
        return []
    low = answer.lower()
    return [marker for marker in PROMPT_LEAK_MARKERS if marker in low]


def sanitize_input(state: AgentState) -> AgentState:
    """First graph node. Sanitizes state['question'] before guardrail runs."""
    raw_question = state.get("question", "")
    clean_question = sanitize_text(raw_question)

    if clean_question != raw_question:
        print(f"[sanitizer] Question modified: original length={len(raw_question)}, "
              f"cleaned length={len(clean_question)}")

    return {**state, "question": clean_question}
