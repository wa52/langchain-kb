"""LAN access protection.

When ``LAN_TOKEN`` is configured, non-loopback clients must present
``Authorization: Bearer <LAN_TOKEN>`` to reach the API and MCP surfaces.
Loopback access stays frictionless. When no token is configured, every
request is allowed (local-only default).
"""

import hmac
import ipaddress

from fastapi import Request
from fastapi.responses import JSONResponse

import config

_LOOPBACK_HOSTS = {"localhost", "localhost."}


def is_loopback(host: str | None) -> bool:
    """True when the client address is the local machine."""
    if not host:
        return False
    host = host.strip().lower()
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _authorized(host: str | None, auth_header: str | None) -> bool:
    """Whether a request from ``host`` with ``auth_header`` may proceed."""
    if not config.LAN_TOKEN:
        return True
    if is_loopback(host):
        return True
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return False
    token = auth_header[7:].strip()
    return hmac.compare_digest(token, config.LAN_TOKEN)


async def lan_access_middleware(request: Request, call_next):
    """Gate /api and /mcp behind the LAN token for non-loopback clients."""
    path = request.url.path.lower()
    if path.startswith("/api/") or path.startswith("/mcp"):
        host = request.client.host if request.client else None
        auth = request.headers.get("authorization")
        if not _authorized(host, auth):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "LAN access token required",
                },
            )
    return await call_next(request)
