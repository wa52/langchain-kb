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
