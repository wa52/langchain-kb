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
    mock_vs = MagicMock()
    mock_vs._collection.count.return_value = 42
    mock_kg = MagicMock()
    mock_kg.graph.number_of_nodes.return_value = 10
    mock_kg.graph.number_of_edges.return_value = 5
    rm.vector_store = mock_vs
    rm.graph = mock_kg
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


class TestLandingPage:

    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_root_links_to_docs_and_mcp(self, client):
        resp = client.get("/")
        html = resp.text
        assert "/docs" in html
        assert "/mcp" in html

    def test_root_links_to_health_api(self, client):
        resp = client.get("/")
        html = resp.text
        assert "/api/v1/health" in html

    def test_root_has_product_title(self, client):
        from config import PRODUCT_NAME
        resp = client.get("/")
        html = resp.text
        assert PRODUCT_NAME in html

    def test_root_excluded_from_openapi(self, client):
        schema = client.app.openapi()
        assert "/" not in schema.get("paths", {})
