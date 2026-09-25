"""Default tool catalog assembled at the process composition root."""

from src.harness.events import Event
from src.harness.plugins import PluginContext


class AgentToolsPlugin:
    id = "agent-tools"

    async def start(self, context: PluginContext) -> None:
        from src.agent.tools import retrieve_graph, retrieve_knowledge, save_research_material
        from src.agent.project_workflow import project_workflow
        from src.agent.filesystem_tools import inspect_local_path, index_local_path

        tools = [
            retrieve_knowledge, project_workflow, save_research_material,
            inspect_local_path, index_local_path,
        ]
        from config import ENABLE_GRAPH
        if ENABLE_GRAPH:
            tools.append(retrieve_graph)
        for tool in tools:
            if tool.name == "inspect_local_path":
                context.tools.register_tool(
                    tool, plugin_id=self.id, tags=("filesystem", "read", "local"),
                    risk_level="low", retryable=True, read_only=True,
                )
                continue
            if tool.name == "index_local_path":
                context.tools.register_tool(
                    tool, plugin_id=self.id, tags=("filesystem", "knowledge", "write", "index"),
                    risk_level="medium", retryable=False, read_only=False,
                )
                continue
            tags = ("knowledge", "search") if tool.name.startswith("retrieve") else ("knowledge", "write")
            context.tools.register_tool(tool, plugin_id=self.id, tags=tags, retryable=tool.name.startswith("retrieve"), read_only=tool.name.startswith("retrieve"))

        # External MCP discovery stays lazy and is performed once when the
        # Agent is first built; service startup must not wait on remote tools.

    async def stop(self, _context: PluginContext) -> None:
        return None
