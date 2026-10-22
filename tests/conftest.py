"""Shared test fixtures.

Forces the LAN access token off for every test so an ambient LAN_TOKEN in
the developer's .env cannot turn the API/MCP test suite into 401 failures.
Individual tests that exercise the security middleware patch config.LAN_TOKEN
explicitly.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_lan_token(monkeypatch):
    monkeypatch.setattr("config.LAN_TOKEN", "")


@pytest.fixture(autouse=True)
def _no_real_scheduled_sync(monkeypatch):
    """TestClient lifespan must never sync configured personal source folders."""
    monkeypatch.setattr("config.EXPERIENCE_DIRS", [])
