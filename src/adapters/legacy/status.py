"""Compatibility adapter for the current status implementation."""


def get_system_status(resource_manager):
    from src.api.services.status import get_system_status as _get

    return _get(resource_manager)
