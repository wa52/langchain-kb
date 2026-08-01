import os
import pickle
import time
from pathlib import Path

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from config import TOP_K, CHROMA_PERSIST_DIR, ENABLE_HYBRID_SEARCH
from src.vector_store.chroma_client import get_vector_store
from src.vector_store.embedding import get_embedding_model

_bm25_retriever = None
_BM25_PERSIST_PATH = Path(CHROMA_PERSIST_DIR) / "bm25_index.pkl"


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


def _load_bm25_from_disk(expected_count: int | None = None) -> bool:
    global _bm25_retriever
    if not _BM25_PERSIST_PATH.exists():
        return False
    try:
        with open(_BM25_PERSIST_PATH, "rb") as f:
            data = pickle.load(f)
        texts: list[str] = data["texts"]
        if expected_count is not None and len(texts) != expected_count:
            _bm25_retriever = None
            return False
        metadatas: list[dict] = data["metadatas"]
        _bm25_retriever = BM25Retriever.from_texts(texts, metadatas=metadatas)
        _bm25_retriever.k = TOP_K
        return True
    except Exception:
        _bm25_retriever = None
        return False


def _save_bm25_to_disk(texts: list[str], metadatas: list[dict]):
    _BM25_PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_BM25_PERSIST_PATH, "wb") as f:
        pickle.dump({"texts": texts, "metadatas": metadatas}, f)


def rebuild_bm25(store, echo_fn: callable = print):
    global _bm25_retriever

    try:
        expected_count = store._collection.count()
    except Exception:
        expected_count = None

    if _bm25_retriever is not None:
        # Already loaded in this process (data unchanged); avoid re-parsing the
        # persisted pickle on every agent construction.
        echo_fn("  -> BM25 索引已在内存中，跳过重建")
        return

    if _load_bm25_from_disk(expected_count=expected_count):
        echo_fn(f"  -> BM25 索引已从磁盘加载 ({_BM25_PERSIST_PATH})")
        return

    try:
        all_texts = []
        all_metadatas = []
        batch_size = 500
        offset = 0
        while True:
            batch = store._collection.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=offset,
            )
            batch_docs = batch.get("documents") if batch else []
            if not batch_docs:
                break
            all_texts.extend(batch_docs)
            all_metadatas.extend(
                batch.get("metadatas") or [{}] * len(batch_docs)
            )
            offset += batch_size

        if not all_texts:
            return
        docs = [
            Document(page_content=t, metadata=m or {})
            for t, m in zip(all_texts, all_metadatas)
        ]
        t0 = time.time()
        texts = [doc.page_content for doc in docs]
        _bm25_retriever = BM25Retriever.from_texts(
            texts, metadatas=[doc.metadata for doc in docs]
        )
        _bm25_retriever.k = TOP_K
        _save_bm25_to_disk(texts, [doc.metadata for doc in docs])
        echo_fn(f"  -> BM25 索引构建完成 ({len(docs)} 篇, {time.time()-t0:.1f}s)")
    except Exception as e:
        echo_fn(f"  [BM25] 索引更新失败: {e}")
