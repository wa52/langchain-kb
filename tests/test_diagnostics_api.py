"""Diagnostics API tests at the HTTP seam."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    from src.api.services.diagnostics import get_diagnostics_task_manager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    get_diagnostics_task_manager().clear()
    yield
    ResourceManager._instance = None
    get_diagnostics_task_manager().clear()


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    rm.vector_store = MagicMock()
    rm.graph = MagicMock()
    rm.llm = MagicMock()
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


def _fake_checks():
    return [
        {"name": "data_dirs", "ok": True, "status": "ready", "detail": "ok",
         "error": None, "duration_ms": 1.0, "fix": "", "repairable": False},
        {"name": "bm25", "ok": False, "status": "error", "detail": "stale",
         "error": "bm25 stale", "duration_ms": 2.0,
         "fix": "python -m src.monitor --repair", "repairable": True},
    ]


class TestRunDiagnostics:
    def test_run_returns_task_id(self, client, rm):
        with patch("src.api.routers.diagnostics.run_diagnostics_task", new=AsyncMock()):
            resp = client.post("/api/v1/diagnostics")
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert len(body["task_id"]) > 0

    def test_task_polls_to_done_with_result(self, client, rm):
        mgr = None

        async def fake_run(task_id):
            nonlocal mgr
            from src.api.services.diagnostics import get_diagnostics_task_manager
            mgr = get_diagnostics_task_manager()
            mgr.update_task(task_id, status="done", result={
                "checks": _fake_checks(),
                "summary": {"total": 2, "ok": 1, "failed": 1},
            })

        with patch("src.api.routers.diagnostics.run_diagnostics_task", side_effect=fake_run):
            task_id = client.post("/api/v1/diagnostics").json()["task_id"]
        # drive the coroutine synchronously
        import asyncio
        asyncio.get_event_loop().run_until_complete(fake_run(task_id))

        resp = client.get(f"/api/v1/diagnostics/tasks/{task_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "done"
        assert body["result"]["summary"] == {"total": 2, "ok": 1, "failed": 1}
        checks = body["result"]["checks"]
        assert checks[0]["name"] == "data_dirs"
        assert checks[0]["ok"] is True
        assert checks[1]["repairable"] is True

    def test_task_not_found(self, client, rm):
        resp = client.get("/api/v1/diagnostics/tasks/nope")
        assert resp.status_code == 404


class TestRepairDiagnostics:
    def test_repair_runs_monitor_for_done_task(self, client, rm):
        mgr = None

        async def fake_run(task_id):
            nonlocal mgr
            from src.api.services.diagnostics import get_diagnostics_task_manager
            mgr = get_diagnostics_task_manager()
            mgr.update_task(task_id, status="done", result={
                "checks": _fake_checks(),
                "summary": {"total": 2, "ok": 1, "failed": 1},
            })

        with patch("src.api.routers.diagnostics.run_diagnostics_task", side_effect=fake_run):
            task_id = client.post("/api/v1/diagnostics").json()["task_id"]
        import asyncio
        asyncio.get_event_loop().run_until_complete(fake_run(task_id))

        with patch("src.api.routers.diagnostics.repair_check", new=AsyncMock(return_value=True)) as m:
            resp = client.post("/api/v1/diagnostics/repair", json={
                "task_id": task_id, "name": "bm25",
            })
        assert resp.status_code == 200
        assert resp.json() == {"name": "bm25", "repaired": True}
        m.assert_awaited_once_with("bm25")

    def test_repair_requires_completed_task(self, client, rm):
        resp = client.post("/api/v1/diagnostics/repair", json={
            "task_id": "no-such-task", "name": "bm25",
        })
        assert resp.status_code == 400

    def test_repair_rejects_non_repairable_or_unknown(self, client, rm):
        mgr = None

        async def fake_run(task_id):
            nonlocal mgr
            from src.api.services.diagnostics import get_diagnostics_task_manager
            mgr = get_diagnostics_task_manager()
            mgr.update_task(task_id, status="done", result={
                "checks": [
                    {"name": "tmp_files", "ok": False, "repairable": True},
                    {"name": "llm", "ok": False, "repairable": False},
                ],
                "summary": {"total": 2, "ok": 0, "failed": 2},
            })

        with patch("src.api.routers.diagnostics.run_diagnostics_task", side_effect=fake_run):
            task_id = client.post("/api/v1/diagnostics").json()["task_id"]
        import asyncio
        asyncio.get_event_loop().run_until_complete(fake_run(task_id))

        # not in the failed/repairable set -> rejected
        resp = client.post("/api/v1/diagnostics/repair", json={
            "task_id": task_id, "name": "llm",
        })
        assert resp.status_code == 400
        resp = client.post("/api/v1/diagnostics/repair", json={
            "task_id": task_id, "name": "unknown_check",
        })
        assert resp.status_code == 400

        # valid repairable member -> allowed
        with patch("src.api.routers.diagnostics.repair_check", new=AsyncMock(return_value=True)):
            resp = client.post("/api/v1/diagnostics/repair", json={
                "task_id": task_id, "name": "tmp_files",
            })
        assert resp.status_code == 200
        assert resp.json()["repaired"] is True

    def test_run_rejects_concurrent(self, client, rm):
        with patch("src.api.routers.diagnostics.run_diagnostics_task", new=AsyncMock()):
            first = client.post("/api/v1/diagnostics")
        assert first.status_code == 202
        with patch("src.api.routers.diagnostics.run_diagnostics_task", new=AsyncMock()):
            second = client.post("/api/v1/diagnostics")
        assert second.status_code == 409
