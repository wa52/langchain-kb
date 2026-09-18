from src.application.search import search_documents as _search_documents


def search_documents(
    rm, query: str, top_k: int
) -> tuple[list[dict], float]:
    return _search_documents(rm, query, top_k)
