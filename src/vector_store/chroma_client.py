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
    _invalidate_stats_cache()


def set_vector_store(store):
    global _vector_store
    _vector_store = store


def delete_by_source(source_name: str):
    vs = get_vector_store()
    vs.delete(where={"source": source_name})
    _invalidate_stats_cache()
    print(f"  -> 从向量库删除: {source_name}")


_stats_cache: dict | None = None
_stats_cache_key: tuple | None = None
_stats_cache_ts: float = 0.0
_STATS_CACHE_TTL_SECONDS = 10.0


def _invalidate_stats_cache():
    """Drop the cached collection stats (called after writes)."""
    global _stats_cache, _stats_cache_key, _stats_cache_ts
    _stats_cache = None
    _stats_cache_key = None
    _stats_cache_ts = 0.0


def get_collection_stats() -> dict:
    vs = get_vector_store()
    try:
        count = vs._collection.count()
    except Exception:
        count = 0

    global _stats_cache, _stats_cache_key, _stats_cache_ts
    # Cache keyed by vector-store identity + chunk count, with a short TTL.
    # count() is cheap; the full metadata scan (500/batch over every chunk)
    # is what makes repeated calls slow on large corpora.
    key = (id(vs), count)
    now = time.time()
    if (
        _stats_cache is not None
        and _stats_cache_key == key
        and (now - _stats_cache_ts) < _STATS_CACHE_TTL_SECONDS
    ):
        return _stats_cache

    if count == 0:
        result = {"count": 0, "sources": [], "source_count": 0}
        _stats_cache, _stats_cache_key, _stats_cache_ts = result, key, now
        return result

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
    result = {"count": count, "sources": sorted(sources), "source_count": len(sources)}
    _stats_cache, _stats_cache_key, _stats_cache_ts = result, key, now
    return result


def add_documents_with_progress(chunks: list, batch_size: int = 32, echo_fn: callable = print):
    vs = get_vector_store()
    total = len(chunks)
    if total == 0:
        return

    _inject_capability_metadata(chunks)

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

    _invalidate_stats_cache()
    echo_fn()
    total_elapsed = time.time() - t0
    echo_fn(f"  -> 完成! {total} 个向量, {total_elapsed:.1f}s, {total/total_elapsed:.0f} ch/s")


def _inject_capability_metadata(chunks: list):
    """Attach capability metadata to chunks that don't already have it.

    Maps each chunk onto the industrial vision AI capability model via
    source/content rules (no LLM). Skips chunks already carrying the fields.
    """
    from src.capability.mapper import classify_chunk
    for c in chunks:
        meta = getattr(c, "metadata", None) or {}
        if "capability_domain" in meta:
            continue
        source = meta.get("source", "")
        text = getattr(c, "page_content", "") or ""
        try:
            tags = classify_chunk(source, text)
        except Exception:
            continue
        for k, v in tags.items():
            if k != "source":
                meta[k] = v
        c.metadata = meta
