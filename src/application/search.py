from src.application.query import QueryService


def search_documents(query_service: QueryService, query: str, top_k: int) -> tuple[list[dict], float]:
    import time

    started = time.time()
    results = query_service.search(query, limit=top_k)
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
