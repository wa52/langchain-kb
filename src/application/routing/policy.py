"""Pure policy combining intent, context, and retrieval evidence."""

from __future__ import annotations

from src.application.routing.context import ContextAssessment
from src.application.routing.retrieval_probe import RetrievalProbe
from src.domain.routing import Intent, IntentAssessment, Route, RoutingDecision


class RoutingPolicy:
    def __init__(self, *, rag_threshold: float) -> None:
        self._rag_threshold = max(0.0, min(1.0, rag_threshold))

    def decide(self, intent: IntentAssessment, context: ContextAssessment, probe: RetrievalProbe | None, *, routing_ms: float) -> RoutingDecision:
        if intent.intent is Intent.ACTION:
            return self._decision(Route.AGENT, intent.confidence, intent, ("tool_or_side_effect_intent",), {"routing_ms": routing_ms})
        if intent.intent is Intent.DIRECT and not context.is_knowledge_follow_up:
            if probe is not None:
                signals = probe.signals(context=False, topic_similarity=context.topic_similarity)
                signals["routing_ms"] = routing_ms
                return self._decision(Route.DIRECT, intent.confidence, intent, intent.reasons, signals)
            return self._decision(Route.DIRECT, intent.confidence, intent, intent.reasons, {"routing_ms": routing_ms})
        if probe is None:
            return self._decision(Route.DIRECT, 0.0, intent, ("no_retrieval_probe",), {"routing_ms": routing_ms})
        signals = probe.signals(context=context.is_knowledge_follow_up, topic_similarity=context.topic_similarity)
        confidence = round(0.58 * probe.semantic + 0.20 * probe.lexical + 0.12 * probe.rank_gap + 0.10 * float(signals["context"]), 3)
        reasons = ["retrieval_semantic_hit"] if probe.semantic >= self._rag_threshold else []
        if probe.lexical >= 0.25:
            reasons.append("keyword_coverage")
        if context.is_knowledge_follow_up:
            reasons.append("context_followup")
        if probe.documents:
            reasons.append("hybrid_candidates_available")
        route = Route.FAST_RAG if confidence >= self._rag_threshold else Route.DIRECT
        return self._decision(route, confidence, intent, tuple(reasons or ["low_retrieval_confidence"]), signals, probe.documents)

    @staticmethod
    def _decision(route, confidence, intent, reasons, signals, documents=()):
        return RoutingDecision(route, confidence, tuple(reasons), dict(signals), tuple(documents), intent.intent, intent.domain, intent.side_effect)
