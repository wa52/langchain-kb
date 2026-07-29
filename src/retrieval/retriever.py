import time

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from config import TOP_K, ENABLE_HYBRID_SEARCH
from src.vector_store.chroma_client import get_vector_store
from src.vector_store.embedding import get_embedding_model

_bm25_retriever = None


def set_bm25_retriever(r):
    global _bm25_retriever
    _bm25_retriever = r


def get_retriever(k: int | None = None):
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


def rebuild_bm25(store, echo_fn: callable = print):
    global _bm25_retriever
    try:
        all_data = store._collection.get(include=["documents", "metadatas"])
        if not all_data or not all_data.get("documents"):
            return
        docs = [
            Document(page_content=t, metadata=m or {})
            for t, m in zip(all_data["documents"], all_data["metadatas"] or [{}] * len(all_data["documents"]))
        ]
        t0 = time.time()
        texts = [doc.page_content for doc in docs]
        _bm25_retriever = BM25Retriever.from_texts(
            texts, metadatas=[doc.metadata for doc in docs]
        )
        _bm25_retriever.k = TOP_K
        echo_fn(f"  -> BM25 索引构建完成 ({len(docs)} 篇, {time.time()-t0:.1f}s)")
    except Exception as e:
        echo_fn(f"  [BM25] 索引更新失败: {e}")
