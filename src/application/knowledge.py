import time

from src.domain.routing import ScoredDocument


def retrieve_documents(query: str, k: int, capability: str | None = None):
    """Application boundary for Agent-oriented hybrid retrieval."""
    if capability is None:
        try:
            from src.resources import ResourceManager
            manager = ResourceManager.get_instance()
            if manager.is_ready():
                return manager.get_retriever(k=k).invoke(query)
        except RuntimeError:
            # CLI/tests may call retrieval before the managed API lifecycle.
            pass

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


def retrieve_scored_documents(query: str, top_k: int) -> list[ScoredDocument]:
    """Return ranked candidates without changing the legacy Document[] API.

    Dense relevance is supplied by Chroma; BM25 exposes ranks rather than raw
    incomparable scores, so each channel is normalized before fusion.
    """
    from src.vector_store.service import VectorStoreService
    from src.retrieval import retriever as retrieval

    dense = VectorStoreService().similarity_search_with_scores(query, top_k)
    bm25 = retrieval._bm25_retriever.invoke(query)[:top_k] if retrieval._bm25_retriever is not None else []
    candidates: dict[tuple[str, str], dict] = {}
    for rank, (doc, score) in enumerate(dense, 1):
        key = (str((getattr(doc, "metadata", {}) or {}).get("source", "")), str(getattr(doc, "page_content", "")))
        candidates[key] = {"document": doc, "dense_score": max(0.0, min(1.0, float(score))), "dense_rank": rank, "bm25_score": 0.0, "bm25_rank": None}
    for rank, doc in enumerate(bm25, 1):
        key = (str((getattr(doc, "metadata", {}) or {}).get("source", "")), str(getattr(doc, "page_content", "")))
        row = candidates.setdefault(key, {"document": doc, "dense_score": 0.0, "dense_rank": None, "bm25_score": 0.0, "bm25_rank": None})
        row["bm25_rank"] = rank
        row["bm25_score"] = 1.0 / rank
    rows = []
    for row in candidates.values():
        # Dense relevance is already [0, 1]; BM25 uses reciprocal rank [0, 1].
        channels = [row["dense_score"]] if row["dense_rank"] else []
        if row["bm25_rank"]:
            channels.append(row["bm25_score"])
        row["fusion_score"] = sum(channels) / len(channels) if channels else 0.0
        rows.append(row)
    rows.sort(key=lambda row: row["fusion_score"], reverse=True)
    return [ScoredDocument(**row, final_rank=index) for index, row in enumerate(rows[:top_k], 1)]


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
