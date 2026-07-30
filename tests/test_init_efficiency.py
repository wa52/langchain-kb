from unittest.mock import MagicMock, patch

import pytest
from langchain_core.retrievers import BaseRetriever

from src.resources import ResourceManager


def _make_retriever_mock():
    return MagicMock(spec=BaseRetriever)


@pytest.fixture(autouse=True)
def reset_singleton():
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


def test_embedding_initialized_only_once():
    with (
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()) as mock_emb,
        patch("src.resources.Chroma", return_value=MagicMock()),
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25"),
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
    ):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_emb.assert_called_once()


def test_vector_store_created_only_once():
    with (
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()),
        patch("src.resources.Chroma", return_value=MagicMock()) as mock_chroma,
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25"),
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
    ):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_chroma.assert_called_once()


def test_llm_initialized_only_once():
    with (
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()),
        patch("src.resources.Chroma", return_value=MagicMock()),
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25"),
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
        patch("src.llm.get_llm", return_value=MagicMock()) as mock_llm,
    ):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_llm.assert_called_once()


def test_get_retriever_does_not_reinit_resources():
    chroma_mock = MagicMock()
    chroma_mock.as_retriever.return_value = _make_retriever_mock()
    with (
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()),
        patch("src.resources.Chroma", return_value=chroma_mock) as mock_chroma,
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25"),
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
    ):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_chroma.reset_mock()
        _ = rm.get_retriever(k=5)
        _ = rm.get_retriever(k=10)
        mock_chroma.assert_not_called()


def test_resources_not_recreated_on_idempotent_startup():
    with (
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()) as mock_emb,
        patch("src.resources.Chroma", return_value=MagicMock()) as mock_chroma,
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25") as mock_rebuild,
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
        patch("src.llm.get_llm", return_value=MagicMock()) as mock_llm,
    ):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        rm.startup(echo_fn=lambda _: None)

        mock_emb.assert_called_once()
        mock_chroma.assert_called_once()
        mock_llm.assert_called_once()
        mock_rebuild.assert_called_once()
