"""LAN access token protection tests.

Covers the security middleware seam: loopback exemption, Bearer token
enforcement for non-loopback clients, and no-auth when no token is set.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_singleton():
    from src.resources import ResourceManager
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    yield
    ResourceManager._instance = None


@pytest.fixture
def rm():
    from src.resources import ResourceManager
    rm = ResourceManager.get_instance()
    rm._initialized = True
    rm.vector_store = MagicMock()
    rm.graph = MagicMock()
    rm.agent = MagicMock()
    return rm


@pytest.fixture
def client(rm):
    from src.api.app import create_app
    return TestClient(create_app())


class TestIsLoopback:
    def test_loopback_hosts(self):
        from src.api.security import is_loopback
        assert is_loopback("127.0.0.1")
        assert is_loopback("127.0.0.2")
        assert is_loopback("::1")
        assert is_loopback("0:0:0:0:0:0:0:1")
        assert is_loopback("::ffff:127.0.0.1")
        assert is_loopback("localhost")
        assert is_loopback("LOCALHOST")
        assert is_loopback("localhost.")

    def test_remote_hosts(self):
        from src.api.security import is_loopback
        assert not is_loopback("192.168.1.10")
        assert not is_loopback("10.0.0.5")
        assert not is_loopback("testserver")
        assert not is_loopback(None)


class TestAuthorized:
    def test_no_token_configured_allows_all(self):
        from src.api.security import _authorized
        with patch("config.LAN_TOKEN", ""):
            assert _authorized("192.168.1.10", None) is True
            assert _authorized(None, None) is True

    def test_loopback_exempt_when_token_set(self):
        from src.api.security import _authorized
        with patch("config.LAN_TOKEN", "sekrit"):
            assert _authorized("127.0.0.1", None) is True
            assert _authorized("::1", None) is True

    def test_remote_requires_bearer(self):
        from src.api.security import _authorized
        with patch("config.LAN_TOKEN", "sekrit"):
            assert _authorized("192.168.1.10", None) is False
            assert _authorized("192.168.1.10", "Bearer sekrit") is True
            assert _authorized("192.168.1.10", "Bearer wrong") is False
            assert _authorized("192.168.1.10", "bearer sekrit") is True
            assert _authorized("192.168.1.10", "Basic abc") is False


class TestMiddleware:
    def test_api_allowed_without_token_when_unconfigured(self, client):
        with patch("config.LAN_TOKEN", ""):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_api_rejects_remote_without_token(self, client):
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 401
        assert "token" in resp.json()["detail"].lower()

    def test_api_rejects_wrong_token(self, client):
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.get(
                "/api/v1/health",
                headers={"Authorization": "Bearer nope"},
            )
        assert resp.status_code == 401

    def test_api_allows_correct_token(self, client):
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.get(
                "/api/v1/health",
                headers={"Authorization": "Bearer sekrit"},
            )
        assert resp.status_code == 200

    def test_static_spa_not_gated(self, client):
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.get("/some/spa/route")
        # SPA fallback is served openly; middleware only gates /api and /mcp.
        assert resp.status_code in (200, 404)
        assert "LAN access token required" not in resp.text

    def test_mcp_path_gated(self, client):
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.post("/mcp")
        assert resp.status_code == 401
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.post("/mcp", headers={"Authorization": "Bearer sekrit"})
        assert resp.status_code != 401

    def test_loopback_bypass_in_middleware(self):
        import asyncio

        from starlette.requests import Request as StarletteRequest

        from src.api.security import lan_access_middleware

        passthrough = MagicMock(status_code=200)

        async def call_next(_request):
            return passthrough

        async def run():
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/health",
                "headers": [],
                "client": ("127.0.0.1", 54321),
                "query_string": b"",
                "scheme": "http",
                "server": ("127.0.0.1", 8000),
                "asgi": {"version": "3.0"},
            }
            with patch("config.LAN_TOKEN", "sekrit"):
                return await lan_access_middleware(StarletteRequest(scope), call_next)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(run())
        finally:
            loop.close()
        assert result is passthrough

    def test_case_insensitive_gate(self, client):
        with patch("config.LAN_TOKEN", "sekrit"):
            resp = client.get("/API/v1/health")
        assert resp.status_code == 401
