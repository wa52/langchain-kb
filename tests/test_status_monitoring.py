"""监控层测试：src/status.py 状态注册表、整体状态推导、
ResourceManager/BM25/索引任务的上报接线、/api/v1/status 端点与控制台 /status。"""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_state():
    """Reset both the ResourceManager singleton and the status registry."""
    from src.resources import ResourceManager
    from src.status import reset_status
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    reset_status()
    yield
    ResourceManager._instance = None
    reset_status()


@pytest.fixture
def mock_startup_deps():
    """Mock all external dependencies ResourceManager.startup() touches."""
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


@pytest.fixture
def started_rm(mock_startup_deps):
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm.startup(echo_fn=lambda _: None)
    return rm


class TestStatusRegistry:

    def test_default_components_all_pending(self):
        from src.status import PENDING, snapshot_status
        snap = snapshot_status()
        for name in ("embedding", "llm", "vector_store", "bm25", "graph", "agent", "index"):
            assert snap[name]["state"] == PENDING, name

    def test_loading_ready_records_duration(self):
        from src.status import SystemStatus, READY, LOADING
        s = SystemStatus()
        s.set_loading("embedding", "BAAI/bge-small-zh")
        assert s.snapshot()["embedding"]["state"] == LOADING
        time.sleep(0.01)
        s.set_ready("embedding", "model-ok")
        c = s.snapshot()["embedding"]
        assert c["state"] == READY
        assert c["detail"] == "model-ok"
        assert c["duration_ms"] is not None and c["duration_ms"] > 0
        assert c["error"] is None

    def test_error_and_disabled(self):
        from src.status import SystemStatus, ERROR, DISABLED
        s = SystemStatus()
        s.set_error("llm", RuntimeError("no key"))
        c = s.snapshot()["llm"]
        assert c["state"] == ERROR
        assert "no key" in c["error"]
        s.set_disabled("graph", "ENABLE_GRAPH=false")
        assert s.snapshot()["graph"]["state"] == DISABLED

    def test_reset_all_returns_to_pending(self):
        from src.status import SystemStatus, PENDING
        s = SystemStatus()
        s.set_ready("embedding", "ok")
        s.set_error("llm", "x")
        s.reset_all()
        assert all(v["state"] == PENDING for v in s.snapshot().values())

    def test_uptime_positive(self):
        from src.status import uptime_seconds
        assert uptime_seconds() >= 0


class TestOverallState:

    def test_error_if_core_fails(self):
        from src.status import overall_state, ERROR
        comps = {
            "embedding": {"state": ERROR}, "llm": {"state": "ready"},
            "vector_store": {"state": "ready"},
        }
        assert overall_state(comps) == ERROR

    def test_ok_when_core_ready(self):
        from src.status import overall_state
        comps = {
            "embedding": {"state": "ready"}, "llm": {"state": "ready"},
            "vector_store": {"state": "ready"}, "bm25": {"state": "ready"},
            "graph": {"state": "ready"}, "agent": {"state": "pending"},
        }
        assert overall_state(comps) == "ok"

    def test_degraded_when_optional_fails(self):
        from src.status import overall_state
        comps = {
            "embedding": {"state": "ready"}, "llm": {"state": "ready"},
            "vector_store": {"state": "ready"}, "bm25": {"state": "error"},
            "graph": {"state": "ready"},
        }
        assert overall_state(comps) == "degraded"

    def test_pending_while_loading(self):
        from src.status import overall_state, PENDING
        comps = {
            "embedding": {"state": "loading"}, "llm": {"state": "pending"},
            "vector_store": {"state": "ready"},
        }
        assert overall_state(comps) == PENDING


