"""External MCP client integration for the RAG agent.

Loads MCP server config (opencode-style mcp.json) and connects to external
MCP servers, returning LangChain BaseTools that are merged into the agent's
toolset. Failures degrade gracefully — the local knowledge tools always work.
"""

import json
import os
import re
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


_ENV_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _resolve_command_value(value):
    """Expand an exact ``${ENV_VAR}`` command value without exposing secrets.

    MCP configurations are usually committed or shared, so credentials must
    remain in the environment rather than being copied into ``mcp.json``.
    Values that are not an exact variable reference are returned unchanged.
    """
    if not isinstance(value, str):
        return value
    match = _ENV_REFERENCE.fullmatch(value)
    return os.getenv(match.group(1), "") if match else value


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
            cmd = [_resolve_command_value(value) for value in (cfg.get("command") or [])]
            if not cmd or not cmd[0] or any(value == "" for value in cmd):
                print(f"  [MCP] 跳过服务器 {name}（缺少命令或环境变量）")
                continue
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


def _server_dispatch_tool(server_name: str, server_tools: list):
    """Collapse all tools of one MCP server into a single dispatch tool.

    The agent sees one tool per server (e.g. `filesystem`) whose first
    argument is `operation` (the underlying MCP tool name) followed by that
    operation's arguments. The args schema dynamically includes the parameter
    fields of all operations so the LLM knows what each operation expects.
    """
    from pydantic import BaseModel, Field, ConfigDict, create_model
    from langchain_core.tools import StructuredTool

    operations = {getattr(t, "name", ""): t for t in server_tools if getattr(t, "name", "")}
    op_list = ", ".join(sorted(operations)) or "（无）"

    # Collect parameter fields from every operation's args_schema
    param_fields: dict[str, tuple] = {}
    op_param_hint: dict[str, list[str]] = {}
    for op_name, tool in operations.items():
        schema = getattr(tool, "args_schema", None)
        try:
            if isinstance(schema, dict):
                props = schema.get("properties", {})
            elif schema is not None and hasattr(schema, "model_json_schema"):
                props = schema.model_json_schema().get("properties", {})
            else:
                props = {}
        except Exception:
            props = {}
        op_param_hint[op_name] = sorted(props.keys())
        for pname, pspec in props.items():
            if pname not in param_fields:
                ftype = pspec.get("type")
                if not ftype and pspec.get("anyOf"):
                    ftype = next(
                        (item.get("type") for item in pspec["anyOf"] if item.get("type") != "null"),
                        None,
                    )
                default = pspec.get("default", None)
                ann = str if ftype == "string" else (float if ftype == "number" else (int if ftype == "integer" else str))
                if default is None and pspec.get("anyOf"):
                    ann = ann | None
                desc = pspec.get("description", "")
                param_fields[pname] = (ann, Field(default=default, description=desc))

    param_hint_text = "\n".join(
        f"  {op}: {', '.join(params) if params else '（无参数）'}"
        for op, params in op_param_hint.items()
    )

    fields = {
        "operation": (str, Field(description=f"要调用的操作，可选: {op_list}")),
        **param_fields,
    }
    DispatchArgs = create_model(
        f"{server_name}DispatchArgs",
        **fields,
        __config__=ConfigDict(extra="allow"),
    )

    def dispatch(operation: str, **kwargs) -> str:
        tool = operations.get(operation)
        if tool is None:
            return f"未知操作: {operation}，可用操作: {op_list}"
        # Forward the operation's own parameters only
        allowed = set(op_param_hint.get(operation, []))
        # The dispatch schema merges parameters from all operations, so fields
        # belonging to another operation arrive as None. Do not forward those
        # synthetic values to the stricter MCP schema.
        forwarded = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        return _make_sync_compatible(tool).invoke(forwarded)

    description = (
        f"调用 {server_name} MCP 服务器的工具。\n"
        f"可用操作（operation）: {op_list}\n"
        f"各操作所需参数:\n{param_hint_text}\n"
        "用法: 传 operation=某操作名，以及该操作所需的参数。"
    )
    return StructuredTool.from_function(
        func=dispatch,
        name=server_name,
        description=description,
        args_schema=DispatchArgs,
    )


def load_mcp_tools(config_path, tool_name_prefix: bool = True, tool_mode: str | None = None) -> list:
    """Load external MCP tools for the agent.

    ``direct`` exposes every MCP operation as an individual Agent tool. The
    legacy ``dispatch`` mode exposes one operation router per server. The mode
    defaults to ``MCP_TOOL_MODE`` and then to ``direct``.

    Each server is loaded independently so one unavailable server does not hide
    tools from other enabled servers. Missing config and total load failures
    still degrade to an empty list so local tools remain available.
    """
    connections = _to_connections(config_path)
    if not connections:
        return []

    mode = (tool_mode or os.getenv("MCP_TOOL_MODE", "direct")).strip().lower()
    if mode not in {"direct", "dispatch"}:
        print(f"  [MCP] 忽略无效 MCP_TOOL_MODE={mode!r}，使用 direct")
        mode = "direct"

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        import asyncio

        client = MultiServerMCPClient(
            connections,
            tool_name_prefix=tool_name_prefix,
        )
    except Exception as e:
        print(f"  [MCP] 外部工具客户端加载失败（不影响本地工具）: {e}")
        return []

    result = []
    for server_name in connections:
        try:
            server_tools = asyncio.run(client.get_tools(server_name=server_name))
            if mode == "dispatch":
                if server_tools:
                    result.append(_server_dispatch_tool(server_name, server_tools))
            else:
                result.extend(_make_sync_compatible(tool) for tool in server_tools)
        except Exception as e:
            print(f"  [MCP] 跳过服务器 {server_name}（不影响其他 MCP）: {e}")
    return result


def default_mcp_config_path() -> str:
    """Default mcp.json location (MCP_CONFIG_PATH or <KNOWLEDGE_HOME>/mcp.json)."""
    from config import MCP_CONFIG_PATH
    return MCP_CONFIG_PATH
