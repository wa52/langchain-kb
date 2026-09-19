"""Conversation adapter seam selected by the composition root.

The current dependency factory remains compatible with the existing API
module while the concrete persistence/model integrations are migrated here.
"""

from src.api.services.chat import _conversation_service


def create_conversation_backend():
    """Return the current ``ChatPort`` implementation."""
    return _conversation_service()
