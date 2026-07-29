import time

from langchain_chroma import Chroma

from config import CHROMA_PERSIST_DIR
from src.vector_store.embedding import get_embedding_model

_vector_store = None


def get_vector_store(embeddings=None):
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    if embeddings is None:
        embeddings = get_embedding_model()
    _vector_store = Chroma(
        collection_name="langchain_docs",
        persist_directory=CHROMA_PERSIST_DIR,
        embedding_function=embeddings,
    )
    return _vector_store


def reset_vector_store():
    global _vector_store
    _vector_store = None


def set_vector_store(store):
    global _vector_store
    _vector_store = store


def delete_by_source(source_name: str):
    vs = get_vector_store()
    vs.delete(where={"source": source_name})
    print(f"  -> 从向量库删除: {source_name}")


def get_collection_stats() -> dict:
    vs = get_vector_store()
    count = vs._collection.count()
    if count == 0:
        return {"count": 0, "sources": [], "source_count": 0}
    all_data = vs._collection.get(include=["metadatas"])
    sources = set()
    for m in all_data.get("metadatas", []):
        if m and "source" in m:
            sources.add(m["source"])
    return {"count": count, "sources": sorted(sources), "source_count": len(sources)}


def add_documents_with_progress(chunks: list, batch_size: int = 32):
    vs = get_vector_store()
    total = len(chunks)
    if total == 0:
        return

    print(f"  向量化 {total} 个文档片段 (batch_size={batch_size}) ...")
    t0 = time.time()

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        vs.add_documents(batch)
        pct = min(100, int((i + len(batch)) / total * 100))
        elapsed = time.time() - t0
        speed = (i + len(batch)) / elapsed if elapsed > 0 else 0
        print(f"  [{pct:3d}%] {min(i + len(batch), total):>4d}/{total}  ({elapsed:.1f}s, {speed:.0f} chunks/s)")

    total_elapsed = time.time() - t0
    dims = len(chunks[0].page_content) if chunks else 0
    print(f"  -> 完成! {total} 个向量, {total_elapsed:.1f}s, {total/total_elapsed:.0f} chunks/s")
