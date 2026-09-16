from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


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
    rm.vector_store = mock_vs
    rm.graph = mock_kg
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["vector_count"] == 42
        assert body["entity_count"] == 10
        assert isinstance(body["uptime"], float)
        assert isinstance(body["index_version"], int)

    def test_health_503_when_not_ready(self):
        from src.api.app import create_app
        app = create_app()
        c = TestClient(app)
        resp = c.get("/api/v1/health")
        assert resp.status_code == 503


class TestSearch:
    def test_search_returns_results(self, client, rm):
        fake_doc = MagicMock()
        fake_doc.id = "chunk_001"
        fake_doc.page_content = "LangChain is a framework"
        fake_doc.metadata = {"source": "doc.md"}
        rm.vector_store.similarity_search_with_relevance_scores.return_value = [
            (fake_doc, 0.95)
        ]

        resp = client.post("/api/v1/retrieval/search", json={
            "query": "LangChain",
            "top_k": 3,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 1
        r = body["results"][0]
        assert r["source"] == "doc.md"
        assert r["chunk_id"] == "chunk_001"
        assert r["score"] == 0.95
        assert r["content"] == "LangChain is a framework"
        assert isinstance(body["elapsed_ms"], float)

    def test_search_uses_top_k(self, client, rm):
        rm.vector_store.similarity_search_with_relevance_scores.return_value = []
        resp = client.post("/api/v1/retrieval/search", json={
            "query": "test",
            "top_k": 10,
        })
        assert resp.status_code == 200
        rm.vector_store.similarity_search_with_relevance_scores.assert_called_with(
            "test", k=10
        )

    def test_search_empty_query_rejected(self, client):
        resp = client.post("/api/v1/retrieval/search", json={"query": ""})
        assert resp.status_code == 422

    def test_search_top_k_out_of_range(self, client):
        resp = client.post("/api/v1/retrieval/search", json={
            "query": "test",
            "top_k": 100,
        })
        assert resp.status_code == 422


class TestChat:
    def test_chat_returns_answer(self, client):
        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()) as mock_agent,
            patch("src.api.services.chat.stream_rag_response", return_value=["Hello ", "world"]),
            patch("src.api.services.chat.save_history", return_value="sess_123"),
        ):
            resp = client.post("/api/v1/chat", json={"query": "hi"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Hello world"
        assert "citations" in body
        assert body["conversation_id"] == "sess_123"
        assert isinstance(body["elapsed_ms"], float)

    def test_chat_with_session_id(self, client):
        with (
            patch("src.api.services.chat.create_rag_agent", return_value=MagicMock()),
            patch("src.api.services.chat.stream_rag_response", return_value=["OK"]),
            patch("src.api.services.chat.load_history", return_value=[{"role": "user", "content": "prev"}]),
            patch("src.api.services.chat.save_history", return_value="sess_456"),
        ):
            resp = client.post("/api/v1/chat", json={
                "query": "follow up",
                "session_id": "sess_456",
            })
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "sess_456"

    def test_chat_empty_query_rejected(self, client):
        resp = client.post("/api/v1/chat", json={"query": ""})
        assert resp.status_code == 422


class TestIndexDocuments:
    def test_index_creates_task_and_starts_background(self, client, rm, tmp_path):
        d = tmp_path / "docs"
        d.mkdir()
        (d / "test.md").write_text("# hello", encoding="utf-8")

        # The endpoint only creates the task; patch the runner so the real
        # ingestion pipeline (embedding load + vector write + BM25 rebuild)
        # does not run against the real chroma_db/data dirs in tests.
        with patch("src.api.routers.indexing.run_index_task"):
            resp = client.post("/api/v1/documents/index", json={
                "path": str(d),
            })
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert len(body["task_id"]) > 0

    def test_index_path_not_found(self, client, rm):
        resp = client.post("/api/v1/documents/index", json={
            "path": "/nonexistent",
        })
        assert resp.status_code == 400


class TestTaskPolling:
    def test_get_task_returns_status(self, client):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        tid = mgr.create_task("/some/path")
        mgr.update_task(tid, status="running")

        resp = client.get(f"/api/v1/index/tasks/{tid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == tid
        assert body["status"] == "running"

    def test_get_task_not_found(self, client):
        resp = client.get("/api/v1/index/tasks/no-such-task")
        assert resp.status_code == 404

    def test_task_lifecycle(self, client):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        tid = mgr.create_task("/path")
        assert client.get(f"/api/v1/index/tasks/{tid}").json()["status"] == "pending"

        mgr.update_task(tid, status="running", progress="50%")
        body = client.get(f"/api/v1/index/tasks/{tid}").json()
        assert body["status"] == "running"
        assert body["progress"] == "50%"

        mgr.update_task(tid, status="done", result={"chunks_added": 15})
        body = client.get(f"/api/v1/index/tasks/{tid}").json()
        assert body["status"] == "done"
        assert body["result"]["chunks_added"] == 15


class TestErrorResponse:
    def test_unified_error_structure_on_404(self, client):
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    def test_unified_error_structure_on_422(self, client):
        resp = client.post("/api/v1/retrieval/search", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body or "detail" in body
