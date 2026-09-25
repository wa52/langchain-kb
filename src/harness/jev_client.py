"""Provider-aware transport for the TypeSafe-compatible Jev API."""

from dataclasses import dataclass
from hashlib import sha256
from threading import Lock


_auth_lock = Lock()
_rejected_keys: set[bytes] = set()


@dataclass(frozen=True)
class JevEndpoint:
    provider: str
    url: str
    model: str


def endpoint_for_key(api_key: str) -> JevEndpoint:
    if api_key.strip().startswith("vck_"):
        return JevEndpoint(
            "vercel_gateway",
            "https://ai-gateway.vercel.sh/typesafe/v1/systemone",
            "typesafe-ai/jev",
        )
    return JevEndpoint("typesafe", "https://api.typesafe.ai/v1/systemone", "jev-latest")


def clear_jev_auth_rejection() -> None:
    with _auth_lock:
        _rejected_keys.clear()


def request_jev(payload: dict, api_key: str, *, force: bool = False) -> dict:
    import httpx

    endpoint = endpoint_for_key(api_key)
    fingerprint = sha256(api_key.encode("utf-8")).digest()
    with _auth_lock:
        if not force and fingerprint in _rejected_keys:
            raise PermissionError("Jev provider previously rejected this key")
    response = httpx.post(endpoint.url, json={**payload, "model": endpoint.model},
                          headers={"Authorization": f"Bearer {api_key}"}, timeout=5.0, trust_env=False)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        if response.status_code in (401, 403):
            with _auth_lock:
                _rejected_keys.add(fingerprint)
        raise
    with _auth_lock:
        _rejected_keys.discard(fingerprint)
    return response.json()
