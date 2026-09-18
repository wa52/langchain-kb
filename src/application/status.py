"""Application facade for runtime status queries."""

from src.adapters.legacy.status import get_system_status

__all__ = ["get_system_status"]
