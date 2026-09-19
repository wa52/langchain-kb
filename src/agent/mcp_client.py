"""External MCP client integration for the RAG agent.

Loads MCP server config (opencode-style mcp.json) and connects to external
MCP servers, returning LangChain BaseTools that are merged into the agent's
toolset. Failures degrade gracefully — the local knowledge tools always work.
"""

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class McpToolEntry:
    """An MCP tool together with the server metadata needed by the harness."""

    tool: object
    server_id: str
    tags: tuple[str, ...]
    risk_level: str
    retryable: bool
    read_only: bool


MCP_CATALOG_NOT_STARTED = "NOT_STARTED"
MCP_CATALOG_DISCOVERING = "DISCOVERING"
MCP_CATALOG_READY = "READY"
MCP_CATALOG_DEGRADED = "DEGRADED"

# A registry is process-local, but several chat requests can reach it at the
# same time.  This lock protects creation and state transitions of the small
# per-registry MCP lifecycle maps attached below.
_CATALOG_STATE_LOCK = threading.Lock()


_MUTATING_TOOL_WORDS = frozenset({
    "create", "write", "update", "edit", "delete", "remove", "move",
    "rename", "execute", "run", "send", "publish", "upload",
})


def _tool_metadata(server_id: str, tool) -> tuple[tuple[str, ...], str, bool, bool]:
    """Infer safe discovery metadata without changing how an MCP tool runs.

    MCP servers do not consistently expose side-effect annotations through the
    LangChain adapter.  Until a server provides them, name/description verbs
    give the registry a conservative, inspectable baseline.  Execution policy
    will consume this metadata in a later phase; this function only describes
    the tool catalog.
    """
    text = f"{getattr(tool, 'name', '')} {getattr(tool, 'description', '')}".lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    is_mutating = bool(words & _MUTATING_TOOL_WORDS)
    tags = {"mcp", server_id.lower(), "write" if is_mutating else "read"}
    tags.update(words & _MUTATING_TOOL_WORDS)
    return tuple(sorted(tags)), ("medium" if is_mutating else "low"), not is_mutating, not is_mutating


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


def _to_connections(config_path, server_names: set[str] | None = None) -> dict:
    """Convert opencode-style servers to MultiServerMCPClient connections.

    local  → {"command", "args", "transport": "stdio"}
    remote → {"url", "transport": "streamable-http", "headers"}
    """
    connections: dict = {}
    for name, cfg in _enabled_servers(config_path).items():
        if server_names is not None and name not in server_names:
            continue
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


def _load_mcp_tool_entries_for_connection(
    server_name: str,
    connection: dict,
    *,
    tool_name_prefix: bool,
    tool_mode: str,
) -> list[McpToolEntry] | None:
    """Discover one server without allowing it to delay another server.

    ``None`` means the server could not be reached.  An empty list is a valid
    READY result for a server which currently exposes no tools.
    """
    from config import MCP_DISCOVERY_TIMEOUT_SECONDS
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        import asyncio
        client = MultiServerMCPClient({server_name: connection}, tool_name_prefix=tool_name_prefix)
        server_tools = asyncio.run(_get_tools_with_timeout(
            client, server_name, timeout_seconds=MCP_DISCOVERY_TIMEOUT_SECONDS,
        ))
    except Exception as exc:
        print(f"  [MCP] 跳过服务器 {server_name}（不影响其他 MCP）: {exc}")
        return None

    result: list[McpToolEntry] = []
    if tool_mode == "dispatch":
        if server_tools:
            tool = _server_dispatch_tool(server_name, server_tools)
            tags, risk_level, retryable, read_only = _tool_metadata(server_name, tool)
            result.append(McpToolEntry(tool, server_name, tags, risk_level, retryable, read_only))
    else:
        for server_tool in server_tools:
            tool = _make_sync_compatible(server_tool)
            tags, risk_level, retryable, read_only = _tool_metadata(server_name, tool)
            result.append(McpToolEntry(tool, server_name, tags, risk_level, retryable, read_only))
    return result


def load_mcp_tool_entries(config_path, tool_name_prefix: bool = True, tool_mode: str | None = None) -> list[McpToolEntry]:
    """Load MCP tools with the originating server's discovery metadata.

    ``direct`` exposes every MCP operation as an individual Agent tool. The
    legacy ``dispatch`` mode exposes one operation router per server. The mode
    defaults to ``MCP_TOOL_MODE`` and then to ``direct``.

    Each server is loaded independently so one unavailable server does not hide
    tools from other enabled servers. Missing config and total load failures
    still degrade to an empty list so local tools remain available.
    """
    from config import MCP_ENABLED
    if not MCP_ENABLED:
        return []

    connections = _to_connections(config_path)
    if not connections:
        return []

    mode = (tool_mode or os.getenv("MCP_TOOL_MODE", "direct")).strip().lower()
    if mode not in {"direct", "dispatch"}:
        print(f"  [MCP] 忽略无效 MCP_TOOL_MODE={mode!r}，使用 direct")
        mode = "direct"

    result: list[McpToolEntry] = []
    for server_name, connection in connections.items():
        entries = _load_mcp_tool_entries_for_connection(
            server_name, connection, tool_name_prefix=tool_name_prefix, tool_mode=mode,
        )
        if entries is not None:
            result.extend(entries)
    return result


def load_mcp_tool_entries_for_server(
    config_path, server_name: str, tool_name_prefix: bool = True, tool_mode: str | None = None,
) -> list[McpToolEntry] | None:
    """Load one configured server for the parallel catalog lifecycle."""
    from config import MCP_ENABLED
    if not MCP_ENABLED:
        return []
    connections = _to_connections(config_path, {server_name})
    connection = connections.get(server_name)
    if connection is None:
        return None
    mode = (tool_mode or os.getenv("MCP_TOOL_MODE", "direct")).strip().lower()
    if mode not in {"direct", "dispatch"}:
        mode = "direct"
    return _load_mcp_tool_entries_for_connection(
        server_name, connection, tool_name_prefix=tool_name_prefix, tool_mode=mode,
    )


