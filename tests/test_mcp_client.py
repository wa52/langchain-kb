import json
import sys
import types
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


class TestCommandEnvironment:
    def test_connections_expand_exact_environment_variable_references(self, tmp_path, monkeypatch):
        from src.agent.mcp_client import _to_connections

        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcp": {"feishu": {
            "type": "local",
            "command": ["npx", "mcp", "-a", "${FEISHU_APP_ID}"],
        }}}), encoding="utf-8")
        monkeypatch.setenv("FEISHU_APP_ID", "cli_test")

        assert _to_connections(str(config))["feishu"]["args"] == ["mcp", "-a", "cli_test"]

    def test_connections_skip_missing_command_environment_variable(self, tmp_path, monkeypatch):
        from src.agent.mcp_client import _to_connections

        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcp": {"feishu": {
            "type": "local",
            "command": ["npx", "mcp", "-a", "${FEISHU_APP_ID}"],
        }}}), encoding="utf-8")
        monkeypatch.delenv("FEISHU_APP_ID", raising=False)

        assert _to_connections(str(config)) == {}


class TestLoadTools:
    def test_load_returns_tools(self, sample_config, monkeypatch):
        from unittest.mock import MagicMock
        from src.agent.mcp_client import load_mcp_tools

        fake_tools = TestServerDispatch()._fake_server_tools()

        async def fake_get_tools(server_name=None):
            return fake_tools

        mock_client = MagicMock()
        mock_client.return_value.get_tools = fake_get_tools
        module = types.ModuleType("langchain_mcp_adapters.client")
        module.MultiServerMCPClient = mock_client
        monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", module)
        tools = load_mcp_tools(sample_config)
        # 2 个 enabled server，每个返回两个 operation tool。
        assert len(tools) == 4
        assert {tool.name for tool in tools} == {"list_directory", "read_file"}

    def test_load_failure_returns_empty(self, sample_config, monkeypatch):
        from src.agent.mcp_client import load_mcp_tools

        module = types.ModuleType("langchain_mcp_adapters.client")
        module.MultiServerMCPClient = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", module)
        tools = load_mcp_tools(sample_config)
        assert tools == []

    def test_loaded_entries_keep_server_and_discovery_metadata(self, sample_config, monkeypatch):
        from unittest.mock import MagicMock
        from src.agent.mcp_client import load_mcp_tool_entries

        fake_tools = TestServerDispatch()._fake_server_tools()

        async def fake_get_tools(server_name=None):
            return fake_tools

        mock_client = MagicMock()
        mock_client.return_value.get_tools = fake_get_tools
        module = types.ModuleType("langchain_mcp_adapters.client")
        module.MultiServerMCPClient = mock_client
        monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", module)

        entries = load_mcp_tool_entries(sample_config)

        assert len(entries) == 4
        assert {entry.server_id for entry in entries} == {"filesystem", "remote_svc"}
        assert all("mcp" in entry.tags and "read" in entry.tags for entry in entries)
        assert all(entry.read_only and entry.retryable for entry in entries)


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

    def test_catalog_registration_keeps_mcp_tool_metadata(self):
        """Discovery owns registration; it must retain execution metadata."""
        from unittest.mock import MagicMock
        from src.agent.mcp_client import McpToolEntry, _register_mcp_entries
        from src.harness import ToolRegistry

        tool = MagicMock()
        tool.name = "github_create_issue"
        tool.description = "Create a GitHub issue"
        tool.args_schema = None
        entry = McpToolEntry(
            tool=tool,
            server_id="github",
            tags=("github", "mcp", "write"),
            risk_level="medium",
            retryable=False,
            read_only=False,
        )
        registry = ToolRegistry()

        _register_mcp_entries(registry, [entry])

        spec = registry.get("github_create_issue")
        assert spec.source == "mcp"
        assert spec.server_id == "github"
        assert spec.tags == ("github", "mcp", "write")
        assert spec.risk_level == "medium"
        assert not spec.read_only
        assert not spec.retryable

    def test_agent_starts_mcp_catalog_discovery(self):
        """The agent triggers asynchronous discovery without blocking startup."""
        from unittest.mock import patch
        from src.agent import rag_agent
        from src.harness import ToolRegistry

        registry = ToolRegistry()
        with (
            patch("src.agent.rag_agent.get_embedding_model"),
            patch("src.agent.rag_agent.get_vector_store"),
            patch("src.agent.rag_agent.VectorStoreService"),
            patch("src.agent.rag_agent.get_llm"),
            patch("src.agent.rag_agent.create_deep_agent"),
            patch("src.agent.mcp_client.ensure_mcp_tools_registered") as discover,
        ):
            rag_agent.create_rag_agent(registry)

        discover.assert_called_once_with(registry)


