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


@dataclass(frozen=True)
class ScoredDocument:
    """A retriever candidate with independently inspectable channel signals."""

    document: Any
    dense_score: float = 0.0
    bm25_score: float = 0.0
    fusion_score: float = 0.0
    dense_rank: int | None = None
    bm25_rank: int | None = None
    final_rank: int = 0

    @property
    def page_content(self) -> str:
        return str(getattr(self.document, "page_content", ""))

    @property
    def metadata(self) -> dict:
        return dict(getattr(self.document, "metadata", {}) or {})
