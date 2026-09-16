"""Integration tests for retrieve_knowledge tool.

Tests through the public interface using real Chroma in-memory + real HuggingFace embeddings.
LLM-dependent features (grading/rewrite/compression) are disabled via patch.
"""

import uuid
import pytest
from unittest.mock import patch
from langchain_core.documents import Document
from langchain_chroma import Chroma

from src.vector_store.embedding import get_embedding_model
from src.vector_store.chroma_client import (
    get_vector_store,
    set_vector_store,
    reset_vector_store,
)
from src.agent.tools import retrieve_knowledge
from src.retrieval.retriever import rebuild_bm25

SAMPLE_DOCS = [
    Document(
        page_content=(
            "RAG (Retrieval-Augmented Generation) 是一种结合检索和生成的 NLP 技术。"
            "它通过从外部知识库检索相关文档来增强大语言模型的生成能力。"
            "RAG 的工作流程包括：文档索引、检索和生成三个阶段。"
        ),
        metadata={"source": "rag_intro.md"},
    ),
    Document(
        page_content=(
            "LangChain Agent 是一个可以自主决策和执行任务的智能体。"
            "它可以访问多种工具并根据用户输入选择合适的工具来完成任务。"
            "Agent 使用 ReAct 模式进行推理和行动。"
        ),
        metadata={"source": "agent_intro.md"},
    ),
    Document(
        page_content=(
            "Conversation Buffer Memory 是 LangChain 中最简单的记忆方式。"
            "它将对话历史存储在缓冲区中，每次调用时将所有历史消息注入到提示中。"
            "这种方式适合短期对话但有 token 限制。"
        ),
        metadata={"source": "memory_intro.md"},
    ),
]


@pytest.fixture(autouse=True)
def fresh_store():
    reset_vector_store()
    embeddings = get_embedding_model()
    store = Chroma(embedding_function=embeddings, collection_name=f"test_{uuid.uuid4().hex[:8]}")
    set_vector_store(store)
    yield
    reset_vector_store()


@pytest.fixture(autouse=True)
def no_real_bm25_write():
    """rebuild_bm25(vs) 用内存测试库时不得覆写真实的 chroma_db/bm25_index.pkl。"""
    with patch("src.retrieval.retriever._save_bm25_to_disk"):
        yield


PATCH_GRADING = patch("src.agent.tools.ENABLE_GRADING", False)
PATCH_REWRITE = patch("src.agent.tools.ENABLE_REWRITE", False)
PATCH_COMPRESSION = patch("src.agent.tools.ENABLE_CONTEXT_COMPRESSION", False)


@PATCH_GRADING
@PATCH_REWRITE
@PATCH_COMPRESSION
class TestRetrieveKnowledge:

    def test_relevant_query(self):
        vs = get_vector_store()
        vs.add_documents(SAMPLE_DOCS)
        result = retrieve_knowledge.invoke({"query": "RAG"})
        assert "rag_intro.md" in result
        assert "RAG" in result or "Retrieval-Augmented" in result

    @patch("src.agent.tools.ENABLE_GRAPH", False)
    def test_empty_knowledge_base(self):
        result = retrieve_knowledge.invoke({"query": "RAG"})
        assert result == "未找到相关信息。"

    def test_irrelevant_query(self):
        vs = get_vector_store()
        vs.add_documents(SAMPLE_DOCS)
        result = retrieve_knowledge.invoke({"query": "量子计算"})
        assert result != "未找到相关信息。"
        assert "来源:" in result

    @patch("src.retrieval.retriever.ENABLE_HYBRID_SEARCH", True)
    def test_hybrid_search_uses_ensemble(self):
        vs = get_vector_store()
        vs.add_documents(SAMPLE_DOCS)
        rebuild_bm25(vs)
        result = retrieve_knowledge.invoke({"query": "RAG"})
        assert "rag_intro.md" in result
        assert "RAG" in result or "Retrieval-Augmented" in result
