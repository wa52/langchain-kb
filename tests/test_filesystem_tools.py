import asyncio
import json
from pathlib import Path

import pytest


def _run_async(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _filesystem_config(path: Path, root: Path) -> Path:
    config = path / "mcp.json"
    config.write_text(json.dumps({
        "mcp": {
            "filesystem": {
                "type": "local",
                "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", str(root)],
                "enabled": True,
            }
        }
    }), encoding="utf-8")
    return config


def test_filesystem_tool_rejects_paths_outside_configured_roots(tmp_path):
    from src.agent.filesystem_tools import validate_filesystem_path

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    config_path = _filesystem_config(tmp_path, allowed)
    secret = outside / "private.txt"
    secret.write_text("must not be read", encoding="utf-8")

    with pytest.raises(PermissionError, match="不在 filesystem MCP 授权目录内"):
        validate_filesystem_path(str(secret), config_path=config_path)


def test_inspect_tool_reports_duplicate_files_without_exposing_contents(tmp_path, monkeypatch):
    from src.agent.filesystem_tools import inspect_local_path

    allowed = tmp_path / "allowed"
    left = allowed / "left"
    right = allowed / "right"
    left.mkdir(parents=True)
    right.mkdir()
    (left / "same.hdev").write_text("unique-file-content", encoding="utf-8")
    (right / "renamed.hdev").write_text("unique-file-content", encoding="utf-8")
    (right / "only-there.md").write_text("different-content", encoding="utf-8")
    config_path = _filesystem_config(tmp_path, allowed)
    monkeypatch.setattr("src.agent.filesystem_tools.default_mcp_config_path", lambda: str(config_path))

    result = json.loads(inspect_local_path.invoke({
        "path": str(left), "compare_with": str(right),
    }))

    assert result["file_count"] == 1
    assert result["compare_file_count"] == 2
    assert result["duplicate_file_count"] == 1
    assert result["duplicate_pairs"] == [{"path": "same.hdev", "matches": ["renamed.hdev"]}]
    assert "unique-file-content" not in json.dumps(result)


def test_index_tool_uses_existing_duplicate_aware_ingestion_and_invalidates_cache(tmp_path, monkeypatch):
    from src.agent.filesystem_tools import index_local_path

    allowed = tmp_path / "allowed"
    source = allowed / "docs"
    source.mkdir(parents=True)
    (source / "guide.md").write_text("synthetic source", encoding="utf-8")
    config_path = _filesystem_config(tmp_path, allowed)
    monkeypatch.setattr("src.agent.filesystem_tools.default_mcp_config_path", lambda: str(config_path))
    add_calls = []
    monkeypatch.setattr("src.ingestion.pipeline.run_add_path", lambda *args, **kwargs: add_calls.append((args, kwargs)) or 3)

    class ResourceManager:
        invalidated = 0

        def invalidate_retriever_cache(self):
            self.invalidated += 1

    manager = ResourceManager()
    monkeypatch.setattr("src.resources.ResourceManager.get_instance", lambda: manager)

    result = index_local_path.invoke({"path": str(source)})

    assert "3" in result
    assert add_calls[0][0][0] == str(source.resolve())
    assert manager.invalidated == 1


def test_agent_plugin_registers_filesystem_tools_with_write_metadata():
    from src.harness.events import EventBus
    from src.harness.plugins import PluginContext
    from src.harness.tools import ToolRegistry
    from src.bootstrap.agent_tools import AgentToolsPlugin

    registry = ToolRegistry()
    context = PluginContext(EventBus(), registry, {})
    _run_async(AgentToolsPlugin().start(context))

    inspect_spec = registry.get("inspect_local_path")
    index_spec = registry.get("index_local_path")
    assert "filesystem" in inspect_spec.tags and inspect_spec.read_only
    assert "filesystem" in index_spec.tags and not index_spec.read_only
    assert index_spec.risk_level == "medium"


def test_index_tool_requires_agent_approval(monkeypatch):
    from src.harness.events import EventBus
    from src.harness.plugins import PluginContext
    from src.harness.tools import ToolRegistry
    from src.bootstrap.agent_tools import AgentToolsPlugin
    from src.agent import rag_agent

    registry = ToolRegistry()
    _run_async(AgentToolsPlugin().start(PluginContext(EventBus(), registry, {})))
    captured = {}
    monkeypatch.setattr(rag_agent, "ENABLE_HYBRID_SEARCH", False)
    monkeypatch.setattr(rag_agent, "get_embedding_model", lambda: object())
    monkeypatch.setattr(rag_agent, "get_vector_store", lambda: object())
    monkeypatch.setattr(rag_agent, "get_llm", lambda **_: object())
    monkeypatch.setattr(rag_agent, "_create_checkpointer", lambda: (object(), None))
    monkeypatch.setattr("src.agent.mcp_client.ensure_mcp_tools_registered", lambda *_: None)

    def create_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(rag_agent, "create_deep_agent", create_agent)
    rag_agent.create_rag_agent(registry, tool_names=("index_local_path",))

    assert captured["interrupt_on"]["index_local_path"] is True


def test_capability_catalog_exposes_filesystem_tools_without_path_values():
    from src.application.capabilities import capability_catalog
    from src.harness.events import EventBus
    from src.harness.plugins import PluginContext
    from src.harness.tools import ToolRegistry
    from src.bootstrap.agent_tools import AgentToolsPlugin

    registry = ToolRegistry()
    _run_async(AgentToolsPlugin().start(PluginContext(EventBus(), registry, {})))
    catalog = capability_catalog(registry, [], mcp_enabled=True)
    tools = {item["name"]: item for item in catalog["tools"]}
    assert tools["inspect_local_path"]["read_only"] is True
    assert tools["index_local_path"]["read_only"] is False
    assert tools["index_local_path"]["risk_level"] == "medium"
    assert "D:\\" not in json.dumps(catalog)
