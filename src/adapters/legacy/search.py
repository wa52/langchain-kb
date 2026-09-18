def search_documents(rm, query: str, top_k: int):
    from src.api.services.search import search_documents as _search
    return _search(rm, query, top_k)
