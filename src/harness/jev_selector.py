"""Optional TypeSafe Jev adapter for high-precision tool selection."""

from collections.abc import Iterable
import os
from typing import Callable

from src.harness.selector import ToolCandidate, ToolSelectionContext, ToolSelector
from src.harness.tools import ToolSpec


class JevToolSelector:
    """Rank rule-recalled candidates with Jev; fall back safely on any failure."""

    def __init__(self, fallback: ToolSelector, *, api_key: str | None = None, max_candidates: int = 5, request: Callable | None = None) -> None:
        self._fallback = fallback
        self._api_key = api_key or os.getenv("TYPESAFE_API_KEY", "").strip()
        self._max_candidates = max_candidates
        self._request = request

    def select(self, query: str, tools: Iterable[ToolSpec], *, context: ToolSelectionContext | None = None) -> tuple[ToolCandidate, ...]:
        recalled = self._fallback.select(query, tools, context=context)
        if not self._api_key or not recalled:
            return recalled
        criteria = {
            item.spec.name: (
                f"{item.spec.description}\nsource={item.spec.source}; "
                f"server={item.spec.server_id or 'local'}; tags={', '.join(item.spec.tags)}; "
                f"read_only={item.spec.read_only}"
            )
            for item in recalled
        }
        payload = {"state": {"user_request": query}, "model": "jev-latest", "questions": {
            "tool": {"type": "choice", "instructions": "Which available tool best advances `user_request`?", "criteria": criteria}
        }}
        try:
            if self._request is None:
                import httpx
                response = httpx.post("https://api.typesafe.ai/v1/systemone", json=payload, headers={"Authorization": f"Bearer {self._api_key}"}, timeout=5.0, trust_env=False)
                response.raise_for_status()
                body = response.json()
            else:
                body = self._request(payload, self._api_key)
            probabilities = body["answers"]["tool"]["probabilities"]
            ranked = sorted(recalled, key=lambda item: (-float(probabilities.get(item.spec.name, 0)), item.spec.name))
            return tuple(ToolCandidate(item.spec, float(probabilities.get(item.spec.name, 0))) for item in ranked[:self._max_candidates])
        except Exception:
            return recalled

    def select_names(self, query: str, tools: Iterable[ToolSpec], *, context: ToolSelectionContext | None = None) -> tuple[str, ...]:
        return tuple(item.spec.name for item in self.select(query, tools, context=context))
