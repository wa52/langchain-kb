"""Adapter around the current Chroma + BM25 retrieval implementation."""

from src.domain.models import DocumentChunk, Query, RetrievalResult


class CurrentRetrieverAdapter:
    """Compatibility adapter; replace this without changing QueryService."""

    def __init__(self, vector_store=None) -> None:
        self._vector_store = vector_store

    def retrieve(self, query: Query) -> list[RetrievalResult]:
        if self._vector_store is None:
            from src.vector_store.service import VectorStoreService
            docs = VectorStoreService().similarity_search_with_scores(query.text, query.limit)
        else:
            docs = self._vector_store.similarity_search_with_relevance_scores(query.text, k=query.limit)
        results: list[RetrievalResult] = []
        for rank, (doc, score) in enumerate(docs, start=1):
            metadata = dict(getattr(doc, "metadata", {}) or {})
            chunk = DocumentChunk(
                content=str(getattr(doc, "page_content", "")),
                source=str(metadata.get("source", "")),
                chunk_id=str(getattr(doc, "id", "") or metadata.get("chunk_id", "")),
                metadata=metadata,
            )
            results.append(RetrievalResult(chunk=chunk, score=float(score), rank=rank, channel="vector"))
        return results
