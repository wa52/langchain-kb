"""Knowledge overview aggregation for the web client.

Gathers light-weight statistics from the vector store, BM25, graph, and the
most recent index task. Reads cached stats; no expensive probes or rebuilds.
"""

import logging

from src.resources import ResourceManager
from src.api.services.indexing import get_task_manager

logger = logging.getLogger(__name__)


def _bm25_chunk_count() -> int | None:
    from src.retrieval import retriever as _ret
    bm25 = _ret._bm25_retriever
    if bm25 is None:
        return None
    try:
        return len(bm25.docs)
    except Exception:
        return None


def get_knowledge_stats(rm: ResourceManager) -> dict:
    from src.ingestion.tracker import list_all_files

    try:
        chunks = int(rm.vector_store._collection.count()) if rm.vector_store is not None else 0
    except Exception:
        chunks = 0
    # Tracker lookup is proportional to the number of source files, unlike
    # scanning metadata for every vector in a large collection.
    documents = len(list_all_files())

    graph_stats = {"entities": 0, "relations": 0}
    kg = rm.graph
    if kg is not None:
        try:
            graph_stats = {
                "entities": kg.graph.number_of_nodes(),
                "relations": kg.graph.number_of_edges(),
            }
        except Exception as exc:
            logger.warning("knowledge stats: graph read failed: %s", exc)

    task = get_task_manager().latest_task()
    index_task = None
    if task is not None:
        index_task = {
            "task_id": task.get("task_id"),
            "status": task.get("status"),
            "progress": task.get("progress"),
            "result": task.get("result"),
            "error": task.get("error"),
        }

    return {
        "documents": documents,
        "chunks": chunks,
        "bm25_chunks": _bm25_chunk_count(),
        "graph": graph_stats,
        "index_task": index_task,
    }
