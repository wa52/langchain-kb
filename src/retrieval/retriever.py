import os
import pickle
import re
import time
import tempfile
from pathlib import Path
from threading import Lock

from langchain_classic.retrievers.ensemble import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from config import TOP_K, CHROMA_PERSIST_DIR, ENABLE_HYBRID_SEARCH
from src.vector_store.chroma_client import get_vector_store
from src.vector_store.embedding import get_embedding_model

_bm25_retriever = None
_bm25_invalidated = False
_BM25_SAVE_LOCK = Lock()
_BM25_PERSIST_PATH = Path(CHROMA_PERSIST_DIR) / "bm25_index.pkl"


def _bm25_invalid_path() -> Path:
    return _BM25_PERSIST_PATH.with_suffix(".invalid")

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _bm25_tokenize(text: str) -> list[str]:
    """Tokenize for BM25.

    jieba segments Chinese text, which the default whitespace split would
    treat as a single giant token; non-CJK text keeps the fast whitespace
    split so the (mostly English) corpus stays cheap to load/rebuild.
    """
    if _CJK_RE.search(text):
        import jieba
        return [t for t in jieba.cut(text) if t.strip()]
    return text.split()


def set_bm25_retriever(r):
    global _bm25_retriever, _bm25_invalidated
    _bm25_retriever = r
    _bm25_invalidated = False


def invalidate_bm25():
    """Discard both in-memory and persisted BM25 data after collection writes."""
    global _bm25_retriever, _bm25_invalidated
    _bm25_retriever = None
    _bm25_invalidated = True
    with _BM25_SAVE_LOCK:
        invalid_path = _bm25_invalid_path()
        invalid_path.parent.mkdir(parents=True, exist_ok=True)
        invalid_path.write_text("invalid", encoding="ascii")
        try:
            _BM25_PERSIST_PATH.unlink(missing_ok=True)
        except OSError:
            # The in-memory invalidation still prevents stale reads in this
            # process; startup will rebuild if the cache cannot be loaded.
            pass


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


def _load_bm25_from_disk(expected_count: int | None = None, echo_fn: callable = None) -> bool:
    global _bm25_retriever
    if _bm25_invalid_path().exists() or not _BM25_PERSIST_PATH.exists():
        return False
    try:
        with open(_BM25_PERSIST_PATH, "rb") as f:
            data = pickle.load(f)
        texts: list[str] = data["texts"]
        if expected_count is not None and len(texts) != expected_count:
            if echo_fn:
                echo_fn(
                    f"  -> BM25 缓存已失效（缓存 {len(texts)} / 当前 {expected_count}），"
                    "需要全量重建（可能耗时数十秒）..."
                )
            _bm25_retriever = None
            return False
        metadatas: list[dict] = data["metadatas"]
        _bm25_retriever = BM25Retriever.from_texts(
            texts, metadatas=metadatas, preprocess_func=_bm25_tokenize
        )
        _bm25_retriever.k = TOP_K
        return True
    except Exception:
        _bm25_retriever = None
        return False


def _save_bm25_to_disk(texts: list[str], metadatas: list[dict]):
    _BM25_PERSIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _BM25_SAVE_LOCK:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{_BM25_PERSIST_PATH.name}.", suffix=".tmp",
            dir=_BM25_PERSIST_PATH.parent,
        )
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump({"texts": texts, "metadatas": metadatas}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, _BM25_PERSIST_PATH)
            _bm25_invalid_path().unlink(missing_ok=True)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)


def _bm25_doc_count(retriever) -> int | None:
    """Best-effort chunk count of a loaded BM25Retriever."""
    try:
        return len(retriever.docs)
    except Exception:
        return None


def rebuild_bm25(store, echo_fn: callable = print):
    global _bm25_retriever, _bm25_invalidated

    from src.status import get_registry
    reg = get_registry()
    reg.set_loading("bm25", "加载/构建 BM25 索引")

    try:
        expected_count = store._collection.count()
    except Exception:
        expected_count = None

    force_rebuild = _bm25_invalidated
    if _bm25_retriever is not None and not force_rebuild:
        in_mem = _bm25_doc_count(_bm25_retriever)
        # Skip only when the in-memory index still matches the collection;
        # after a data change the index must be rebuilt even in this process.
        if expected_count is not None and in_mem == expected_count:
            echo_fn("  -> BM25 索引已在内存中，跳过重建")
            reg.set_ready("bm25", f"{in_mem} chunks · 已在内存" if in_mem is not None else "已在内存")
            return
        echo_fn("  -> BM25 数据已变更，重建索引")
        _bm25_retriever = None

    if not force_rebuild and _load_bm25_from_disk(expected_count=expected_count, echo_fn=echo_fn):
        echo_fn(f"  -> BM25 索引已从磁盘加载 ({_BM25_PERSIST_PATH})")
        n = _bm25_doc_count(_bm25_retriever)
        reg.set_ready("bm25", f"{n} chunks · 磁盘加载" if n is not None else "磁盘加载")
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
            _bm25_invalidated = False
            reg.set_ready("bm25", "0 chunks（空语料）")
            return
        docs = [
            Document(page_content=t, metadata=m or {})
            for t, m in zip(all_texts, all_metadatas)
        ]
        t0 = time.time()
        texts = [doc.page_content for doc in docs]
        _bm25_retriever = BM25Retriever.from_texts(
            texts, metadatas=[doc.metadata for doc in docs],
            preprocess_func=_bm25_tokenize,
        )
        _bm25_retriever.k = TOP_K
        _save_bm25_to_disk(texts, [doc.metadata for doc in docs])
        _bm25_invalidated = False
        reg.set_ready("bm25", f"{len(docs)} chunks · 全量重建")
        echo_fn(f"  -> BM25 索引构建完成 ({len(docs)} 篇, {time.time()-t0:.1f}s)")
    except Exception as e:
        reg.set_error("bm25", e, "全量重建")
        echo_fn(f"  [BM25] 索引更新失败: {e}")
        raise
