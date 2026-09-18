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
        with (
            patch("config.DEEPSEEK_API_KEY", ""),
            patch("config.LLM_API_KEY", ""),
        ):
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
            patch("config.LLM_API_BASE", ""),
            patch("config.LOCAL_LLM_BASE", "http://127.0.0.1:11434/v1?api_key=sk-abc&x=1"),
        ):
            resp = client.get("/api/v1/settings")
        body = resp.json()
        assert "sk-secret" not in resp.text
        assert "sk-abc" not in resp.text
        assert body["llm_api_base"] == "http://host:8080/v1"
        assert "api_key=" not in body["local_llm_base"]
        assert body["local_llm_base"] == "http://127.0.0.1:11434/v1?x=1"

    def test_mcp_view_lists_servers_without_secrets(self, client, tmp_path):
        config_path = tmp_path / "mcp.json"
        config_path.write_text(
            '{"mcp":{"browser":{"type":"local","command":["npx","secret"],"enabled":true},'
            '"remote":{"type":"remote","url":"https://user:secret@example.com/mcp?api_key=x",'
            '"headers":{"Authorization":"Bearer hidden"},"enabled":false}}}',
            encoding="utf-8",
        )
        with (
            patch("config.MCP_CONFIG_PATH", str(config_path)),
            patch("config.MCP_ENABLED", True),
        ):
            body = client.get("/api/v1/settings").json()
        assert body["mcp_enabled"] is True
        assert [server["name"] for server in body["mcp_servers"]] == ["browser", "remote"]
        assert body["mcp_servers"][1]["target"] == "https://example.com/mcp"
        assert "secret" not in str(body["mcp_servers"])
        assert "hidden" not in str(body["mcp_servers"])
        assert isinstance(body["mcp_http_available"], bool)

    def test_global_mcp_switch_hot_reloads_agent(self, client, tmp_path):
        import config

        original = config.MCP_ENABLED
        try:
            with (
                patch("config.KNOWLEDGE_HOME", tmp_path),
                patch("dotenv.set_key") as set_key,
                patch("src.api.services.settings._drop_agent_for_mcp_reload") as reload_agent,
            ):
                resp = client.post("/api/v1/settings/mcp", json={"enabled": False})
            assert resp.status_code == 200
            assert resp.json()["mcp_enabled"] is False
            set_key.assert_called_once_with(str(tmp_path / ".env"), "MCP_ENABLED", "false")
            reload_agent.assert_called_once()
        finally:
            config.MCP_ENABLED = original

    def test_single_mcp_server_switch_updates_config(self, client, tmp_path):
        import json

        config_path = tmp_path / "mcp.json"
        config_path.write_text(
            '{"mcp":{"browser":{"type":"local","command":["npx"],"enabled":true}}}',
            encoding="utf-8",
        )
        with (
            patch("config.MCP_CONFIG_PATH", str(config_path)),
            patch("src.api.services.settings._drop_agent_for_mcp_reload") as reload_agent,
        ):
            resp = client.post(
                "/api/v1/settings/mcp/server",
                json={"name": "browser", "enabled": False},
            )
        assert resp.status_code == 200
        assert json.loads(config_path.read_text(encoding="utf-8"))["mcp"]["browser"]["enabled"] is False
        reload_agent.assert_called_once()

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


class TestGraphModeToggle:
    def test_enable_llm_mode_persists_and_applies(self, client, tmp_path):
        import config

        original = config.ENABLE_GRAPH_LLM_EXTRACTION
        try:
            with (
                patch("config.KNOWLEDGE_HOME", tmp_path),
                patch("dotenv.set_key") as mock_set_key,
            ):
                resp = client.post("/api/v1/settings/graph-mode", json={"enabled": True})
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["graph_llm_extraction"] is True
            mock_set_key.assert_called_once_with(
                str(tmp_path / ".env"), "ENABLE_GRAPH_LLM_EXTRACTION", "true"
            )
            # takes effect immediately for the settings view
            assert config.ENABLE_GRAPH_LLM_EXTRACTION is True
            assert client.get("/api/v1/settings").json()["graph_llm_extraction"] is True
        finally:
            config.ENABLE_GRAPH_LLM_EXTRACTION = original

    def test_disable_jieba_mode(self, client, tmp_path):
        import config

        original = config.ENABLE_GRAPH_LLM_EXTRACTION
        try:
            with (
                patch("config.KNOWLEDGE_HOME", tmp_path),
                patch("dotenv.set_key") as mock_set_key,
            ):
                resp = client.post("/api/v1/settings/graph-mode", json={"enabled": False})
            assert resp.status_code == 200
            assert resp.json()["graph_llm_extraction"] is False
            mock_set_key.assert_called_once_with(
                str(tmp_path / ".env"), "ENABLE_GRAPH_LLM_EXTRACTION", "false"
            )
            assert config.ENABLE_GRAPH_LLM_EXTRACTION is False
        finally:
            config.ENABLE_GRAPH_LLM_EXTRACTION = original

    def test_invalid_body_rejected(self, client):
        resp = client.post("/api/v1/settings/graph-mode", json={"enabled": "not-a-bool"})
        assert resp.status_code == 422

    def test_missing_body_rejected(self, client):
        resp = client.post("/api/v1/settings/graph-mode", json={})
        assert resp.status_code == 422
