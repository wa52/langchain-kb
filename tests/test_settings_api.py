"""Read-only settings API tests at the HTTP seam.

Covers the GET /api/v1/settings shape, the safe no-secret rendering of
API keys, and the read-only nature of the endpoint.
"""

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
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


class TestSettingsApi:
    def test_returns_readonly_config_view(self, client):
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "knowledge_home", "data_dir", "external_dir", "chroma_persist_dir",
            "embedding_model", "llm_model", "llm_api_configured",
            "hf_offline", "graph_enabled", "hybrid_search",
            "mcp_enabled", "lan_protection",
        ):
            assert key in body, f"missing field {key}"
        assert isinstance(body["llm_api_configured"], bool)
        assert isinstance(body["graph_enabled"], bool)
        assert isinstance(body["lan_protection"], bool)

    def test_lan_protection_reflects_token(self, client):
        with patch("config.LAN_TOKEN", ""):
            assert client.get("/api/v1/settings").json()["lan_protection"] is False
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.get(
                "/api/v1/settings",
                headers={"Authorization": "Bearer sekrit"},
            )
            assert resp.status_code == 200
            assert resp.json()["lan_protection"] is True

    def test_no_secret_leakage_when_key_configured(self, client):
        secret = "sk-test-very-secret-value-12345"
        with patch("config.DEEPSEEK_API_KEY", secret):
            resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_api_configured"] is True
        assert secret not in resp.text
        assert "api_key" not in body

    def test_key_flag_false_when_missing(self, client):
        with patch("config.DEEPSEEK_API_KEY", ""):
            resp = client.get("/api/v1/settings")
        body = resp.json()
        assert body["llm_api_configured"] is False

    def test_hf_offline_flag_reflects_env(self, client, monkeypatch):
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        assert client.get("/api/v1/settings").json()["hf_offline"] is False
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        assert client.get("/api/v1/settings").json()["hf_offline"] is True
        monkeypatch.setenv("HF_HUB_OFFLINE", "0")
        assert client.get("/api/v1/settings").json()["hf_offline"] is False
        monkeypatch.setenv("HF_HUB_OFFLINE", "false")
        assert client.get("/api/v1/settings").json()["hf_offline"] is False

    def test_base_url_credentials_are_redacted(self, client):
        with (
            patch("config.DEEPSEEK_API_BASE", "http://user:sk-secret@host:8080/v1"),
            patch("config.LOCAL_LLM_BASE", "http://127.0.0.1:11434/v1?api_key=sk-abc&x=1"),
        ):
            resp = client.get("/api/v1/settings")
        body = resp.json()
        assert "sk-secret" not in resp.text
        assert "sk-abc" not in resp.text
        assert body["llm_api_base"] == "http://host:8080/v1"
        assert "api_key=" not in body["local_llm_base"]
        assert body["local_llm_base"] == "http://127.0.0.1:11434/v1?x=1"

    def test_mcp_enabled_reflects_config_file(self, client, tmp_path):
        with patch("config.MCP_CONFIG_PATH", str(tmp_path / "mcp.json")):
            assert client.get("/api/v1/settings").json()["mcp_enabled"] is False
            (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
            assert client.get("/api/v1/settings").json()["mcp_enabled"] is True

    def test_chroma_ok_reflects_directory(self, client, tmp_path):
        with patch("config.CHROMA_PERSIST_DIR", str(tmp_path / "chroma")):
            assert client.get("/api/v1/settings").json()["chroma_ok"] is False
            (tmp_path / "chroma").mkdir()
            assert client.get("/api/v1/settings").json()["chroma_ok"] is True

    def test_no_mutating_methods(self, client):
        resp = client.post("/api/v1/settings", json={})
        assert resp.status_code == 405
        resp = client.put("/api/v1/settings", json={})
        assert resp.status_code == 405