class TestResourceManagerStatus:

    def test_startup_marks_components_ready(self, started_rm):
        from src.status import snapshot_status
        snap = snapshot_status()
        assert snap["embedding"]["state"] == "ready"
        assert snap["llm"]["state"] == "ready"
        assert snap["vector_store"]["state"] == "ready"
        assert snap["graph"]["state"] == "ready"
        # agent is lazy: stays pending until first get_agent()
        assert snap["agent"]["state"] == "pending"

    def test_get_agent_marks_agent_ready(self, started_rm):
        from src.status import snapshot_status
        with patch("src.agent.rag_agent.create_rag_agent", return_value=MagicMock()):
            started_rm.get_agent()
        assert snapshot_status()["agent"]["state"] == "ready"

    def test_get_agent_error_recorded(self, started_rm):
        from src.status import snapshot_status
        with patch(
            "src.agent.rag_agent.create_rag_agent",
            side_effect=RuntimeError("build failed"),
        ):
            with pytest.raises(RuntimeError):
                started_rm.get_agent()
        assert snapshot_status()["agent"]["state"] == "error"
        assert "build failed" in snapshot_status()["agent"]["error"]

    def test_shutdown_resets_all(self, started_rm):
        from src.status import snapshot_status, PENDING
        started_rm.shutdown(echo_fn=lambda _: None)
        assert all(v["state"] == PENDING for v in snapshot_status().values())

    def test_failed_startup_marks_loading_component_error(self, mock_startup_deps):
        from src.resources import ResourceManager
        with patch(
            "src.graph_store.graph.KnowledgeGraph", side_effect=RuntimeError("graph crash")
        ):
            rm = ResourceManager.get_instance()
            with pytest.raises(RuntimeError):
                rm.startup(echo_fn=lambda _: None)
        from src.status import snapshot_status
        # graph was still loading when startup aborted -> marked error
        assert snapshot_status()["graph"]["state"] == "error"


class TestBm25Status:

    @pytest.fixture(autouse=True)
    def _cleanup_bm25_global(self):
        from src.retrieval import retriever as retriever_mod
        saved = retriever_mod._bm25_retriever
        retriever_mod._bm25_retriever = None
        yield
        retriever_mod._bm25_retriever = saved

    def _make_store(self):
        mock_store = MagicMock()
        mock_store._collection.get.side_effect = [
            {"documents": ["text1", "text2"], "metadatas": [{"source": "a.md"}, {"source": "b.md"}]},
            {"documents": [], "metadatas": []},
        ]
        return mock_store

    @patch("src.retrieval.retriever._save_bm25_to_disk")
    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    def test_rebuild_marks_ready(self, _load, _save):
        from src.retrieval.retriever import rebuild_bm25
        from src.status import snapshot_status
        store = self._make_store()
        try:
            rebuild_bm25(store, echo_fn=lambda _: None)
        except Exception:
            pass
        snap = snapshot_status()
        assert snap["bm25"]["state"] == "ready", snap["bm25"]
        assert "全量重建" in snap["bm25"]["detail"]

    @patch("src.retrieval.retriever._save_bm25_to_disk")
    @patch("src.retrieval.retriever._load_bm25_from_disk", return_value=False)
    @patch(
        "src.retrieval.retriever.BM25Retriever.from_texts",
        side_effect=RuntimeError("bm25 broken"),
    )
    def test_rebuild_failure_marks_error(self, _from_texts, _load, _save):
        from src.retrieval.retriever import rebuild_bm25
        from src.status import snapshot_status
        store = self._make_store()
        with pytest.raises(RuntimeError, match="bm25 broken"):
            rebuild_bm25(store, echo_fn=lambda _: None)
        assert snapshot_status()["bm25"]["state"] == "error"
        assert "bm25 broken" in snapshot_status()["bm25"]["error"]

    @patch("src.retrieval.retriever._save_bm25_to_disk")
    def test_load_from_disk_marks_ready(self, _save):
        from src.retrieval import retriever as retriever_mod
        from src.status import snapshot_status
        saved = retriever_mod._bm25_retriever
        retriever_mod._bm25_retriever = None
        try:
            with patch(
                "src.retrieval.retriever._load_bm25_from_disk", return_value=True
            ):
                store = MagicMock()
                store._collection.count.return_value = 2
                retriever_mod.rebuild_bm25(store, echo_fn=lambda _: None)
            assert snapshot_status()["bm25"]["state"] == "ready"
            assert "磁盘加载" in snapshot_status()["bm25"]["detail"]
        finally:
            retriever_mod._bm25_retriever = saved