async def _get_tools_with_timeout(client, server_name: str, *, timeout_seconds: float):
    """Bound lazy MCP discovery so an unavailable server cannot block chat."""
    import asyncio

    return await asyncio.wait_for(
        client.get_tools(server_name=server_name),
        timeout=max(0.1, float(timeout_seconds)),
    )


def load_mcp_tools(config_path, tool_name_prefix: bool = True, tool_mode: str | None = None) -> list:
    """Load external MCP tools for legacy callers that only need handlers."""
    return [entry.tool for entry in load_mcp_tool_entries(config_path, tool_name_prefix, tool_mode)]


def _catalog_maps(tool_registry, config_path: str) -> tuple[dict[str, str], dict[str, threading.Event]]:
    """Create the per-server catalog state once for a ToolRegistry."""
    with _CATALOG_STATE_LOCK:
        states = getattr(tool_registry, "_mcp_server_states", None)
        events = getattr(tool_registry, "_mcp_server_events", None)
        if states is None or events is None:
            enabled = _enabled_servers(config_path)
            connections = _to_connections(config_path)
            states = {
                name: (MCP_CATALOG_NOT_STARTED if name in connections else MCP_CATALOG_DEGRADED)
                for name in enabled
            }
            events = {name: threading.Event() for name in enabled}
            for name, state in states.items():
                if state == MCP_CATALOG_DEGRADED:
                    events[name].set()
            tool_registry._mcp_server_states = states
            tool_registry._mcp_server_events = events
            tool_registry._mcp_config_path = config_path
        return states, events


def _refresh_catalog_flags(tool_registry) -> None:
    states = getattr(tool_registry, "_mcp_server_states", {})
    tool_registry._mcp_catalog_discovering = any(state == MCP_CATALOG_DISCOVERING for state in states.values())
    tool_registry._mcp_catalog_discovered = bool(states) and not tool_registry._mcp_catalog_discovering


def _register_mcp_entries(tool_registry, entries: list[McpToolEntry]) -> None:
    for entry in entries:
        try:
            existing = tool_registry.get(getattr(entry.tool, "name", ""))
        except KeyError:
            existing = None
        if existing is not None:
            continue
        tool_registry.register_tool(
            entry.tool,
            plugin_id="mcp",
            source="mcp",
            server_id=entry.server_id,
            tags=entry.tags,
            risk_level=entry.risk_level,
            retryable=entry.retryable,
            read_only=entry.read_only,
        )


def ensure_mcp_tools_registered(tool_registry, config_path=None) -> None:
    """Populate a registry's MCP catalog once, on the first Agent request.

    This preserves fast API startup while ensuring ToolSelector sees the same
    MCP catalog that the eventual Agent can receive.  A failed discovery is
    remembered for this runtime; changing MCP settings creates a fresh Agent
    lifecycle and therefore retries discovery.
    """
    path = config_path or default_mcp_config_path()
    states, events = _catalog_maps(tool_registry, path)

    def discover(server_name: str) -> None:
        try:
            entries = load_mcp_tool_entries_for_server(path, server_name)
            if entries is None:
                states[server_name] = MCP_CATALOG_DEGRADED
            else:
                _register_mcp_entries(tool_registry, entries)
                states[server_name] = MCP_CATALOG_READY
        finally:
            events[server_name].set()
            _refresh_catalog_flags(tool_registry)

    # MCP processes and remote endpoints can take seconds to launch.  Start
    # each one independently: a slow browser/filesystem process must never
    # postpone GitHub or Feishu becoming selectable.
    for server_name, state in tuple(states.items()):
        if state != MCP_CATALOG_NOT_STARTED:
            continue
        states[server_name] = MCP_CATALOG_DISCOVERING
        _refresh_catalog_flags(tool_registry)
        threading.Thread(
            target=discover, args=(server_name,), name=f"mcp-discovery-{server_name}", daemon=True,
        ).start()


def mcp_catalog_readiness(tool_registry, domain: str | None, *, timeout_seconds: float | None = None) -> dict[str, object]:
    """Return domain-specific MCP readiness, with at most a short bounded wait.

    The caller invokes this only for a routed Agent action.  General chat and
    KB/RAG requests never wait for MCP discovery.  A missing or failed server
    is an explicit degraded result rather than a silent empty tool catalog.
    """
    normalized = (domain or "").strip().lower()
    states = getattr(tool_registry, "_mcp_server_states", {})
    events = getattr(tool_registry, "_mcp_server_events", {})
    if not normalized or normalized == "general" or normalized not in states:
        return {"domain": normalized or "general", "state": "NOT_APPLICABLE", "waited_ms": 0.0}

    if timeout_seconds is None:
        from config import MCP_ACTION_READY_WAIT_SECONDS
        timeout_seconds = MCP_ACTION_READY_WAIT_SECONDS
    started = time.perf_counter()
    state = states.get(normalized, MCP_CATALOG_DEGRADED)
    if state == MCP_CATALOG_DISCOVERING:
        events[normalized].wait(timeout=max(0.0, float(timeout_seconds)))
        state = states.get(normalized, MCP_CATALOG_DISCOVERING)
    return {
        "domain": normalized,
        "state": state,
        "waited_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def default_mcp_config_path() -> str:
    """Default mcp.json location (MCP_CONFIG_PATH or <KNOWLEDGE_HOME>/mcp.json)."""
    from config import MCP_CONFIG_PATH
    return MCP_CONFIG_PATH
