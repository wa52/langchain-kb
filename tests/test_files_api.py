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
    rm.vector_store._collection.count.return_value = 42
    rm.graph = MagicMock()
    rm.graph.graph.number_of_nodes.return_value = 10
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


class TestListFiles:
    def test_list_files_returns_tracked(self, client):
        fake = [
            {"source_type": "external", "file_key": "docs.md", "hash": "abc"},
            {"source_type": "internal", "file_key": "readme.md", "hash": "def"},
        ]
        with patch("src.ingestion.tracker.list_all_files", return_value=fake):
            resp = client.get("/api/v1/files")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["files"] == fake


class TestRemoveFile:
    def test_remove_file_starts_task(self, client):
        from src.api.services.indexing import get_task_manager
        get_task_manager()._tasks.clear()
        with (
            patch("src.api.services.files.remove_file", return_value={"removed": "x.md", "keep_file": False}),
            patch("src.status.get_registry"),
        ):
            resp = client.delete("/api/v1/files/x.md")
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert len(body["task_id"]) > 0

    def test_remove_file_concurrent_rejected(self, client):
        from src.api.services.indexing import get_task_manager
        mgr = get_task_manager()
        mgr._tasks.clear()
        # simulate an active remove task for the same name
        tid = mgr.create_task("remove:x.md")
        mgr.update_task(tid, status="running")
        resp = client.delete("/api/v1/files/x.md")
        assert resp.status_code == 409
