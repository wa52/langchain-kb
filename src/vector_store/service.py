from config import TOP_K, ENABLE_HYBRID_SEARCH
from src.vector_store.chroma_client import (
    get_vector_store,
    reset_vector_store,
    delete_by_source as _delete_by_source,
    add_documents_with_progress,
)
from src.retrieval.retriever import rebuild_bm25 as _rebuild_bm25, _bm25_retriever
from src.vector_store.embedding import get_embedding_model
from langchain_classic.retrievers.ensemble import EnsembleRetriever


class VectorStoreService:
    def __init__(self, echo_fn: callable = print):
        self._echo_fn = echo_fn

    def get_retriever(self, k: int | None = None):
        k = k or TOP_K
        embeddings = get_embedding_model()
        vector_store = get_vector_store(embeddings)
        vector_retriever = vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": k * 4},
        )
        if ENABLE_HYBRID_SEARCH and _bm25_retriever is not None:
            return EnsembleRetriever(
                retrievers=[vector_retriever, _bm25_retriever],
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
        reset_vector_store()
        vs = get_vector_store()
        vs.delete_collection()
        reset_vector_store()
