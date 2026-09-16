import time


def retrieve_documents(query: str, k: int, capability: str | None = None):
    """Application boundary for Agent-oriented hybrid retrieval."""
    from src.vector_store.service import VectorStoreService

    service = VectorStoreService()
    retriever = (
        service.get_retriever(k=k, capability=capability)
        if capability is not None
        else service.get_retriever(k=k)
    )
    return retriever.invoke(query)


def retrieve_graph(query: str) -> str:
    """Application boundary for graph lookup."""
    from src.graph_store.service import GraphService

    return GraphService().search(query)


def search_documents(query: str, top_k: int) -> tuple[list[dict], float]:
    """Application use case for scored API/CLI search results."""
    t0 = time.time()
    from src.vector_store.service import VectorStoreService
    docs_with_scores = VectorStoreService().similarity_search_with_scores(query, top_k)
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
