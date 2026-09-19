def search_documents(rm, query: str, top_k: int):
    from src.application.search import search_documents as _search
    from src.bootstrap.composition import create_query_service

    return _search(create_query_service(rm), query, top_k)
