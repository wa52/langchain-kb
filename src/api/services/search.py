from src.resources import ResourceManager
from src.application.knowledge import search_documents as _search_documents


def search_documents(
    rm: ResourceManager, query: str, top_k: int
) -> tuple[list[dict], float]:
    return _search_documents(rm, query, top_k)
