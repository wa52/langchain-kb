import time

from src.resources import ResourceManager


def search_documents(
    rm: ResourceManager, query: str, top_k: int
) -> tuple[list[dict], float]:
    t0 = time.time()
    vs = rm.vector_store
    docs_with_scores = vs.similarity_search_with_relevance_scores(query, k=top_k)
    results = []
    for doc, score in docs_with_scores:
        chunk_id = doc.id or doc.metadata.get("chunk_id", "")
        results.append({
            "source": doc.metadata.get("source", "unknown"),
            "chunk_id": chunk_id,
            "score": round(float(score), 4),
            "content": doc.page_content[:500],
        })
    elapsed_ms = (time.time() - t0) * 1000
    return results, round(elapsed_ms, 2)
