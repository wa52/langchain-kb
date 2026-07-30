from pathlib import Path

import config as cfg
from src.graph_store.graph import KnowledgeGraph, build_graph_store
from src.graph_store.retriever import set_graph, get_graph
from src.llm import get_llm


class GraphService:
    def __init__(self, echo_fn: callable = print):
        self._echo_fn = echo_fn

    def search(self, query: str) -> str:
        kg = get_graph()
        return kg.search(query)

    def build_from_chunks(self, chunks: list, llm=None):
        kg = KnowledgeGraph(echo_fn=self._echo_fn)
        if llm is None and cfg.ENABLE_GRAPH_LLM_EXTRACTION:
            llm = get_llm(temperature=0)
        kg.build_from_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    def build_from_disk(self):
        kg = build_graph_store()
        set_graph(kg)
        return kg

    def add_chunks(self, chunks: list, llm=None):
        kg = get_graph()
        if llm is None and cfg.ENABLE_GRAPH_LLM_EXTRACTION:
            llm = get_llm(temperature=0)
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    def get_stats(self) -> dict:
        kg = get_graph()
        return kg.stats()

    def get_entity_count(self) -> int:
        kg = get_graph()
        return kg.graph.number_of_nodes()
