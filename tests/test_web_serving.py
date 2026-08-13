"""Web client serving tests at the HTTP seam.

Verifies FastAPI serves the built Vite app (web/dist) with SPA fallback
while API/MCP paths keep JSON 404s, and that the embedded single-file UI
remains the fallback when no build exists.
"""

from pathlib import Path
from unittest.mock import MagicMock

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
    rm.agent = MagicMock()
    return rm


def _make_client(monkeypatch, dist: Path | None) -> TestClient:
    from src.api import app as app_module
    monkeypatch.setattr(app_module, "WEB_DIST", dist if dist is not None else Path("no_such_web_dist"))
    return TestClient(app_module.create_app())


def _fake_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>SPA ROOT</body></html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('spa')", encoding="utf-8")
    return dist


class TestWebClientServed:
    def test_root_serves_built_index(self, rm, tmp_path, monkeypatch):
        client = _make_client(monkeypatch, _fake_dist(tmp_path))
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "SPA ROOT" in resp.text

    def test_spa_fallback_for_client_route(self, rm, tmp_path, monkeypatch):
        client = _make_client(monkeypatch, _fake_dist(tmp_path))
        resp = client.get("/chat")
        assert resp.status_code == 200
        assert "SPA ROOT" in resp.text

    def test_api_unknown_stays_json_404(self, rm, tmp_path, monkeypatch):
        client = _make_client(monkeypatch, _fake_dist(tmp_path))
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_bare_api_path_stays_json_404(self, rm, tmp_path, monkeypatch):
        client = _make_client(monkeypatch, _fake_dist(tmp_path))
        resp = client.get("/api")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_assets_served(self, rm, tmp_path, monkeypatch):
        client = _make_client(monkeypatch, _fake_dist(tmp_path))
        resp = client.get("/assets/app.js")
        assert resp.status_code == 200
        assert resp.text.strip() == "console.log('spa')"

    def test_embedded_ui_fallback_when_no_dist(self, rm, monkeypatch):
        client = _make_client(monkeypatch, None)
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "text/html" in resp.headers["content-type"]
