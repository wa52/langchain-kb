"""Framework-free routing language shared by application services."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Route(StrEnum):
    DIRECT = "direct"
    FAST_RAG = "fast_rag"
    AGENT = "agent"


class Intent(StrEnum):
    """User intent before runtime routing."""

    DIRECT = "direct"
    KNOWLEDGE = "knowledge"
    ACTION = "action"


@dataclass(frozen=True)
class IntentAssessment:
    intent: Intent
    domain: str = "general"
    side_effect: bool = False
    confidence: float = 0.0
    reasons: tuple[str, ...] = ()

    def snapshot(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "domain": self.domain,
            "side_effect": self.side_effect,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RoutingDecision:
    route: Route
    confidence: float
    reasons: tuple[str, ...] = ()
    signals: dict[str, float | bool | int] = field(default_factory=dict)
    documents: tuple[Any, ...] = field(default_factory=tuple, repr=False, compare=False)
    intent: Intent | None = None
    domain: str = "general"
    side_effect: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "signals": dict(self.signals),
            "intent": self.intent.value if self.intent else None,
            "domain": self.domain,
            "side_effect": self.side_effect,
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
