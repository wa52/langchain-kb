"""Runtime composition root.

Only this module selects the current chat implementation.  Replacing the
legacy adapter with a native application backend therefore does not require
changing API, CLI, or Feishu transports.
"""

from src.ports.chat import ChatPort


def create_chat_backend() -> ChatPort:
    """Build the current chat backend behind the application port."""
    from src.adapters.legacy.chat import LegacyChatAdapter

    return LegacyChatAdapter()


def create_query_service(resource_manager):
    """Compose the retrieval adapter outside the application use case."""
    from src.adapters.retrieval.current import CurrentRetrieverAdapter
    from src.application.query import QueryService

    return QueryService(CurrentRetrieverAdapter(resource_manager.vector_store))


def create_agent_runtime(*, agent_factory, stream_fn):
    """Compose the current AgentRuntime without exposing LangGraph to callers."""
    from src.adapters.agent import LangGraphAgentRuntime

    return LangGraphAgentRuntime(agent_factory=agent_factory, stream_fn=stream_fn)
