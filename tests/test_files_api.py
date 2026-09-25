from unittest.mock import MagicMock, patch
import asyncio
import time

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


class TestSourceHealthAudit:
    def test_only_one_source_health_audit_can_run_at_a_time(self, client):
        from src.api.services.source_health import get_source_health_task_manager

        manager = get_source_health_task_manager()
        manager.clear()
        manager.create_task()

        resp = client.post("/api/v1/files/health-audit")

        assert resp.status_code == 409
        manager.clear()

    def test_listing_files_does_not_trigger_a_health_scan(self, client):
        with patch("src.bootstrap.composition.create_source_health_auditor") as create_auditor:
            resp = client.get("/api/v1/files")

        assert resp.status_code == 200
        create_auditor.assert_not_called()

    def test_start_and_poll_health_audit(self, client):
        from src.api.services.source_health import get_source_health_task_manager

        manager = get_source_health_task_manager()
        manager.clear()

        async def finish_task(task_id):
            manager.update_task(
                task_id,
                status="done",
                progress={"checked": 1, "total": 1},
                result={
                    "summary": {
                        "total": 1, "checked": 1, "healthy": 1, "missing": 0,
                        "changed": 0, "duplicate_files": 0, "unreadable": 0,
                        "unresolved": 0, "issues_total": 0,
                    },
                    "issues": [],
                    "issues_truncated": False,
                },
                completed_at="2026-09-25T00:00:00+00:00",
            )

        with patch("src.api.routers.files.run_source_health_task", new=finish_task):
            with TestClient(client.app) as active_client:
                started = active_client.post("/api/v1/files/health-audit")
                assert started.status_code == 202
                body = started.json()
                assert body["task_id"]

                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    status = active_client.get(f"/api/v1/files/health-audit/{body['task_id']}")
                    if status.json()["status"] == "done":
                        break
                    time.sleep(0.01)

        assert status.status_code == 200
        assert status.json()["result"]["summary"]["healthy"] == 1
        assert status.headers["cache-control"] == "no-store"
        manager.clear()
