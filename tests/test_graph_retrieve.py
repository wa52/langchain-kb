import pytest
from unittest.mock import patch
from langchain_core.documents import Document

from src.graph_store.graph import KnowledgeGraph
from src.graph_store.retriever import set_graph, search_graph


SAMPLE_DOC = Document(
    page_content=(
        "LangChain 是一个框架，支持 RAG 和 Agent。"
        "RAG 是检索增强生成的技术。"
        "Agent 可以自主决策和行动。"
        "LangChain 支持多种 Agent 类型。"
        "RAG 结合了检索和生成能力。"
        "LangChain Agent 可以使用工具。"
        "RAG 利用向量数据库存储嵌入。"
    ),
    metadata={"source": "test.md"},
)


@pytest.fixture(autouse=True)
def fresh_graph():
    kg = KnowledgeGraph()
    kg.build_from_chunks([SAMPLE_DOC])
    set_graph(kg)
    yield


class TestGraphRetrieve:

    def test_search_relevant(self):
        result = search_graph("RAG")
        assert "RAG" in result
        assert "LangChain" in result

    def test_search_empty_graph(self):
        kg = KnowledgeGraph()
        kg.build_from_chunks([])
        set_graph(kg)
        result = search_graph("RAG")
        assert result == "未找到相关的图谱信息。"

    def test_search_unrelated(self):
        result = search_graph("量子计算")
        assert result == "未找到相关的图谱信息。"
