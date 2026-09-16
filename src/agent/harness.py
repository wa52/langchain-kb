"""Small policy layer around the Deep Agents execution loop."""

from langchain.agents.middleware import AgentMiddleware


def _retryable_tool(name: str) -> bool:
    lowered = name.lower()
    safe_names = {
        "read_file", "read_text_file", "list_directory", "list_directory_with_sizes",
        "search_files", "glob", "grep", "retrieve_knowledge", "retrieve_graph",
        "browser_search", "browser_open", "browser_read", "filesystem_read_file",
        "filesystem_list_directory", "filesystem_search_files",
    }
    return lowered in safe_names


class ToolRecoveryMiddleware(AgentMiddleware):
    """Retry one transient exception for read-only tools only."""

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception:
            name = request.tool_call.get("name", "")
            if not _retryable_tool(name):
                raise
            return handler(request)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception:
            name = request.tool_call.get("name", "")
            if not _retryable_tool(name):
                raise
            return await handler(request)


def verify_agent_run(answer: str, tool_results: list[dict], waiting_approval: bool) -> dict:
    """Return a stable, non-LLM completion verdict for a run."""
    if waiting_approval:
        return {"complete": False, "reason": "waiting_approval"}
    errors = [result for result in tool_results if result.get("status") == "error"]
    if errors:
        return {"complete": False, "reason": "tool_error", "error_count": len(errors)}
    if not answer.strip():
        return {"complete": False, "reason": "empty_answer"}
    return {"complete": True, "reason": "answer_produced"}
