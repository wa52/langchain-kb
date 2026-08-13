import time

from src.resources import ResourceManager
from src.status import (
    snapshot_status,
    uptime_seconds,
    overall_state,
    ERROR,
    LOADING,
    PENDING,
    READY,
)


def _resolve_state(name: str, present: bool, reg: dict) -> str:
    """以注册表为准（含 loading/error 等中间态），否则按组件是否已加载判定。"""
    rstate = reg.get(name, {}).get("state")
    if present:
        return ERROR if rstate == ERROR else READY
    return rstate if rstate in (LOADING, ERROR) else PENDING


def _component(name: str, present: bool, reg: dict) -> dict:
    r = reg.get(name, {})
    return {
        "name": name,
        "state": _resolve_state(name, present, reg),
        "detail": r.get("detail") or "",
        "duration_ms": r.get("duration_ms"),
        "error": r.get("error"),
    }


def _bm25_chunks():
    from src.retrieval import retriever as _ret
    bm25 = _ret._bm25_retriever
    if bm25 is None:
        return None
    try:
        return len(bm25.docs)
    except Exception:
        return None


def get_system_status(rm: ResourceManager) -> dict:
    reg = snapshot_status()
    kg = rm.graph

    from src.retrieval import retriever as _ret
    bm25_present = _ret._bm25_retriever is not None

    components = {
        "embedding": _component("embedding", rm.embedding_model is not None, reg),
        "llm": _component("llm", rm.llm is not None, reg),
        "vector_store": _component("vector_store", rm.vector_store is not None, reg),
        "bm25": _component("bm25", bm25_present, reg),
        "graph": _component("graph", kg is not None, reg),
        "agent": _component("agent", rm.agent is not None, reg),
        # index 反映最近一次索引任务的活动状态（与 rm 无关）
        "index": dict(reg.get("index", {})),
    }

    vs = rm.vector_store
    vector_count = vs._collection.count() if vs else 0
    entity_count = kg.graph.number_of_nodes() if kg else 0

    return {
        "status": overall_state(components),
        "uptime": round(uptime_seconds(), 2),
        "index_version": rm.get_index_version(),
        "vector_count": vector_count,
        "entity_count": entity_count,
        "bm25_chunks": _bm25_chunks(),
        "components": components,
    }