class TestIndexTaskStatus:

    def test_run_index_task_updates_status(self, tmp_path):
        import asyncio
        from src.api.services.indexing import run_index_task, get_task_manager
        from src.status import snapshot_status
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("# t", encoding="utf-8")
        mgr = get_task_manager()
        mgr._tasks.clear()
        tid = mgr.create_task(str(d))
        with patch(
            "src.ingestion.pipeline.run_add_path", return_value=7
        ):
            asyncio.run(run_index_task(tid, str(d)))
        assert snapshot_status()["index"]["state"] == "ready"
        assert "7 chunks" in snapshot_status()["index"]["detail"]

    def test_run_index_task_failure_marks_error(self, tmp_path):
        import asyncio
        from src.api.services.indexing import run_index_task, get_task_manager
        from src.status import snapshot_status
        d = tmp_path / "docs"
        d.mkdir()
        mgr = get_task_manager()
        mgr._tasks.clear()
        tid = mgr.create_task(str(d))
        with patch(
            "src.ingestion.pipeline.run_add_path", side_effect=RuntimeError("disk full")
        ):
            asyncio.run(run_index_task(tid, str(d)))
        assert snapshot_status()["index"]["state"] == "error"
        assert "disk full" in snapshot_status()["index"]["error"]


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    mock_vs = MagicMock()
    mock_vs._collection.count.return_value = 42
    mock_kg = MagicMock()
    mock_kg.graph.number_of_nodes.return_value = 10
    mock_kg.graph.number_of_edges.return_value = 5
    rm.embedding_model = MagicMock()
    rm.llm = MagicMock()
    rm.vector_store = mock_vs
    rm.graph = mock_kg
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


class TestStatusEndpoint:

    def test_status_returns_components(self, client, rm):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["vector_count"] == 42
        assert body["entity_count"] == 10
        assert isinstance(body["index_version"], int)
        comps = body["components"]
        assert set(comps) == {
            "embedding", "llm", "vector_store", "bm25", "graph", "agent", "index",
        }
        assert comps["embedding"]["state"] == "ready"
        assert comps["agent"]["state"] == "ready"
        assert comps["vector_store"]["detail"] is not None
        for name, c in comps.items():
            assert c["name"] == name
            assert isinstance(c["state"], str)

    def test_status_503_when_not_ready(self):
        from src.api.app import create_app
        app = create_app()
        c = TestClient(app)
        assert c.get("/api/v1/status").status_code == 503

    def test_status_health_consistency(self, client, rm):
        health = client.get("/api/v1/health").json()
        status = client.get("/api/v1/status").json()
        assert health["vector_count"] == status["vector_count"] == 42
        assert health["entity_count"] == status["entity_count"] == 10

    def test_status_exposed_in_openapi(self, client):
        schema = client.app.openapi()
        assert "/api/v1/status" in schema.get("paths", {})


class TestConsoleStatusCommand:

    @patch("src.vector_store.service.VectorStoreService.get_stats",
           return_value={"count": 5, "source_count": 2, "sources": ["a.md"]})
    @patch("src.graph_store.service.GraphService.get_entity_count", return_value=10)
    def test_status_command_output(self, _g, _s):
        from src.cli.console import _status_command, handle_command
        text = _status_command()
        assert "系统状态监控" in text
        for name in ("embedding", "llm", "vector_store", "bm25", "graph", "agent", "index"):
            assert name in text
        out = handle_command("/status", {"agent": None, "messages": [], "session_id": None})
        assert "embedding" in out
