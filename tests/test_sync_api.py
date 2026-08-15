"""Scheduled-sync API tests at the HTTP seam."""

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


@pytest.fixture(autouse=True)
def isolate_sync(tmp_path, monkeypatch):
    import src.api.services.sync as sync
    monkeypatch.setattr(sync, "_STATUS_PATH", tmp_path / "sync_status.json")
    monkeypatch.setattr(sync, "_running", False)
    yield


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    rm.vector_store = MagicMock()
    rm.graph = MagicMock()
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


class TestSyncStatus:
    def test_defaults_when_unconfigured(self, client):
        with patch("config.EXPERIENCE_DIRS", []):
            resp = client.get("/api/v1/sync/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dirs"] == []
        assert body["enabled"] is False
        assert body["running"] is False
        assert body["last_sync_at"] is None

    def test_reflects_configured_dirs(self, client, tmp_path):
        with patch("config.EXPERIENCE_DIRS", [str(tmp_path)]):
            body = client.get("/api/v1/sync/status").json()
        assert body["enabled"] is True
        assert body["dirs"] == [str(tmp_path)]


class TestSyncDirs:
    def test_add_directory(self, client, tmp_path):
        with (
            patch("config.EXPERIENCE_DIRS", []),
            patch("dotenv.find_dotenv", return_value=str(tmp_path / ".env")),
            patch("dotenv.set_key") as mock_set_key,
        ):
            resp = client.post("/api/v1/sync/dirs", json={"path": str(tmp_path)})
        assert resp.status_code == 200
        body = resp.json()
        assert str(tmp_path.resolve()) in body["dirs"]
        mock_set_key.assert_called_once()
        key = mock_set_key.call_args.args[1]
        assert key == "EXPERIENCE_DIRS"

    def test_add_missing_directory_rejected(self, client, tmp_path):
        with patch("config.EXPERIENCE_DIRS", []):
            resp = client.post("/api/v1/sync/dirs", json={"path": str(tmp_path / "nope")})
        assert resp.status_code == 400

    def test_remove_directory(self, client, tmp_path):
        with (
            patch("config.EXPERIENCE_DIRS", [str(tmp_path)]),
            patch("dotenv.find_dotenv", return_value=str(tmp_path / ".env")),
            patch("dotenv.set_key"),
        ):
            resp = client.delete(f"/api/v1/sync/dirs?path={tmp_path}")
        assert resp.status_code == 200
        assert resp.json()["dirs"] == []


class TestSyncRun:
    def test_run_sync_starts(self, client):
        from unittest.mock import AsyncMock

        import src.api.services.sync as sync

        with patch.object(sync, "run_sync_now", AsyncMock(return_value=True)):
            resp = client.post("/api/v1/sync/run")
        assert resp.status_code == 202
        body = resp.json()
        assert body["running"] is True
        assert body["started"] is True
