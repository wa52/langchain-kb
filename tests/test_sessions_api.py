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
    rm.vector_store = MagicMock()
    rm.graph = MagicMock()
    rm.llm = MagicMock()
    return rm


@pytest.fixture
def client(rm, tmp_path):
    import src.agent.chat_history as ch
    ch.HISTORY_DIR = tmp_path / "chat_history"
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_sessions(client, tmp_path):
    import src.agent.chat_history as ch
    ch.save_history([
        {"role": "user", "content": "LangChain 是什么？"},
        {"role": "assistant", "content": "LangChain 是一个框架。"},
    ], "sess_a")
    ch.save_history([
        {"role": "user", "content": "RAG 是什么？"},
        {"role": "assistant", "content": "RAG 是检索增强生成。"},
    ], "sess_b")
    return client


class TestListSessions:
    def test_empty_list(self, client):
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        assert resp.json()["sessions"] == []

    def test_lists_sessions(self, sample_sessions):
        resp = sample_sessions.get("/api/v1/sessions")
        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) == 2
        ids = {s["id"] for s in sessions}
        assert ids == {"sess_a", "sess_b"}
        by_id = {s["id"]: s for s in sessions}
        assert by_id["sess_a"]["title"] == "LangChain 是什么？"
        assert by_id["sess_a"]["turns"] == 1


class TestGetSession:
    def test_get_existing(self, sample_sessions):
        resp = sample_sessions.get("/api/v1/sessions/sess_a")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "sess_a"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"

    def test_get_missing_404(self, client):
        resp = client.get("/api/v1/sessions/nonexistent")
        assert resp.status_code == 404

    def test_invalid_session_id_rejected(self, client):
        resp = client.get("/api/v1/sessions/bad$id")
        assert resp.status_code == 400


class TestDeleteSession:
    def test_delete_existing(self, sample_sessions):
        resp = sample_sessions.delete("/api/v1/sessions/sess_a")
        assert resp.status_code == 204
        assert sample_sessions.get("/api/v1/sessions/sess_a").status_code == 404

    def test_delete_missing_404(self, client):
        resp = client.delete("/api/v1/sessions/nonexistent")
        assert resp.status_code == 404
