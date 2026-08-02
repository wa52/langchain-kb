import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_config(tmp_path):
    cfg = {
        "mcp": {
            "filesystem": {
                "type": "local",
                "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "D:/"],
                "enabled": True,
            },
            "remote_svc": {
                "type": "remote",
                "url": "https://example.com/mcp",
                "enabled": True,
                "headers": {"Authorization": "Bearer x"},
            },
            "disabled_svc": {
                "type": "local",
                "command": ["python", "server.py"],
                "enabled": False,
            },
        }
    }
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(p)


class TestParseMcpConfig:
    def test_parses_servers(self, sample_config):
        from src.agent.mcp_client import parse_mcp_config
        servers = parse_mcp_config(sample_config)
        assert set(servers.keys()) == {"filesystem", "remote_svc", "disabled_svc"}

    def test_only_enabled_servers(self, sample_config):
        from src.agent.mcp_client import _enabled_servers
        enabled = _enabled_servers(sample_config)
        assert set(enabled.keys()) == {"filesystem", "remote_svc"}


class TestConnections:
    def test_local_connection_stdio(self, sample_config):
        from src.agent.mcp_client import _to_connections
        conns = _to_connections(sample_config)
        fs = conns["filesystem"]
        assert fs["transport"] == "stdio"
        assert fs["command"] == "npx"
        assert "-y" in fs["args"]

    def test_remote_connection_http(self, sample_config):
        from src.agent.mcp_client import _to_connections
        conns = _to_connections(sample_config)
        r = conns["remote_svc"]
        assert r["transport"] == "streamable-http"
        assert r["url"] == "https://example.com/mcp"
        assert r["headers"]["Authorization"] == "Bearer x"

    def test_missing_config_returns_empty(self, tmp_path):
        from src.agent.mcp_client import parse_mcp_config
        assert parse_mcp_config(str(tmp_path / "none.json")) == {}


class TestLoadTools:
    def test_load_returns_tools(self, sample_config):
        from unittest.mock import MagicMock, patch
        from src.agent.mcp_client import load_mcp_tools

        fake_tools = [MagicMock(), MagicMock()]

        async def fake_get_tools():
            return fake_tools

        with patch("langchain_mcp_adapters.client.MultiServerMCPClient") as MockClient:
            instance = MockClient.return_value
            instance.get_tools = fake_get_tools
            tools = load_mcp_tools(sample_config)
        assert len(tools) == 2

    def test_load_failure_returns_empty(self, sample_config):
        from unittest.mock import patch
        from src.agent.mcp_client import load_mcp_tools

        with patch("langchain_mcp_adapters.client.MultiServerMCPClient",
                   side_effect=RuntimeError("boom")):
            tools = load_mcp_tools(sample_config)
        assert tools == []


class TestRagAgentIntegration:
    def test_agent_loads_external_tools(self, sample_config):
        from unittest.mock import MagicMock, patch
        from src.agent import rag_agent

        with (
            patch("src.agent.mcp_client.load_mcp_tools") as m_load,
            patch("src.agent.rag_agent.get_embedding_model"),
            patch("src.agent.rag_agent.get_vector_store"),
            patch("src.agent.rag_agent.VectorStoreService"),
            patch("src.agent.rag_agent.get_llm"),
            patch("src.agent.rag_agent.create_deep_agent") as m_create,
        ):
            m_load.return_value = ["ext_tool_1", "ext_tool_2"]
            rag_agent.create_rag_agent()
            tools = m_create.call_args.kwargs["tools"]
            assert "ext_tool_1" in tools
            assert "ext_tool_2" in tools
