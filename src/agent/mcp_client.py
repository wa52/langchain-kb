"""External MCP client integration for the RAG agent.

Loads MCP server config (opencode-style mcp.json) and connects to external
MCP servers, returning LangChain BaseTools that are merged into the agent's
toolset. Failures degrade gracefully — the local knowledge tools always work.
"""

import json
import os
from pathlib import Path


def parse_mcp_config(path) -> dict:
    """Read mcp.json (opencode-style) and return the servers dict.

    Format:
    {
      "mcp": {
        "filesystem": {"type": "local", "command": [...], "enabled": true},
        "remote_svc": {"type": "remote", "url": "...", "enabled": true,
                       "headers": {...}}
      }
    }
    Returns {} if the file is missing or malformed.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    servers = data.get("mcp", data) if isinstance(data, dict) else {}
    return servers if isinstance(servers, dict) else {}


def _enabled_servers(config_path) -> dict:
    servers = parse_mcp_config(config_path)
    return {
        name: cfg for name, cfg in servers.items()
        if isinstance(cfg, dict) and cfg.get("enabled", True)
    }


def _to_connections(config_path) -> dict:
    """Convert opencode-style servers to MultiServerMCPClient connections.

    local  → {"command", "args", "transport": "stdio"}
    remote → {"url", "transport": "streamable-http", "headers"}
    """
    connections: dict = {}
    for name, cfg in _enabled_servers(config_path).items():
        stype = (cfg.get("type") or "local").lower()
        if stype == "remote":
            conn = {"url": cfg["url"], "transport": "streamable-http"}
            if cfg.get("headers"):
                conn["headers"] = cfg["headers"]
        else:
            cmd = cfg.get("command") or []
            conn = {
                "command": cmd[0] if cmd else "",
                "args": list(cmd[1:]) if len(cmd) > 1 else [],
                "transport": "stdio",
            }
        connections[name] = conn
    return connections


def _make_sync_compatible(tool):
    """Wrap an async-only MCP tool so it also supports synchronous invocation.

    MCP tools are StructuredTool with func=None and only an async _arun.
    The sync agent (agent.stream) calls _run which raises "does not support
    sync invocation". Rebuild the tool with a sync func that bridges via
    asyncio.run, while keeping the original async coroutine.
    """
    if getattr(tool, "func", None) is not None:
        return tool

    original_arun = tool._arun
    args_schema = tool.args_schema

    def sync_func(*args, config=None, run_manager=None, **kwargs):
        import asyncio
        # StructuredTool's _run passes config only when the func signature has
        # a config param; we declare it so the async impl receives it.
        return asyncio.run(original_arun(*args, config=config, run_manager=run_manager, **kwargs))

    from langchain_core.tools import StructuredTool
    return StructuredTool.from_function(
        func=sync_func,
        coroutine=original_arun,
        name=tool.name,
        description=tool.description,
        args_schema=args_schema,
        return_direct=getattr(tool, "return_direct", False),
        response_format=getattr(tool, "response_format", "content"),
    )


def load_mcp_tools(config_path, tool_name_prefix: bool = True) -> list:
    """Load external MCP tools for the agent.

    Returns a list of LangChain BaseTools, each wrapped to support both sync
    and async invocation. On any failure (missing config, server unreachable),
    returns [] so the agent still builds with local tools.
    """
    connections = _to_connections(config_path)
    if not connections:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        import asyncio

        client = MultiServerMCPClient(
            connections,
            tool_name_prefix=tool_name_prefix,
        )
        tools = asyncio.run(client.get_tools())
        return [_make_sync_compatible(t) for t in tools]
    except Exception as e:
        print(f"  [MCP] 外部工具加载失败（不影响本地工具）: {e}")
        return []


def default_mcp_config_path() -> str:
    """Default mcp.json location (MCP_CONFIG_PATH or <KNOWLEDGE_HOME>/mcp.json)."""
    from config import MCP_CONFIG_PATH
    return MCP_CONFIG_PATH
