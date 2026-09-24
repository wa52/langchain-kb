"""Read-only capability catalog projection for user-facing surfaces."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def capability_catalog(tool_registry: Any, configured_servers: Iterable[dict], *, mcp_enabled: bool) -> dict:
    """Project registered tool metadata and configured MCP readiness safely.

    This function is deliberately observational: it never starts discovery or
    executes handlers. Secrets and endpoint targets are not part of the result.
    """
    tools = []
    if tool_registry is not None:
        for spec in tool_registry.catalog(include_disabled=True):
            tools.append({
                "name": spec.name,
                "description": spec.description,
                "source": spec.source,
                "server_id": spec.server_id,
                "tags": list(spec.tags),
                "risk_level": spec.risk_level,
                "read_only": spec.read_only,
                "retryable": spec.retryable,
                "enabled": spec.enabled,
            })

    states = getattr(tool_registry, "_mcp_server_states", {}) if tool_registry is not None else {}
    mcp_servers = []
    for server in configured_servers:
        name = str(server.get("name") or "")
        configured_enabled = bool(server.get("enabled", True))
        if not name:
            continue
        if not mcp_enabled or not configured_enabled:
            state = "disabled"
        else:
            state = {
                "READY": "ready",
                "DISCOVERING": "discovering",
                "DEGRADED": "degraded",
                "NOT_STARTED": "not_started",
            }.get(str(states.get(name, "NOT_STARTED")).upper(), "degraded")
        mcp_servers.append({
            "name": name,
            "type": str(server.get("type") or "local"),
            "enabled": mcp_enabled and configured_enabled,
            "status": state,
        })

    ready = sum(1 for item in tools if item["enabled"]) + sum(
        1 for item in mcp_servers if item["status"] == "ready"
    )
    degraded = sum(1 for item in mcp_servers if item["status"] == "degraded")
    return {
        "tools": sorted(tools, key=lambda item: (item["source"], item["name"])),
        "mcp_servers": sorted(mcp_servers, key=lambda item: item["name"]),
        "summary": {
            "tools": len(tools),
            "mcp_servers": len(mcp_servers),
            "ready": ready,
            "degraded": degraded,
        },
    }
