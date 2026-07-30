import time

from src.resources import ResourceManager


_start_time: float = time.time()


def get_health_status(rm: ResourceManager) -> dict:
    uptime = time.time() - _start_time
    vs = rm.vector_store
    vector_count = vs._collection.count() if vs else 0
    kg = rm.graph
    entity_count = kg.graph.number_of_nodes() if kg else 0
    return {
        "status": "ok",
        "uptime": round(uptime, 2),
        "index_version": rm.get_index_version(),
        "vector_count": vector_count,
        "entity_count": entity_count,
    }
