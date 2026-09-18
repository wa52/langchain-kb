import time

from src.adapters.retrieval.current import CurrentRetrieverAdapter
from src.application.query import QueryService


def search_documents(rm, query: str, top_k: int) -> tuple[list[dict], float]:
    started = time.time()
    results = QueryService(CurrentRetrieverAdapter(rm.vector_store)).search(query, limit=top_k)
    payload = [
        {
            "source": result.chunk.source or "unknown",
            "chunk_id": result.chunk.chunk_id,
            "score": round(float(result.score or 0.0), 4),
            "content": result.chunk.content[:500],
        }
        for result in results
    ]
    return payload, round((time.time() - started) * 1000, 2)

__all__ = ["search_documents"]
