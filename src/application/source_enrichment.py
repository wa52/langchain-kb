"""Application service for enriching model citations with retrieval metadata."""

from collections.abc import Callable
from typing import Any


def enrich_sources(
    answer: str,
    *,
    extract_sources: Callable[[str], list[dict]],
    source_lookup: Callable[[str], dict[str, Any]],
    hit_chain: Callable[[], list[str]],
) -> list[dict]:
    """Turn citation markers into stable, transport-ready source records.

    Retrieval storage stays behind ``source_lookup``; this module only owns
    the application-level enrichment contract and is therefore independent of
    Chroma, FastAPI, and the legacy chat implementation.
    """
    sources = extract_sources(answer)
    chain = hit_chain()
    for source in sources:
        found = source_lookup(source["source"])
        source["chunk_id"] = found.get("chunk_id", "")
        source["excerpt"] = found.get("excerpt")
        source["hit_chain"] = list(chain)
    return sources
