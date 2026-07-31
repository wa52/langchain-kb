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

    def test_root_shows_global_web_command(self, client):
        resp = client.get("/")
        html = resp.text
        assert "knowledge web" in html

    def test_root_shows_global_cli_command(self, client):
        resp = client.get("/")
        html = resp.text
        assert "knowledge cli" in html

    def test_root_shows_search_command(self, client):
        resp = client.get("/")
        html = resp.text
        assert "knowledge search" in html

    def test_create_app_ensures_data_dirs(self):
        with patch("config.ensure_data_dirs") as mock:
            from src.api.app import create_app
            create_app()
        mock.assert_called_once()


class TestWorkspaceApp:

    def test_root_is_workspace_with_three_sections(self, client):
        resp = client.get("/")
        html = resp.text
        for section_id in ["chat-view", "search-view", "index-view"]:
            assert f'id="{section_id}"' in html

    def test_root_chat_hits_api(self, client):
        resp = client.get("/")
        assert '"/api/v1/chat"' in resp.text

    def test_root_search_hits_api(self, client):
        resp = client.get("/")
        assert '"/api/v1/retrieval/search"' in resp.text

    def test_root_index_hits_api(self, client):
        resp = client.get("/")
        assert '"/api/v1/documents/index"' in resp.text
        assert '"/api/v1/index/tasks/"' in resp.text

    def test_root_has_viewport_meta(self, client):
        resp = client.get("/")
        assert '<meta name="viewport"' in resp.text

    def test_root_respects_reduced_motion(self, client):
        resp = client.get("/")
        assert "prefers-reduced-motion" in resp.text

    def test_root_has_focus_visible_ring(self, client):
        resp = client.get("/")
        assert ":focus-visible" in resp.text

    def test_root_has_loading_feedback(self, client):
        resp = client.get("/")
        assert "aria-busy" in resp.text
