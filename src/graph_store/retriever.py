from src.graph_store.graph import KnowledgeGraph

_kg: KnowledgeGraph | None = None


def get_graph() -> KnowledgeGraph:
    global _kg
    if _kg is None:
        _kg = KnowledgeGraph()
    return _kg


def set_graph(kg: KnowledgeGraph):
    global _kg
    _kg = kg


def search_graph(query: str) -> str:
    kg = get_graph()
    return kg.search(query)
