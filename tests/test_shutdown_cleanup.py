import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.resources import ResourceManager


@pytest.fixture(autouse=True)
def reset_singleton():
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


@pytest.fixture
def mock_started_rm():
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
    rm = ResourceManager.get_instance()
    rm.startup(echo_fn=lambda _: None)
    yield rm
    for p in patches:
        p.stop()


class TestBackgroundTaskCleanup:
    def test_background_task_can_be_cancelled(self, mock_started_rm):
        async def never_ending():
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                raise

        async def run():
            rm = mock_started_rm
            task = asyncio.create_task(never_ending())
            rm._background_tasks.add(task)
            task.add_done_callback(rm._background_tasks.discard)
            assert len(rm._background_tasks) == 1
            task.cancel()
            await asyncio.sleep(0.05)
            assert len(rm._background_tasks) == 0

        asyncio.run(run())

    def test_shutdown_clears_background_tasks(self, mock_started_rm):
        async def run():
            rm = mock_started_rm
            rm.start_background_task(asyncio.sleep(100), name="long")
            assert len(rm._background_tasks) == 1
            rm._shutdown_event.set()
            rm._ensemble_retriever = None
            rm.embedding_model = None
            rm.vector_store = None
            rm.llm = None
            rm.graph = None
            rm._initialized = False
            assert rm.is_ready() is False

        asyncio.run(run())

    def test_multiple_background_tasks_all_cleared(self, mock_started_rm):
        async def run():
            rm = mock_started_rm
            rm._background_tasks.clear()
            for i in range(5):
                rm.start_background_task(asyncio.sleep(0.01), name=f"t{i}")
            assert len(rm._background_tasks) == 5
            await asyncio.sleep(0.1)
            assert len(rm._background_tasks) == 0

        asyncio.run(run())


class TestShutdownResourceCleanup:
    def test_no_residual_llm_after_shutdown(self, mock_started_rm):
        rm = mock_started_rm
        assert rm.llm is not None
        rm.shutdown(echo_fn=lambda _: None)
        assert rm.llm is None

    def test_no_residual_vector_store_after_shutdown(self, mock_started_rm):
        rm = mock_started_rm
        assert rm.vector_store is not None
        rm.shutdown(echo_fn=lambda _: None)
        assert rm.vector_store is None

    def test_no_residual_embedding_model_after_shutdown(self, mock_started_rm):
        rm = mock_started_rm
        assert rm.embedding_model is not None
        rm.shutdown(echo_fn=lambda _: None)
        assert rm.embedding_model is None

    def test_no_residual_graph_after_shutdown(self, mock_started_rm):
        rm = mock_started_rm
        assert rm.graph is not None
        rm.shutdown(echo_fn=lambda _: None)
        assert rm.graph is None

    def test_get_retriever_raises_after_shutdown(self, mock_started_rm):
        rm = mock_started_rm
        rm.shutdown(echo_fn=lambda _: None)
        with pytest.raises(RuntimeError, match="not initialized"):
            rm.get_retriever(k=5)


class TestLifespanCleanup:
    def test_lifespan_no_residual_tasks(self, mock_started_rm):
        async def run():
            from src.resources import app_lifespan
            mock_app = MagicMock()
            async with app_lifespan(mock_app):
                pass
            rm = ResourceManager.get_instance()
            assert rm._background_tasks is not None
            assert rm.is_ready() is False

        asyncio.run(run())

    def test_shutdown_idempotent_safe(self, mock_started_rm):
        rm = mock_started_rm
        rm.shutdown(echo_fn=lambda _: None)
        rm.shutdown(echo_fn=lambda _: None)
        assert rm._initialized is False
        assert rm.embedding_model is None