class TestSyncCompatible:
    def _async_only_tool(self):
        """Build a StructuredTool with only async (coroutine) impl, func=None."""
        import asyncio
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field

        class Args(BaseModel):
            path: str = Field(description="path")

        async def _impl(path: str) -> str:
            await asyncio.sleep(0)
            return f"read {path}"

        return StructuredTool.from_function(
            coroutine=_impl,
            name="fs_read",
            description="read file",
            args_schema=Args,
        )

    def test_wrapped_tool_supports_sync(self):
        from src.agent.mcp_client import _make_sync_compatible

        tool = self._async_only_tool()
        assert getattr(tool, "func", None) is None  # 确认原工具 async-only

        wrapped = _make_sync_compatible(tool)
        result = wrapped.invoke({"path": "D:/"})
        assert result == "read D:/"

    def test_wrapped_keeps_async(self):
        import asyncio
        from src.agent.mcp_client import _make_sync_compatible

        tool = self._async_only_tool()
        wrapped = _make_sync_compatible(tool)
        result = asyncio.run(wrapped.ainvoke({"path": "D:/"}))
        assert result == "read D:/"

    def test_wrapped_preserves_metadata(self):
        from src.agent.mcp_client import _make_sync_compatible

        tool = self._async_only_tool()
        wrapped = _make_sync_compatible(tool)
        assert wrapped.name == "fs_read"
        assert "read file" in wrapped.description

    def test_existing_sync_tool_untouched(self):
        from src.agent.mcp_client import _make_sync_compatible
        from langchain_core.tools import tool

        @tool
        def local_tool(x: int) -> int:
            """Local tool."""
            return x + 1

        wrapped = _make_sync_compatible(local_tool)
        assert wrapped.func is not None
        assert wrapped.invoke({"x": 1}) == 2


class TestServerDispatch:
    def _fake_server_tools(self):
        """Two fake sync tools under one 'filesystem' server."""
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field

        class ListArgs(BaseModel):
            path: str = Field(description="path")

        class ReadArgs(BaseModel):
            path: str = Field(description="path")

        def list_dir(path: str) -> str:
            return f"list {path}"

        def read_file(path: str) -> str:
            return f"read {path}"

        return [
            StructuredTool.from_function(func=list_dir, name="list_directory", description="list dir", args_schema=ListArgs),
            StructuredTool.from_function(func=read_file, name="read_file", description="read file", args_schema=ReadArgs),
        ]

    def test_dispatch_returns_single_tool(self):
        from src.agent.mcp_client import _server_dispatch_tool
        tool = _server_dispatch_tool("filesystem", self._fake_server_tools())
        assert tool.name == "filesystem"
        # 工具 args_schema 含 operation
        assert "operation" in tool.args_schema.model_fields

    def test_dispatch_routes_operation(self):
        from src.agent.mcp_client import _server_dispatch_tool
        tool = _server_dispatch_tool("filesystem", self._fake_server_tools())
        r = tool.invoke({"operation": "list_directory", "path": "D:/"})
        assert r == "list D:/"
        r2 = tool.invoke({"operation": "read_file", "path": "D:/x.txt"})
        assert r2 == "read D:/x.txt"

    def test_dispatch_omits_null_optional_arguments(self):
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
        from src.agent.mcp_client import _server_dispatch_tool

        class ReadArgs(BaseModel):
            path: str = Field(description="path")
            head: int | None = None
            tail: int | None = None

        def read_file(path: str, head: int | None = None, tail: int | None = None) -> str:
            return f"{path}:{head}:{tail}"

        tool = _server_dispatch_tool(
            "filesystem",
            [StructuredTool.from_function(
                func=read_file,
                name="read_text_file",
                description="read file",
                args_schema=ReadArgs,
            )],
        )
        assert tool.invoke({
            "operation": "read_text_file",
            "path": "D:/x.txt",
            "head": None,
            "tail": None,
        }) == "D:/x.txt:None:None"

    def test_dispatch_unknown_operation(self):
        from src.agent.mcp_client import _server_dispatch_tool
        tool = _server_dispatch_tool("filesystem", self._fake_server_tools())
        r = tool.invoke({"operation": "delete", "path": "D:/"})
        assert "未知操作" in r
        assert "list_directory" in r

    def test_dispatch_description_lists_operations(self):
        from src.agent.mcp_client import _server_dispatch_tool
        tool = _server_dispatch_tool("filesystem", self._fake_server_tools())
        assert "list_directory" in tool.description
        assert "read_file" in tool.description


