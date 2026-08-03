"""Retrieve relevant PDF chunks from ChromaDB based on the user's question."""

import chromadb

from agents.state import AgentState
from config.settings import CHROMA_PATH, CHROMA_COLLECTION, CHROMA_N_RESULTS

# Module-level singleton — PersistentClient reads the SQLite index on init,
# so creating it fresh on every query wastes 1-3s. One init per process.
_collection: chromadb.Collection | None = None


def _get_collection() -> chromadb.Collection:
    """Return the cached ChromaDB collection, initialising it once on first call."""
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_collection(CHROMA_COLLECTION)
    return _collection


def retrieve_context(state: AgentState) -> AgentState:
    """Query ChromaDB with the user's question and store top chunks in state['doc_context']."""
    question = state["question"]

    try:
        from agents.sanitizer import sanitize_text
        collection = _get_collection()
        results = collection.query(query_texts=[question], n_results=CHROMA_N_RESULTS)
        # Objective 2a: sanitize each retrieved chunk before it reaches any LLM prompt.
        chunks: list[str] = [sanitize_text(c, max_chars=1000) for c in results["documents"][0]]
        doc_context = "\n\n---\n\n".join(chunks)
    except Exception as e:
        print(f"Warning: ChromaDB retrieval failed: {e}")
        doc_context = ""

    return {**state, "doc_context": doc_context}
