"""Framework-free routing language shared by application services."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Route(StrEnum):
    DIRECT = "direct"
    FAST_RAG = "fast_rag"
    AGENT = "agent"


@dataclass(frozen=True)
class RoutingDecision:
    route: Route
    confidence: float
    reasons: tuple[str, ...] = ()
    signals: dict[str, float | bool | int] = field(default_factory=dict)
    documents: tuple[Any, ...] = field(default_factory=tuple, repr=False, compare=False)

    def snapshot(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "signals": dict(self.signals),
        }
