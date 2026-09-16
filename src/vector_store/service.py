from config import TOP_K, ENABLE_HYBRID_SEARCH
from src.vector_store.chroma_client import (
    get_vector_store,
    reset_vector_store,
    delete_by_source as _delete_by_source,
    add_documents_with_progress,
)
import src.retrieval.retriever as _retriever_mod
from src.retrieval.retriever import rebuild_bm25 as _rebuild_bm25
from src.vector_store.embedding import get_embedding_model
from langchain_classic.retrievers.ensemble import EnsembleRetriever


class VectorStoreService:
    def __init__(self, echo_fn: callable = print):
        self._echo_fn = echo_fn

    def get_retriever(self, k: int | None = None, capability: str | None = None):
        k = k or TOP_K
        embeddings = get_embedding_model()
        vector_store = get_vector_store(embeddings)
        search_kwargs: dict = {"k": k, "fetch_k": k * 4}
        if capability:
            # Filter by capability domain (exact match on the primary domain).
            search_kwargs["filter"] = {"capability_domain_primary": {"$eq": capability}}
        vector_retriever = vector_store.as_retriever(
            search_type="mmr",
            search_kwargs=search_kwargs,
        )
        # Read the BM25 global at call time: a module-level `from ... import`
        # would bind None at import time and never see the index rebuilt later.
        bm25 = _retriever_mod._bm25_retriever
        if ENABLE_HYBRID_SEARCH and bm25 is not None:
            return EnsembleRetriever(
                retrievers=[vector_retriever, bm25],
                weights=[0.5, 0.5],
            )
        return vector_retriever

    def add_documents(self, chunks: list):
        add_documents_with_progress(chunks, echo_fn=self._echo_fn)

    def delete_by_source(self, source_name: str):
        _delete_by_source(source_name)

    def rebuild_bm25(self):
        store = get_vector_store()
        _rebuild_bm25(store, echo_fn=self._echo_fn)

    def get_stats(self) -> dict:
        from src.vector_store.chroma_client import get_collection_stats
        return get_collection_stats()

    def reset(self):
        from src.retrieval.retriever import invalidate_bm25

        invalidate_bm25()
        reset_vector_store()
        vs = get_vector_store()
        vs.delete_collection()
        reset_vector_store()
