from src.application.search import search_documents as _search_documents


def search_documents(
    rm, query: str, top_k: int
) -> tuple[list[dict], float]:
    from src.bootstrap.composition import create_query_service
    return _search_documents(create_query_service(rm), query, top_k)
