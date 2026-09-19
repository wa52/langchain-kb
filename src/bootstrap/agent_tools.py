"""Default tool catalog assembled at the process composition root."""

from src.harness.events import Event
from src.harness.plugins import PluginContext


class AgentToolsPlugin:
    id = "agent-tools"

    async def start(self, context: PluginContext) -> None:
        from src.agent.tools import retrieve_graph, retrieve_knowledge, save_research_material
        from src.agent.project_workflow import project_workflow

        tools = [retrieve_knowledge, project_workflow, save_research_material]
        from config import ENABLE_GRAPH
        if ENABLE_GRAPH:
            tools.append(retrieve_graph)
        for tool in tools:
            context.tools.register_tool(tool, plugin_id=self.id)

        # External MCP discovery stays lazy and is performed once when the
        # Agent is first built; service startup must not wait on remote tools.

    async def stop(self, _context: PluginContext) -> None:
        return None
