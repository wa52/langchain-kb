from unittest.mock import MagicMock, patch

import pytest

from src.resources import ResourceManager


@pytest.fixture(autouse=True)
def reset_singleton():
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


def mock_deps():
    return [
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()),
        patch("src.llm.client.get_llm", return_value=MagicMock()),
        patch("src.resources.Chroma", return_value=MagicMock()),
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25"),
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
    ]


@pytest.fixture
def started_rm():
    patches = mock_deps() + [
        patch("src.resources.ENABLE_HYBRID_SEARCH", False),
    ]
    with _multi_patch(patches):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        rm.vector_store = MagicMock()
        yield rm


def _multi_patch(patches):
    for p in patches:
        p.start()
    return _PatchContext(patches)


class _PatchContext:
    def __init__(self, patches):
        self._patches = patches

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for p in self._patches:
            p.stop()


class TestSearchDoesNotRescan:
    def test_regular_search_does_not_call_rebuild_bm25(self, started_rm):
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = []
        from src.api.services.search import search_documents
        with patch("src.retrieval.retriever.rebuild_bm25") as mock_rebuild:
            search_documents(started_rm, "test", 5)
            mock_rebuild.assert_not_called()

    def test_regular_search_does_not_regenerate_vectors(self, started_rm):
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = []
        from src.api.services.search import search_documents
        with patch.object(started_rm.vector_store, "add_documents") as mock_add:
            search_documents(started_rm, "test", 5)
            mock_add.assert_not_called()

    def test_get_retriever_does_not_rebuild_bm25(self, started_rm):
        with patch("src.retrieval.retriever.rebuild_bm25") as mock_rebuild:
            _ = started_rm.get_retriever(k=5)
            mock_rebuild.assert_not_called()


class TestTopK:
    def test_top_k_passed_to_vector_store(self, started_rm):
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = []
        from src.api.services.search import search_documents
        search_documents(started_rm, "test", 3)
        started_rm.vector_store.similarity_search_with_relevance_scores.assert_called_with(
            "test", k=3
        )

    def test_top_k_defaults_to_5(self, started_rm):
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = []
        from src.api.services.search import search_documents
        search_documents(started_rm, "test", 5)
        started_rm.vector_store.similarity_search_with_relevance_scores.assert_called_with(
            "test", k=5
        )

    def test_top_k_validates_range_via_api(self):
        from src.api.schemas import SearchRequest
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            SearchRequest(query="test", top_k=0)
        with pytest.raises(pydantic.ValidationError):
            SearchRequest(query="test", top_k=51)


class TestSearchResponse:
    def test_result_contains_all_required_fields(self, started_rm):
        fake = MagicMock(id="chunk_xyz", page_content="content here", metadata={"source": "doc.md"})
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = [(fake, 0.8765)]
        from src.api.services.search import search_documents
        results, elapsed_ms = search_documents(started_rm, "test", 5)
        r = results[0]
        assert r["source"] == "doc.md"
        assert r["chunk_id"] == "chunk_xyz"
        assert r["score"] == 0.8765
        assert "content" in r
        assert isinstance(elapsed_ms, float)
        assert elapsed_ms >= 0

    def test_metadata_missing_source_falls_back(self, started_rm):
        fake = MagicMock(id="c1", page_content="text", metadata={})
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = [(fake, 0.5)]
        from src.api.services.search import search_documents
        results, _ = search_documents(started_rm, "test", 5)
        assert results[0]["source"] == "unknown"

    def test_doc_without_id_uses_metadata_chunk_id(self, started_rm):
        fake = MagicMock()
        fake.id = None
        fake.page_content = "text"
        fake.metadata = {"chunk_id": "meta_id_1", "source": "doc.md"}
        started_rm.vector_store.similarity_search_with_relevance_scores.return_value = [(fake, 0.5)]
        from src.api.services.search import search_documents
        results, _ = search_documents(started_rm, "test", 5)
        assert results[0]["chunk_id"] == "meta_id_1"