class TestLoadToolsConverged:
    def test_background_discovery_never_blocks_local_agent_start(self, monkeypatch):
        import threading
        import time
        from src.agent.mcp_client import ensure_mcp_tools_registered
        from src.harness.tools import ToolRegistry

        entered = threading.Event()
        release = threading.Event()

        def slow_discovery(_path, _server):
            entered.set()
            release.wait(timeout=1)
            return []

        monkeypatch.setattr("src.agent.mcp_client._enabled_servers", lambda _path: {"github": {}})
        monkeypatch.setattr("src.agent.mcp_client._to_connections", lambda _path: {"github": {}})
        monkeypatch.setattr("src.agent.mcp_client.load_mcp_tool_entries_for_server", slow_discovery)
        registry = ToolRegistry()
        started = time.perf_counter()
        ensure_mcp_tools_registered(registry, "unused.json")

        assert time.perf_counter() - started < 0.1
        assert entered.wait(timeout=0.5)
        assert registry._mcp_catalog_discovering is True
        release.set()

    def test_domain_readiness_waits_only_for_requested_server(self, monkeypatch):
        import threading
        import time
        from src.agent.mcp_client import (
            MCP_CATALOG_DISCOVERING,
            MCP_CATALOG_READY,
            ensure_mcp_tools_registered,
            mcp_catalog_readiness,
        )
        from src.harness.tools import ToolRegistry

        github_started = threading.Event()
        github_release = threading.Event()
        filesystem_release = threading.Event()

        def discover(_path, server_name):
            if server_name == "github":
                github_started.set()
                github_release.wait(timeout=1)
            else:
                filesystem_release.wait(timeout=1)
            return []

        monkeypatch.setattr("src.agent.mcp_client._enabled_servers", lambda _path: {"github": {}, "filesystem": {}})
        monkeypatch.setattr("src.agent.mcp_client._to_connections", lambda _path, server_names=None: {
            name: {} for name in {"github", "filesystem"} if server_names is None or name in server_names
        })
        monkeypatch.setattr("src.agent.mcp_client.load_mcp_tool_entries_for_server", discover)
        registry = ToolRegistry()
        ensure_mcp_tools_registered(registry, "unused.json")
        assert github_started.wait(timeout=0.5)
        assert registry._mcp_server_states["github"] == MCP_CATALOG_DISCOVERING

        def release_github():
            time.sleep(0.03)
            github_release.set()

        threading.Thread(target=release_github, daemon=True).start()
        status = mcp_catalog_readiness(registry, "github", timeout_seconds=0.2)

        assert status["state"] == MCP_CATALOG_READY
        assert 15 <= status["waited_ms"] <= 200
        # The unrelated filesystem server can still be discovering; it did not
        # delay GitHub becoming selectable.
        assert registry._mcp_server_states["filesystem"] == MCP_CATALOG_DISCOVERING
        filesystem_release.set()

    def test_domain_readiness_degrades_missing_server_without_waiting(self):
        from src.agent.mcp_client import mcp_catalog_readiness
        from src.harness.tools import ToolRegistry

        status = mcp_catalog_readiness(ToolRegistry(), "github", timeout_seconds=0.2)
        assert status == {"domain": "github", "state": "NOT_APPLICABLE", "waited_ms": 0.0}

    def test_discovery_timeout_returns_control_to_the_agent(self):
        import asyncio
        from src.agent.mcp_client import _get_tools_with_timeout

        class SlowClient:
            async def get_tools(self, server_name=None):
                await asyncio.sleep(1)

        with pytest.raises(TimeoutError):
            asyncio.run(_get_tools_with_timeout(SlowClient(), "slow", timeout_seconds=0.001))

    def test_load_returns_one_tool_per_server(self, sample_config, monkeypatch):
        """dispatch 模式保留每个 server 一个调度工具的兼容行为。"""
        from unittest.mock import MagicMock
        from src.agent.mcp_client import load_mcp_tools

        fake_tools = TestServerDispatch()._fake_server_tools()

        async def fake_get_tools(server_name=None):
            return fake_tools

        mock_client = MagicMock()
        mock_client.return_value.get_tools = fake_get_tools
        module = types.ModuleType("langchain_mcp_adapters.client")
        module.MultiServerMCPClient = mock_client
        monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", module)
        tools = load_mcp_tools(sample_config, tool_mode="dispatch")

        # sample_config 有 2 个 enabled server → 2 个收敛工具
        assert len(tools) == 2
        names = [getattr(t, "name", str(t)) for t in tools]
        assert "filesystem" in names
        assert "remote_svc" in names

    def test_one_server_failure_does_not_hide_other_servers(self, sample_config, monkeypatch):
        from unittest.mock import MagicMock
        from src.agent.mcp_client import load_mcp_tools

        fake_tools = TestServerDispatch()._fake_server_tools()

        async def fake_get_tools(server_name=None):
            if server_name == "filesystem":
                raise RuntimeError("filesystem unavailable")
            return fake_tools

        mock_client = MagicMock()
        mock_client.return_value.get_tools = fake_get_tools
        module = types.ModuleType("langchain_mcp_adapters.client")
        module.MultiServerMCPClient = mock_client
        monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", module)
        tools = load_mcp_tools(sample_config)

        assert len(tools) == 2

    def test_agent_tools_unaffected(self):
        """本地工具仍保留。"""
        from src.agent import rag_agent
        assert rag_agent.retrieve_knowledge is not None
        assert rag_agent.project_workflow is not None
