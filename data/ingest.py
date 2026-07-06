"""One-time script: parse PDFs in data/docs/ and load chunks into ChromaDB."""

import json
import os
import re
import uuid

import chromadb
from pypdf import PdfReader

from config.settings import CHROMA_PATH, CHROMA_COLLECTION, DOCS_DIR

KPI_NAMES_PATH = os.path.join(os.path.dirname(DOCS_DIR), "kpi_names.json")


def _extract_text(pdf_path: str) -> str:
    """Read all pages of a PDF and return the combined text."""
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _chunk_by_sections(text: str) -> list[str]:
    """Split on numbered section headings; merge bare header lines into the next chunk.

    Why section-based over fixed-char: PyPDF produces single-newline text so
    paragraph splitting doesn't work. These PDFs are structured (each KPI / table
    is a numbered section), so splitting on headings keeps each metric definition or
    table spec in one chunk. Retrieving a complete definition is more accurate than
    retrieving two half-definitions cut at 400 chars.
    """
    # Split just before any "1.", "1.1", "2. LINEITEM", etc. followed by uppercase
    parts = re.split(r'\n(?=\d+[\.\d]*\s+[A-Z])', text)
    parts = [p.strip() for p in parts if p.strip()]

    chunks: list[str] = []
    carry = ""
    for part in parts:
        combined = (carry + "\n" + part).strip() if carry else part
        if len(part) < 80:  # bare section header with no content yet — carry forward
            carry = combined
        else:
            chunks.append(combined)
            carry = ""
    if carry:
        chunks.append(carry)

    return [c for c in chunks if len(c) > 30]


def _extract_kpi_names(text: str) -> list[str]:
    """Extract KPI names from two-level section headings (e.g. '1.1 Gross Revenue')."""
    names: list[str] = []
    for match in re.finditer(r'\d+\.\d+\s+([A-Z][A-Za-z ()/\-]+)', text):
        raw = match.group(1).strip()
        acronym = re.search(r'\(([A-Z]{2,})\)', raw)
        if acronym:
            names.append(acronym.group(1).lower())
        clean = re.sub(r'\s*\([^)]*\)', '', raw).strip().lower()
        for part in re.split(r'\s*/\s*', clean):   # "Region / Nation" → two entries
            part = part.strip()
            if len(part.split()) >= 2:              # require at least 2 words — avoids generic singles like "nation"
                names.append(part)
    return list(dict.fromkeys(names))   # deduplicate, preserve order


def ingest_pdfs() -> None:
    """Load every PDF in data/docs/, chunk it, and upsert chunks into ChromaDB."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Drop and recreate so re-runs don't accumulate duplicate chunks
    try:
        client.delete_collection(CHROMA_COLLECTION)
        print(f"Deleted existing collection '{CHROMA_COLLECTION}'")
    except Exception:
        pass
    collection = client.create_collection(CHROMA_COLLECTION)

    pdf_files = [
        f for f in os.listdir(DOCS_DIR)
        if f.endswith(".pdf") and os.path.isfile(os.path.join(DOCS_DIR, f))
    ]
    if not pdf_files:
        print(f"No PDF files found in {DOCS_DIR}/")
        return

    all_text = ""
    for filename in pdf_files:
        path = os.path.join(DOCS_DIR, filename)
        print(f"Ingesting {filename}...")

        text = _extract_text(path)
        all_text += text + "\n"
        chunks = _chunk_by_sections(text)

        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"source": filename, "chunk_index": i} for i, _ in enumerate(chunks)]

        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
        print(f"  Added {len(chunks)} chunks from {filename}")

    kpi_names = _extract_kpi_names(all_text)
    with open(KPI_NAMES_PATH, "w") as f:
        json.dump(kpi_names, f, indent=2)
    print(f"Saved {len(kpi_names)} KPI names to {KPI_NAMES_PATH}")

    print(f"\nDone. Collection '{CHROMA_COLLECTION}' now has {collection.count()} total chunks.")


if __name__ == "__main__":
    ingest_pdfs()
