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
    sources = set()
    batch_size = 500
    offset = 0
    while True:
        batch = vs._collection.get(include=["metadatas"], limit=batch_size, offset=offset)
        batch_metas = batch.get("metadatas", []) if batch else []
        if not batch_metas:
            break
        for m in batch_metas:
            if m and "source" in m:
                sources.add(m["source"])
        offset += batch_size
    return {"count": count, "sources": sorted(sources), "source_count": len(sources)}


def add_documents_with_progress(chunks: list, batch_size: int = 32, echo_fn: callable = print):
    vs = get_vector_store()
    total = len(chunks)
    if total == 0:
        return

    bar_width = 20
    t0 = time.time()

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        vs.add_documents(batch)

        done = min(i + len(batch), total)
        pct = done / total
        filled = int(pct * bar_width)
        bar = "#" * filled + "." * (bar_width - filled)
        elapsed = time.time() - t0
        speed = done / elapsed if elapsed > 0 else 0
        echo_fn(f"\r  [{pct*100:3.0f}%] {bar} {done:>4d}/{total}  ({elapsed:.1f}s, {speed:.0f} ch/s)", end="")

    echo_fn()
    total_elapsed = time.time() - t0
    echo_fn(f"  -> 完成! {total} 个向量, {total_elapsed:.1f}s, {total/total_elapsed:.0f} ch/s")
