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


@pytest.fixture
def mock_deps():
    """Mock all external dependencies that ResourceManager.startup() touches."""
    patches = [
        patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()),
        patch("src.llm.client.get_llm", return_value=MagicMock()),
        patch("src.resources.Chroma", return_value=MagicMock()),
        patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
        patch("src.retrieval.retriever.rebuild_bm25"),
        patch("src.vector_store.chroma_client.set_vector_store"),
        patch("src.graph_store.retriever.set_graph"),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


class TestResourceManagerSingleton:

    def test_singleton_returns_same_instance(self):
        rm1 = ResourceManager.get_instance()
        rm2 = ResourceManager.get_instance()
        assert rm1 is rm2

    def test_singleton_not_initialized_by_default(self):
        rm = ResourceManager.get_instance()
        assert rm.is_ready() is False
        assert rm.embedding_model is None
        assert rm.vector_store is None
        assert rm.llm is None


class TestResourceManagerStartup:

    def test_startup_initializes_all_resources(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)

        assert rm.is_ready() is True
        assert rm.embedding_model is not None
        assert rm.llm is not None
        assert rm.vector_store is not None
        assert rm.graph is not None

    def test_startup_idempotent(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        rm.startup(echo_fn=lambda _: None)

        assert rm.is_ready() is True

    def test_startup_initializes_resources_exactly_once(self, mock_deps):
        with (
            patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()) as mock_emb,
            patch("src.resources.Chroma", return_value=MagicMock()) as mock_chroma,
            patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()) as mock_kg,
            patch("src.retrieval.retriever.rebuild_bm25") as mock_rebuild,
        ):
            rm = ResourceManager.get_instance()
            rm.startup(echo_fn=lambda _: None)

            mock_emb.assert_called_once()
            mock_chroma.assert_called_once()
            mock_kg.assert_called_once()
            mock_rebuild.assert_called_once()


class TestRetrieverCaching:

    def test_retriever_is_cached(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_vs = MagicMock()
        mock_vs.as_retriever.return_value = _make_retriever_mock()
        rm.vector_store = mock_vs

        r1 = rm.get_retriever(k=5)
        r2 = rm.get_retriever(k=5)

        assert r1 is r2
        mock_vs.as_retriever.assert_called_once()

    def test_retriever_recreated_after_cache_invalidation(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_vs = MagicMock()
        mock_vs.as_retriever.side_effect = lambda **_: _make_retriever_mock()
        rm.vector_store = mock_vs

        r1 = rm.get_retriever(k=5)
        rm.invalidate_retriever_cache()
        r2 = rm.get_retriever(k=5)

        assert r1 is not r2
        assert mock_vs.as_retriever.call_count == 2

    def test_index_version_increments_on_invalidation(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        v0 = rm.get_index_version()
        rm.invalidate_retriever_cache()
        v1 = rm.get_index_version()
        assert v1 == v0 + 1

    def test_retriever_cached_per_k_value(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        mock_vs = MagicMock()
        mock_vs.as_retriever.side_effect = lambda **_: _make_retriever_mock()
        rm.vector_store = mock_vs

        r5a = rm.get_retriever(k=5)
        r5b = rm.get_retriever(k=5)

        assert r5a is r5b
        assert mock_vs.as_retriever.call_count == 1

        r10 = rm.get_retriever(k=10)
        assert r10 is not r5a
        assert mock_vs.as_retriever.call_count == 2

        r5c = rm.get_retriever(k=5)
        assert r5c is not r5a
        assert mock_vs.as_retriever.call_count == 3


class TestResourceManagerShutdown:

    def test_shutdown_clears_resources(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        assert rm.is_ready() is True

        rm.shutdown(echo_fn=lambda _: None)
        assert rm.is_ready() is False
        assert rm.embedding_model is None
        assert rm.vector_store is None
        assert rm.llm is None
        assert rm._cached_k is None

    def test_shutdown_idempotent(self, mock_deps):
        rm = ResourceManager.get_instance()
        rm.startup(echo_fn=lambda _: None)
        rm.shutdown(echo_fn=lambda _: None)
        rm.shutdown(echo_fn=lambda _: None)
        assert rm.is_ready() is False


class TestExistingSingletonsSynced:

    def test_startup_syncs_chroma_and_graph_singletons(self, mock_deps):
        with (
            patch("src.vector_store.chroma_client.set_vector_store") as mock_set_vs,
            patch("src.graph_store.retriever.set_graph") as mock_set_g,
        ):
            rm = ResourceManager.get_instance()
            rm.startup(echo_fn=lambda _: None)

            mock_set_vs.assert_called_once_with(rm.vector_store)
            mock_set_g.assert_called_once_with(rm.graph)


class TestFastAPILifespan:

    def test_app_lifespan_integration(self, mock_deps):
        from src.resources import app_lifespan

        mock_app = MagicMock()

        import asyncio
        async def run():
            async with app_lifespan(mock_app):
                rm = ResourceManager.get_instance()
                assert rm.is_ready() is True

            assert rm.is_ready() is False

        asyncio.run(run())


class TestBackgroundTasks:

    def test_start_background_task(self, mock_deps):
        import asyncio

        async def dummy_task():
            await asyncio.sleep(0.01)
            return 42

        async def run():
            rm = ResourceManager.get_instance()
            rm.start_background_task(dummy_task(), name="test")
            assert len(rm._background_tasks) == 1
            await asyncio.sleep(0.05)
            assert len(rm._background_tasks) == 0

        asyncio.run(run())

    def test_background_task_error_does_not_crash(self, mock_deps):
        import asyncio

        async def failing_task():
            raise ValueError("test error")

        async def run():
            rm = ResourceManager.get_instance()
            rm.start_background_task(failing_task(), name="failing")
            await asyncio.sleep(0.05)
            assert len(rm._background_tasks) == 0

        asyncio.run(run())
